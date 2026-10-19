"""Application facade: IPC and recording only. Never opens Bluetooth."""
import asyncio
from .protocol import parse_telemetry
from .safety_health import boot_seconds

class Controller:
    def __init__(self,safety_client,*,recorder=None,recorder_factory=None,clock=boot_seconds):
        self.recorder_factory=recorder_factory
        self.safety=safety_client;self.clock=clock;self.clients={};self.owner=None;self.claimant=None;self.claimed_at=0
        self.generation=0;self.sequence=0;self.tasks=set();self.subscribers=set();self.last=None
        self.connected=False;self.connecting=False;self.storage_fault=None;self.recording=None
        self.last_key=None;self.last_authority=None;self.seen=set();self.ready_revision=0;self.renewal_seq=0
        self.tracking_review=False;self.current_fault=None;self.readiness_task=None;self.initializing=True
        self.reconnect_task=None;self.reconnect_after=0
        if recorder:
            from .recorder import RecordingWorker
            self.recording=RecordingWorker(recorder,self.recording_failed,self.recorded)
        self.unsubscribe=self.safety.subscribe(self.received)
    async def initialize(self):
        await self.safety.open()
        if self.recorder_factory is not None:
            from .recorder import RecordingWorker
            recorder=await asyncio.to_thread(self.recorder_factory)
            await recorder.initialize()
            self.recording=RecordingWorker(recorder,self.recording_failed,self.recorded)
        self.initializing=False
        await self.collect_safety_evidence()
        await self.publish_readiness()
    async def collect_safety_evidence(self):
        s=self.safety.snapshot
        if s.get('fault_id'):
            samples=[];cursor=0
            while len(samples)<256:
                evidence=await self.safety.request('evidence',{'after_seq':cursor,'limit':256-len(samples)})
                samples.extend(evidence['samples'])
                if evidence.get('next_seq',cursor)<=cursor or evidence.get('next_seq',0)>=evidence['snapshot']['ring_last_seq']:break
                cursor=evidence['next_seq']
            self.record('safety_evidence',(evidence['snapshot'],samples))
    def register_client(self,client_id,kind):
        if kind not in ('browser','tray','helper'):raise ValueError('Invalid client kind')
        self.clients[client_id]=kind
    async def unregister_client(self,client_id):
        await self.client_lost(client_id);self.clients.pop(client_id,None)
    def spawn(self,coroutine):
        t=asyncio.create_task(coroutine);self.tasks.add(t);t.add_done_callback(self.tasks.discard);return t
    def subscribe(self,callback):self.subscribers.add(callback);return lambda:self.subscribers.discard(callback)
    def emit(self,event,**data):
        self.sequence+=1;message=dict(v=1,event=event,seq=self.sequence,generation=self.generation,data=data)
        for c in tuple(self.subscribers):
            try:c(message)
            except Exception:self.subscribers.discard(c)
    def session_summary(self):
        row=self.recording.recorder.snapshot() if self.recording else None
        return {k:v for k,v in row.items() if k not in ('sourceTelemetry','speedSamples','safetyEvidence')} if row else None
    def snapshot_for(self,client_id):
        s=self.safety.snapshot;available=self.safety.available
        owner=s.get('owner_id') if s.get('grant_id') else None
        session=self.session_summary();recovery=bool(s.get('fault_id'))
        return dict(generation=self.generation,connected=available and s.get('connected',False),
            connecting=self.connecting,is_owner=available and owner==client_id,
            owner_kind=s.get('owner_kind') if owner else None,owner_present=owner is not None,
            target_speed=s.get('target_speed',1000),blocked=not available or s.get('authorization_state')!='ready' or bool(self.storage_fault),
            recovery=recovery,storage_fault=self.storage_fault,stale=not available or s.get('stale',True),
            stopping=s.get('stopping',False),telemetry=s.get('telemetry_hex'),
            metrics={k:getattr(self.last,k) for k in ('speed_raw','state','unit_mode','distance','steps','calories','duration')} if self.last else None,
            session=session,safety_available=available,safety_fault=s.get('fault'),fault_id=s.get('fault_id'),
            stop_confirmation_id=s.get('stop_confirmation_id'),authorization_state=s.get('authorization_state','unarmed'),
            is_recovery_claimant=self.claimant==client_id,can_resolve_session=self.claimant==client_id or owner==client_id)
    def record(self,kind,payload=None):
        return self.recording.offer(kind,payload) if self.recording else True
    def recording_failed(self,message):
        self.storage_fault=message;self.emit('storage_fault',message=message)
        if self.safety.available:self.spawn(self.withdraw_readiness())
    def recorded(self,row):
        self.tracking_review=bool(row and row['status']=='interrupted');self.emit('walk',session=self.session_summary())
    async def withdraw_readiness(self):
        self.ready_revision+=1
        try:await self.safety.request('recording_ready',dict(ready=False,revision=self.ready_revision,fault_id=self.safety.snapshot.get('fault_id')))
        except ValueError:pass
    async def publish_readiness(self):
        if not self.safety.available or self.storage_fault:return
        if self.recording:await self.recording.drain()
        if self.storage_fault or self.session_summary() and self.session_summary()['status']=='interrupted':return
        self.ready_revision+=1
        await self.safety.request('recording_ready',dict(ready=True,revision=self.ready_revision,fault_id=self.safety.snapshot.get('fault_id')))
    def received(self,message):
        event=message.get('event');s=self.safety.snapshot
        if s.get('fault_id') and s.get('fault_id')!=self.current_fault:
            self.record('safety_evidence',(s,[]))
        self.current_fault=s.get('fault_id')
        key=(s.get('safety_id'),s.get('link_epoch'),s.get('fault_generation'),s.get('grant_id'))
        if key!=self.last_authority:self.last_authority=key;self.generation+=1;self.seen.clear()
        self.connected=self.safety.available and s.get('connected',False)
        self.owner=s.get('owner_id') if s.get('grant_id') else None
        if event=='lost':
            self.owner=None;self.claimant=None;self.connected=False;self.record('interrupt','Safety unavailable; continuity needs review')
            self.emit('lost',**message.get('data',{}));return
        if event=='fault':
            self.record('interrupt','Safety fault; continuity needs review');self.emit('safety',confirmed=False,message=(s.get('fault') or {}).get('reason','Safety fault'));return
        raw=s.get('telemetry_hex');seq=s.get('telemetry_seq',0)
        tk=(s.get('safety_id'),s.get('link_epoch'),seq)
        if raw and tk!=self.last_key:
            gap=self.last_key is not None and (tk[:2]!=self.last_key[:2] or seq!=self.last_key[2]+1)
            if gap:self.record('interrupt','Safety telemetry gap; coverage partial')
            self.last_key=tk
            try:self.last=parse_telemetry(bytes.fromhex(raw))
            except ValueError:self.last=None
            if self.last:
                if s.get('fault_id'):self.record('interrupt','Safety fault; continuity needs review')
                self.record('observe',self.last)
                self.emit('telemetry',hex=raw)
        if event=='safety':self.emit('safety',**message.get('data',{}))
        self.emit('state',state='stopping' if s.get('stopping') else 'ready' if self.connected else 'disconnected',connected=self.connected,blocked=self.snapshot_for(None)['blocked'])
    async def request(self,op,args=None):
        result=await self.safety.request(op,args or {})
        # Replies also carry authoritative state changes, even without an event.
        self.received(dict(event='snapshot'))
        return result
    async def dispatch(self,client_id,request):
        op=request['op'];args=request.get('args',{})
        if op=='observe':return self.snapshot_for(client_id)
        if self.clients.get(client_id)=='helper' and op not in ('stop','stop_disconnect'):raise ValueError('Helper may Stop only')
        if op=='discover':
            if not self.safety.available:await self.safety.open()
            return await self.request('discover')
        if type(request.get('generation')) is not int or request['generation']!=self.generation:raise ValueError('Obsolete connection generation')
        if op=='connect':
            if args.get('recover') is True:
                if not self.safety.available:await self.safety.open()
                if self.claimant not in (None,client_id):raise ValueError('Recovery already claimed')
                self.claimant=client_id;self.claimed_at=self.clock();return self.snapshot_for(client_id)
            self.connecting=True
            try:
                await self.request('connect',{'device_id':args['device_id']});await self.publish_readiness()
                if self.safety.snapshot.get('fault_id'):
                    self.claimant=client_id;self.claimed_at=self.clock()
                else:await self.request('acquire',dict(owner_id=client_id,owner_kind=self.clients[client_id]))
                return {'generation':self.generation,'recovery':bool(self.safety.snapshot.get('fault_id'))}
            finally:self.connecting=False
        if op in ('stop','stop_disconnect'):
            result=await self.request(op);return {'confirmed':result.get('confirmed',False)}
        owner=self.safety.snapshot.get('owner_id') if self.safety.snapshot.get('grant_id') else None
        if op=='resolve_session':
            if client_id not in (owner,self.claimant) or not self.recording or self.storage_fault:raise ValueError('Claim recovery or control first')
            await self.recording.submit('resolve',(args['session_id'],args['choice']));await self.publish_readiness()
            return self.snapshot_for(client_id)
        if op=='acknowledge_recovery':
            if self.claimant!=client_id:raise ValueError('Claim recovery first')
            await self.publish_readiness()
            await self.request('recover',dict(**args,owner_id=client_id,owner_kind=self.clients[client_id]))
            self.claimant=None;return self.snapshot_for(client_id)
        if op=='take_control':
            await self.request('acquire',dict(owner_id=client_id,owner_kind=self.clients[client_id]));return self.snapshot_for(client_id)
        if op=='renew' and self.claimant==client_id:
            self.claimed_at=self.clock();return {}
        if owner!=client_id:raise ValueError('Not current motion owner')
        if op=='renew':
            self.renewal_seq+=1;return await self.request('renew',{'renewal_seq':self.renewal_seq})
        if op=='release':return await self.request('release')
        if op not in ('start','pause','set_speed'):raise ValueError('Unknown operation')
        if self.storage_fault or self.tracking_review:raise ValueError('Resolve interrupted tracking first')
        if request['id'] in self.seen or len(self.seen)>=1024:raise ValueError('Duplicate or exhausted motion request')
        self.seen.add(request['id'])
        if op=='start' and self.last:self.record('before_start',self.last)
        return await self.request(op,{'speed':args.get('speed',self.safety.snapshot.get('target_speed',1000))})
    async def client_lost(self,client_id):
        if self.claimant==client_id:self.claimant=None
        if self.owner==client_id and self.safety.available:
            await self.request('owner_lost')
    async def reconnect_safety(self):
        try:
            # Restore observation/health only. No Bluetooth discover/connect,
            # motion grant, record resolution or recovery acknowledgment here.
            await self.safety.open()
            self.received(dict(event='snapshot'))
            await self.collect_safety_evidence()
        except (OSError,ValueError,TimeoutError):
            pass  # Keep motion blocked; retry at a bounded cadence.
        finally:self.reconnect_after=self.clock()+1
    async def tick(self):
        if (not self.initializing and not self.safety.available and self.clock()>=self.reconnect_after
            and (self.reconnect_task is None or self.reconnect_task.done())):
            self.reconnect_task=self.spawn(self.reconnect_safety())
        if self.claimant and self.clock()-self.claimed_at>=6:self.claimant=None
    async def shutdown(self):
        if self.reconnect_task:
            self.reconnect_task.cancel()
            await asyncio.gather(self.reconnect_task,return_exceptions=True)
        if self.owner and self.safety.available:
            try:await self.request('release')
            except ValueError:pass
        await self.safety.close();self.unsubscribe()
        for t in list(self.tasks):t.cancel()
        await asyncio.gather(*list(self.tasks),return_exceptions=True)
        if self.recording:
            self.record('interrupt','Bridge shut down; continuity needs review');await self.recording.close()
