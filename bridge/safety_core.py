"""Sole Bluetooth authority. The application cannot clear a safety latch implicitly."""
import asyncio
from collections import deque
import secrets
import json
from .control_core import Controller as StopKernel, CommandCancelled
from .protocol import parse_telemetry,encode_command,HEARTBEAT
from .safety_health import HealthMonitor,boot_seconds,OWNER_TIMEOUT,TELEMETRY_TIMEOUT
from .safety_messages import Authority

class SafetyCore(StopKernel):
    def __init__(self,backend,*,clock=boot_seconds):
        super().__init__(backend,clock=clock)
        self.writer_uncertain=False;self.confirmation_proof=None
        self.safety_id=secrets.token_hex(16);self.health=HealthMonitor(clock)
        self.fault_id=None;self.fault_generation=0;self.fault=None
        self.grant_id=None;self.owner_id=None;self.owner_kind=None
        self.command_seq=-1;self.motion_count=0;self.renewal_seq=-1;self.last_renewal=None
        self.recording_ready=False;self.readiness_revision=-1
        self.stop_confirmation_id=None;self.confirmed_at=None
        self.telemetry_seq=0;self.ring=deque(maxlen=256);self.ring_overflow=False
        self.link_state='disconnected';self.motion_pending=False;self.closing=False
    def snapshot(self):
        stale=self.last_valid is None or self.clock()-self.last_valid>=TELEMETRY_TIMEOUT
        state='fault-latched' if self.fault_id else ('stopping' if self.stop_task and not self.stop_task.done() else 'ready' if self.grant_id else 'unarmed')
        return dict(revision=self.sequence,safety_id=self.safety_id,link_epoch=self.link_epoch,fault_generation=self.fault_generation,
            fault_id=self.fault_id,fault=self.fault,link_state=self.link_state,authorization_state=state,
            bridge_healthy=self.health.healthy and not self.health.expired(),owner_id=self.owner_id,owner_kind=self.owner_kind,
            grant_id=self.grant_id,target_speed=self.target_speed,telemetry_seq=self.telemetry_seq,
            telemetry_hex=self.last.packet.hex() if self.last else None,stale=stale,
            writer_uncertain=self.writer_uncertain,stop_confirmation_id=self.stop_confirmation_id,stop_outcome='stopped_confirmed' if self.stop_confirmation_id else 'unconfirmed',
            recording_ready=self.recording_ready,ring_first_seq=self.ring[0]['seq'] if self.ring else 0,
            ring_last_seq=self.telemetry_seq,ring_overflow=self.ring_overflow,connected=self.connected,
            stopping=bool(self.stop_task and not self.stop_task.done()))
    def emit(self,event,**data):
        if not hasattr(self,'safety_id'):return
        if self.writer_uncertain and event=='safety':
            data.update(confirmed=False,message='Stop unconfirmed; a prior motion write may still complete. Use the physical stop control.')
        self.sequence+=1
        message=dict(v=1,event=event,seq=self.sequence,snapshot=self.snapshot(),data=data)
        for callback in tuple(self.subscribers):
            try:callback(message)
            except Exception:self.subscribers.discard(callback)
    def attach_application(self,bridge_id):
        self.health.attach(bridge_id);self.readiness_revision=-1;self.recording_ready=False
    def detach_application(self,bridge_id):
        if self.health.bridge_id!=bridge_id:return
        self.health.detach();self.readiness_revision=-1;self.recording_ready=False
        if self.connected or self.connecting:self.trip('Application connection lost')
    def accept_health(self,frame):
        if self.health.expired() and (self.connected or self.connecting):self.trip('Application health expired')
        return self.health.accept_health(frame)
    def trip(self,reason):
        new_fault=not self.fault_id
        if new_fault:
            self.fault_generation+=1;self.fault_id=secrets.token_hex(16)
            self.fault=dict(id=self.fault_id,reason=reason,telemetry_seq=self.telemetry_seq,stop_outcome='unconfirmed')
        self.grant_id=None;self.owner_id=None;self.owner_kind=None;self.recording_ready=False
        self.blocked=self.recovery=True;self.motion_generation+=1
        if new_fault:self.emit('fault',message=reason+'; motion blocked. Use the physical stop if needed.')
        if new_fault and self.connected and not self.closing and not (self.stop_task and not self.stop_task.done()):
            self.spawn(self.stop(reason,latch=False))
    async def discover(self):
        if self.connected or self.connecting or self.scanning:raise ValueError('Finish current connection first')
        self.scanning=True
        try:
            found=await asyncio.wait_for(self.backend.discover(5),6)
            self.devices={d['id']:d for d in found[:32]};return list(self.devices.values())
        finally:self.scanning=False
    async def connect_device(self,device_id):
        if self.connected or self.connecting:raise ValueError('Already connected or connecting')
        if device_id not in self.devices:raise ValueError('Select a discovered device')
        self.link_epoch+=1;self.generation+=1;epoch=self.link_epoch
        self.connecting=True;self.link_state='connecting';self.last=None;self.last_valid=None
        early=[]
        def packet(raw):
            if self.connected:self.receive_packet(bytes(raw),epoch)
            else:early[:]=[bytes(raw)]
        try:
            await asyncio.wait_for(self.backend.connect(device_id,packet,lambda:self.lose_link(epoch)),20)
            if epoch!=self.link_epoch:raise ValueError('Link lost during connect')
            self.connected=True;self.writer_uncertain=False;self.last_valid=self.clock();self.link_state='connected'
            self.blocked=True;self.initial_report=True
            for raw in early:self.receive_packet(raw,epoch)
            result=await self.stop('Initial connection verification',latch=False)
            if result['outcome']!='stopped_confirmed':self.trip('Initial Stop unconfirmed')
            return result
        except BaseException:
            self.connected=False;self.link_state='lost';self.trip('Connection failed')
            try:await asyncio.wait_for(self.backend.disconnect(),3)
            except Exception:pass
            raise
        finally:self.connecting=False
    def receive_packet(self,packet,link_epoch):self.packet(packet,link_epoch)
    def packet(self,packet,epoch):
        if not self.connected or epoch!=self.link_epoch:return
        try:report=parse_telemetry(packet)
        except ValueError:
            self.trip('Invalid treadmill telemetry');return
        if not report.stopped:self.stop_confirmation_id=None;self.confirmed_at=None
        self.telemetry_seq+=1
        if len(self.ring)==self.ring.maxlen:self.ring_overflow=True
        self.ring.append(dict(seq=self.telemetry_seq,link_epoch=epoch,hex=packet.hex()))
        super().packet(packet,epoch)
        self.blocked=bool(self.fault_id) or not bool(self.grant_id)
    async def write(self,packet,generation,motion=None,before_write=None):
        from . import control_core
        async with self.lock:
            if not self.connected or generation!=self.generation:raise CommandCancelled('Bluetooth connection lost')
            if motion is not None and (motion!=self.motion_generation or self.blocked):raise CommandCancelled('Queued motion cancelled')
            if before_write:before_write()
            try:await asyncio.wait_for(self.backend.write(packet),control_core.STOP_TIMEOUT)
            except BaseException:
                if len(packet)==23 and packet[12]!=0:self.writer_uncertain=True
                raise

    async def heartbeat(self,generation):
        try:
            if self.stop_task and not self.stop_task.done() and self.stop_min_sequence is None:return
            await self.write(HEARTBEAT,generation)
        except Exception:
            if self.connected and generation==self.generation:self.trip('Bluetooth heartbeat write failed')
        finally:self.heartbeat_pending=False
    async def stop(self,reason='user',*,latch=False):
        if latch:self.trip(reason)
        if not (self.stop_task and not self.stop_task.done()):
            self.stop_confirmation_id=None;self.confirmed_at=None
        confirmed=await super().stop()
        confirmed=confirmed and not self.writer_uncertain
        if confirmed:
            proof=(self.link_epoch,self.stop_min_sequence)
            if proof!=self.confirmation_proof or self.stop_confirmation_id is None:
                self.stop_confirmation_id=secrets.token_hex(16);self.confirmed_at=self.clock();self.confirmation_proof=proof
        else:
            if not self.fault_id:
                # Do not recursively retry an unconfirmed Stop.
                self.fault_generation+=1;self.fault_id=secrets.token_hex(16)
                self.fault=dict(id=self.fault_id,reason=reason,telemetry_seq=self.telemetry_seq)
            self.grant_id=None;self.owner_id=None;self.owner_kind=None;self.recording_ready=False
        self.blocked=bool(self.fault_id) or not bool(self.grant_id)
        self.recovery=bool(self.fault_id)
        outcome='stopped_confirmed' if confirmed else 'unconfirmed'
        if self.fault:self.fault['stop_outcome']=outcome
        self.emit('safety',confirmed=confirmed,message='Treadmill reported stopped with zero speed.' if confirmed else 'Stop unconfirmed. Use the physical stop control.' + (' Prior motion write may still complete; power-cycle the stopped treadmill before recovery.' if self.writer_uncertain else ''))
        return dict(outcome=outcome,confirmed=confirmed,stop_confirmation_id=self.stop_confirmation_id)
    async def disconnect_confirmed(self):
        if not (self.stop_confirmation_id and self.last and self.last.stopped and self.last_valid is not None and self.clock()-self.last_valid<5):return False
        await super().disconnect();self.link_state='disconnected';self.grant_id=None;self.owner_id=None;self.owner_kind=None
        self.emit('state',state='disconnected');return True
    def lose_link(self,link_epoch):self.lost(link_epoch)
    def lost(self,epoch):
        if epoch!=self.link_epoch:return
        super().lost(epoch);self.link_state='lost';self.stop_confirmation_id=None
        self.trip('Bluetooth lost; belt state unknown')
    def evidence(self,after_seq,limit):
        result=dict(samples=[],snapshot=self.snapshot(),next_seq=after_seq)
        for item in self.ring:
            if item['seq']<=after_seq:continue
            result['samples'].append(dict(item))
            if len(json.dumps(result))>12000:
                result['samples'].pop();break
            result['next_seq']=item['seq']
            if len(result['samples'])>=limit:break
        return result
    def authority(self):
        return Authority(self.safety_id,self.link_epoch,self.fault_generation,self.health.bridge_id,self.grant_id,self.command_seq+1)
    def check_authority(self,a,*,motion=False):
        if isinstance(a,dict):a=Authority(**a)
        if (a.safety_id!=self.safety_id or a.link_epoch!=self.link_epoch or a.fault_generation!=self.fault_generation or a.bridge_id!=self.health.bridge_id):raise ValueError('Obsolete safety authority')
        if motion:
            if self.health.expired() or not self.health.healthy:self.trip('Application health expired')
            if self.grant_id and self.clock()-self.renewed>=OWNER_TIMEOUT:self.trip('Controller lease expired')
            if self.last_valid is None or self.clock()-self.last_valid>=5:self.trip('Telemetry expired')
            if (not self.grant_id or a.grant_id!=self.grant_id or self.fault_id or not self.recording_ready or not self.connected
                or self.stop_task and not self.stop_task.done()):raise ValueError('Motion blocked; explicit recovery required')
            if a.command_seq<=self.command_seq:raise ValueError('Duplicate/out-of-order motion')
        return a
    def grant(self,args):
        self.grant_id=secrets.token_hex(16);self.owner_id=args['owner_id'];self.owner_kind=args['owner_kind']
        self.target_speed=1000;self.renewed=self.clock();self.last_renewal=None;self.renewal_seq=-1;self.command_seq=-1;self.motion_count=0
        self.blocked=self.recovery=False;self.motion_generation+=1;self.emit('state',state='ready')
        return self.snapshot()
    async def handle_application(self,op,authority,args):
        if self.closing and op not in ('observe','evidence','stop'):raise ValueError('Safety shutting down')
        a=self.check_authority(authority)
        if op=='observe':return self.snapshot()
        if op=='evidence':return self.evidence(args['after_seq'],args['limit'])
        if op=='discover':return {'devices':await self.discover()}
        if op=='connect':return await self.connect_device(args['device_id'])
        if op=='owner_lost':
            if a.grant_id!=self.grant_id:raise ValueError('Not current owner')
            self.trip('Motion controller connection lost')
            return await self.stop('Motion controller connection lost')
        if op in ('stop','stop_disconnect','release'):
            if op=='release' and a.grant_id!=self.grant_id:raise ValueError('Not current grant')
            result=await self.stop(op)
            if result['confirmed'] and op!='stop':await self.disconnect_confirmed()
            return result
        if op=='recording_ready':
            if args['revision']<=self.readiness_revision or args['fault_id']!=self.fault_id:raise ValueError('Obsolete recording readiness')
            self.readiness_revision=args['revision'];self.recording_ready=args['ready']
            if not args['ready'] and self.connected:self.trip('Walk recording unavailable')
            return self.snapshot()
        if op in ('acquire','recover'):
            healthy=not self.motion_pending and not self.connecting and not self.writer_uncertain and self.connected and self.health.healthy and not self.health.expired() and self.last and self.last.stopped and self.last_valid is not None and self.clock()-self.last_valid<5 and self.recording_ready and not (self.stop_task and not self.stop_task.done())
            if not healthy:raise ValueError('Require healthy stopped connection and recording readiness')
            if op=='acquire':
                if self.fault_id:raise ValueError('Explicit fault recovery required')
            else:
                if (not self.fault_id or args['fault_id']!=self.fault_id or args['stop_confirmation_id']!=self.stop_confirmation_id or self.confirmed_at is None or self.clock()-self.confirmed_at>=5):raise ValueError('Require fresh Stop confirmation for current fault')
                self.fault_id=None;self.fault=None
            return self.grant(args)
        if op=='renew':
            self.check_authority(a,motion=True)
            if args['renewal_seq']<=self.renewal_seq:raise ValueError('Old renewal')
            if self.last_renewal is not None and self.clock()-self.last_renewal<1:
                self.command_seq=a.command_seq
                return {'renewed':False}
            self.renewal_seq=args['renewal_seq'];self.last_renewal=self.renewed=self.clock();self.command_seq=a.command_seq
            return {'renewed':True}
        if op not in ('start','pause','set_speed'):raise ValueError('Unknown operation')
        self.check_authority(a,motion=True)
        if self.motion_count>=1024:self.trip('Controller request limit');raise ValueError('Reacquire control')
        if self.motion_pending:raise ValueError('Motion writer busy')
        self.motion_count+=1;self.motion_pending=True;self.command_seq=a.command_seq;epoch=self.motion_generation
        def before():
            self.check_authority(a) # command sequence is already consumed; recheck all live gates below.
            if self.fault_id or self.health.expired() or not self.grant_id or self.clock()-self.renewed>=6 or self.last_valid is None or self.clock()-self.last_valid>=5:raise CommandCancelled('Motion authority expired at writer')
        try:
            await self.write(encode_command(op,args['speed']),self.generation,epoch,before_write=before)
            if op=='set_speed':self.target_speed=args['speed']
            return {'outcome':'written'}
        except CommandCancelled:raise
        except Exception:
            self.trip('Motion command failed or expired');raise
        finally:self.motion_pending=False
    async def tick(self):
        if not (self.connected or self.connecting):return
        if self.health.expired():self.trip('Application health expired')
        elif self.grant_id and self.clock()-self.renewed>=OWNER_TIMEOUT:self.trip('Controller lease expired')
        elif self.last_valid is not None and self.clock()-self.last_valid>=5 and not self.stale_handled:
            self.stale_handled=True;self.trip('Telemetry expired')
    async def close(self):
        self.closing=True
        if self.connected:await self.stop('Safety process shutdown',latch=True)
        for task in list(self.tasks):task.cancel()
        await asyncio.gather(*list(self.tasks),return_exceptions=True)
