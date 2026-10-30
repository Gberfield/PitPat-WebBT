"""Application-side safety IPC; health runs on the command event loop."""
import asyncio,contextlib,json
from pathlib import Path
from .messages import load_json
from .safety_messages import Authority,MAX_FRAME
from .safety_health import boot_seconds
from .platform_paths import check_socket_path

class SafetyClient:
    def __init__(self,runtime_dir,bridge_id):
        self.runtime=Path(runtime_dir);self.bridge_id=bridge_id;self.snapshot={};self.writer=None
        self.serial=0;self.command_seq=0;self.grant_id=None;self.pending={};self.listeners=set();self.reader_task=None;self.watch_task=None
        self.last_received=0;self.available=False;self.seq=-1;self.open_lock=asyncio.Lock()
    def subscribe(self,callback):self.listeners.add(callback);return lambda:self.listeners.discard(callback)
    def emit(self,message):
        for c in tuple(self.listeners):
            try:c(message)
            except Exception:self.listeners.discard(c)
    def accept(self,message):
        s=message.get('snapshot')
        if s and (s.get('safety_id')!=self.snapshot.get('safety_id') or s.get('revision',0)>=self.snapshot.get('revision',0)):self.snapshot=s
        if message.get('event')=='challenge':
            # This callback shares the application's command/HTTP event loop.
            self.send(dict(v=1,op='health',**{k:message[k] for k in ('safety_id','bridge_id','challenge_seq','nonce')}))
        elif message.get('id'):
            future=self.pending.get(message['id'])
            if future and not future.done():
                if message.get('ok'):future.set_result(message.get('result'))
                else:future.set_exception(ValueError(message.get('error','Safety request failed')))
        else:self.emit(message)
    async def open(self):
        async with self.open_lock:
            deadline=boot_seconds()+3
            while True:
                try:return await asyncio.wait_for(self.open_once(),max(.001,deadline-boot_seconds()))
                except (FileNotFoundError,ConnectionRefusedError):
                    if boot_seconds()>=deadline:raise ValueError('Safety process unavailable') from None
                    await asyncio.sleep(.05)

    async def open_once(self):
        if self.available:return
        if self.writer:await self.close()
        self.reader,self.writer=await asyncio.wait_for(asyncio.open_unix_connection(str(check_socket_path(self.runtime/'safety.sock')),limit=MAX_FRAME*4),3)
        self.send(dict(v=1,op='hello',kind='application',bridge_id=self.bridge_id))
        hello=load_json(await asyncio.wait_for(self.reader.readline(),3))
        if hello.get('event')!='authorized':raise ValueError('Safety authorization failed')
        self.available=True;self.last_received=boot_seconds();self.accept(hello)
        self.reader_task=asyncio.create_task(self.read());self.watch_task=asyncio.create_task(self.watch())
    def send(self,message):
        if not self.writer or self.writer.is_closing():raise ValueError('Safety unavailable')
        raw=(json.dumps(message,allow_nan=False)+'\n').encode()
        if len(raw)>MAX_FRAME:raise ValueError('Safety message too large')
        self.writer.write(raw)
        if self.writer.transport.get_write_buffer_size()>MAX_FRAME*8:raise ValueError('Safety output stalled')
    async def read(self):
        try:
            while raw:=await self.reader.readline():
                if len(raw)>MAX_FRAME:raise ValueError('Oversized safety response')
                self.last_received=boot_seconds();self.accept(load_json(raw))
        except (OSError,ValueError,TypeError,RecursionError,KeyError):pass
        finally:self.unavailable()
    async def watch(self):
        while self.available:
            await asyncio.sleep(.05)
            if boot_seconds()-self.last_received>=2.05:self.unavailable()
    def unavailable(self):
        was=self.available;self.available=False
        if self.writer:self.writer.close()
        for future in self.pending.values():
            if not future.done():future.set_exception(ValueError('Safety connection lost; Stop unconfirmed'))
        if was:self.emit(dict(event='lost',data={'message':'Safety unavailable; belt state unconfirmed. Use the physical stop control.'}))
    async def request(self,op,args,authority=None):
        if not self.available:raise ValueError('Safety unavailable; reconnect explicitly')
        if len(self.pending)>=8 and op!='stop':raise ValueError('Safety application requests full')
        self.serial+=1;key=str(self.serial);s=self.snapshot
        if s.get('grant_id')!=self.grant_id:self.grant_id=s.get('grant_id');self.command_seq=0
        self.command_seq+=1
        a=authority or Authority(s['safety_id'],s['link_epoch'],s['fault_generation'],self.bridge_id,s['grant_id'],self.command_seq)
        future=asyncio.get_running_loop().create_future();self.pending[key]=future
        try:
            self.send(dict(v=1,id=key,op=op,authority=a.json() if isinstance(a,Authority) else a,args=args))
            return await asyncio.wait_for(future,26 if op=='connect' else 8)
        except TimeoutError:
            self.unavailable();raise ValueError('Safety response timed out; Stop unconfirmed') from None
        finally:self.pending.pop(key,None)
    async def close(self):
        self.unavailable()
        for t in (self.reader_task,self.watch_task):
            if t:t.cancel()
        await asyncio.gather(*(t for t in (self.reader_task,self.watch_task) if t),return_exceptions=True)
        if self.writer:
            with contextlib.suppress(OSError):await self.writer.wait_closed()
        self.writer=None
