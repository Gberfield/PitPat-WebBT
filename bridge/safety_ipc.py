"""Independent, peer-authenticated safety IPC with reserved Stop capacity."""
import asyncio,contextlib,json,os,stat
from pathlib import Path
from .native import RuntimeLock,peer_uid
from .messages import load_json
from .safety_messages import validate_frame,identifier,MAX_FRAME,MAX_PENDING
from .safety_health import CHALLENGE_INTERVAL,TICK_INTERVAL

class SafetyServer:
    def __init__(self,core,runtime_dir,guard=None):
        self.core=core;self.runtime=Path(runtime_dir);self.path=self.runtime/'safety.sock'
        self.guard=guard;self.server=None;self.tasks=set();self.writers=set();self.application=None
        self.ticker=None;self.inode=None
    async def serve(self):
        if self.guard is None:self.guard=RuntimeLock(self.runtime)
        if self.path.is_symlink():raise ValueError('Unsafe socket')
        if self.path.exists():
            info=self.path.stat()
            if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.getuid():raise ValueError('Invalid socket')
            try:
                r,w=await asyncio.open_unix_connection(str(self.path));w.close();await w.wait_closed()
            except ConnectionRefusedError:self.path.unlink()
            else:raise ValueError('Safety listener already active')
        self.server=await asyncio.start_unix_server(self.accept,path=str(self.path),limit=MAX_FRAME)
        self.path.chmod(0o600);self.inode=self.path.stat().st_ino
        self.ticker=asyncio.create_task(self.run_deadlines())
    async def run_deadlines(self):
        while True:
            await self.core.tick()
            if self.application is not None and self.core.health.expired():self.application.close()
            await asyncio.sleep(TICK_INTERVAL)
    async def accept(self,reader,writer):
        task=asyncio.current_task();self.tasks.add(task);self.writers.add(writer)
        core=self.core;role=None;bridge_id=None;sender=None;challenger=None;unsubscribe=lambda:None
        queue=asyncio.Queue(maxsize=64);latest=None;ready=asyncio.Event();pending=set();stopping=set()
        def send(msg):
            nonlocal latest
            if writer.is_closing():return
            if msg.get('event')=='telemetry':latest=msg
            else:
                try:queue.put_nowait(msg)
                except asyncio.QueueFull:
                    writer.close()
                    if role=='application':core.detach_application(bridge_id)
            ready.set()
        def encoded(msg):
            raw=(json.dumps(msg,allow_nan=False)+'\n').encode()
            if len(raw)>MAX_FRAME:raise ValueError('Oversized safety output')
            return raw
        async def output():
            nonlocal latest
            while True:
                await ready.wait()
                while not queue.empty():
                    msg=queue.get_nowait();writer.write(encoded(msg))
                    await asyncio.wait_for(writer.drain(),.5)
                if latest:
                    msg=latest;latest=None;writer.write(encoded(msg));await asyncio.wait_for(writer.drain(),.5)
                ready.clear()
        async def challenges():
            while True:
                c=core.health.issue_challenge();send(dict(v=1,event='challenge',safety_id=core.safety_id,**c))
                await asyncio.sleep(CHALLENGE_INTERVAL)
        async def command(frame):
            try:
                op=frame['op']
                if role=='helper':
                    if op=='stop':result=await core.stop('Emergency helper')
                    elif op=='evidence':result=core.evidence(**frame['args'])
                    else:result=core.snapshot()
                else:result=await core.handle_application(op,frame['authority'],frame['args'])
                send(dict(v=1,id=frame['id'],ok=True,result=result,error=None,snapshot=core.snapshot()))
            except Exception as exc:
                send(dict(v=1,id=frame['id'],ok=False,result=None,error=str(exc) if isinstance(exc,ValueError) else 'Safety operation failed',snapshot=core.snapshot()))
        try:
            if len(self.writers)>16 or peer_uid(writer.get_extra_info('socket'))!=os.getuid():return
            raw=await asyncio.wait_for(reader.readline(),3);hello=load_json(raw)
            if not isinstance(hello,dict) or type(hello.get('v')) is not int or hello.get('v')!=1 or hello.get('op')!='hello':return
            role=hello.get('kind')
            if role=='application':
                if set(hello)!={'v','op','kind','bridge_id'} or not identifier(hello['bridge_id']) or self.application is not None:return
                bridge_id=hello['bridge_id'];core.attach_application(bridge_id);self.application=writer
            elif role=='helper':
                if set(hello)!={'v','op','kind'}:return
            else:return
            if role=='application' and len(self.writers)>12:return
            send(dict(v=1,event='authorized',snapshot=core.snapshot()))
            sender=asyncio.create_task(output())
            def output_done(t):
                if not t.cancelled() and t.exception():writer.close()
            sender.add_done_callback(output_done)
            unsubscribe=core.subscribe(send)
            if role=='application':challenger=asyncio.create_task(challenges())
            while True:
                raw=await reader.readline()
                await asyncio.sleep(0)
                await core.tick()
                if not raw:break
                if len(raw)>MAX_FRAME:break
                frame=load_json(raw)
                if isinstance(frame,dict) and frame.get('op')=='health':
                    if (role!='application' or set(frame)!={'v','op','safety_id','bridge_id','challenge_seq','nonce'} or type(frame['v']) is not int or frame['v']!=1
                        or type(frame['challenge_seq']) is not int or not isinstance(frame['nonce'],str) or frame['safety_id']!=core.safety_id):break
                    core.accept_health(frame);continue
                try:
                    validate_frame(frame,role)
                    urgent=frame['op']=='stop'
                    if len(pending)>=MAX_PENDING and not urgent:raise ValueError('Safety request backlog full')
                    if urgent and stopping:raise ValueError('Stop already pending')
                except ValueError:
                    send(dict(v=1,id=frame.get('id') if isinstance(frame,dict) else None,ok=False,error='Invalid or excessive safety request',snapshot=core.snapshot()));continue
                t=asyncio.create_task(command(frame));pool=stopping if urgent else pending;pool.add(t);t.add_done_callback(pool.discard)
        except (OSError,ValueError,TypeError,RecursionError,TimeoutError,UnicodeError):pass
        finally:
            if self.application is writer:self.application=None;core.detach_application(bridge_id)
            unsubscribe()
            for t in (sender,challenger):
                if t:t.cancel()
            # Never cancel a late connect/Stop merely because the application died.
            # Authority is already revoked; let bounded safety operations finish.
            await asyncio.gather(*(pending|stopping),*(t for t in (sender,challenger) if t),return_exceptions=True)
            writer.close()
            with contextlib.suppress(OSError):await writer.wait_closed()
            self.writers.discard(writer);self.tasks.discard(task)
    async def close(self):
        if self.server:self.server.close();await self.server.wait_closed()
        if self.ticker:self.ticker.cancel();await asyncio.gather(self.ticker,return_exceptions=True)
        await self.core.close()
        for w in list(self.writers):w.close()
        await asyncio.gather(*list(self.tasks),return_exceptions=True)
        if self.inode and self.path.exists() and self.path.stat().st_ino==self.inode:self.path.unlink()
        if self.guard:self.guard.close();self.guard=None
