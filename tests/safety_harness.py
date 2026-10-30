"""Synthetic process fixtures. The plant lives outside both child processes."""
import asyncio,contextlib,json,os,signal,socket,subprocess,sys,tempfile,time
from pathlib import Path
from aiohttp import ClientSession
from tests.test_bridge_controller import report

class Plant:
    def __init__(self):self.speed=0;self.state=3;self.writes=[];self.tasks=set();self.writers=set()
    async def accept(self,r,w):
        self.writers.add(w)
        async def emit():
            while True:
                w.write((json.dumps({'packet':report(self.speed,self.state).hex()})+'\n').encode());await w.drain();await asyncio.sleep(.05)
        t=asyncio.create_task(emit());self.tasks.add(t)
        try:
            while raw:=await r.readline():
                m=json.loads(raw);p=bytes.fromhex(m['write']);self.writes.append(p)
                if len(p)==23:
                    if p[12] in (0,2):self.speed=0;self.state=3 if p[12]==0 else 2
                    else:self.speed=int.from_bytes(p[6:8],'big');self.state=1
                w.write((json.dumps({'id':m['id']})+'\n').encode());await w.drain()
        except (OSError,ConnectionError):pass
        finally:
            t.cancel();await asyncio.gather(t,return_exceptions=True);self.tasks.discard(t)
            w.close();self.writers.discard(w)
    async def close(self):
        for w in list(self.writers):w.close()
        for t in list(self.tasks):t.cancel()
        await asyncio.gather(*list(self.tasks),return_exceptions=True)

class ProcessPairFixture:
    def __init__(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='pitpat-fault-');self.root=Path(self.tmp.name)
        self.runtime=self.root/'runtime';self.plant=Plant();self.application=None;self.safety=None
        self.children=[];self.logs=[];self.session=None;self.ws=None;self.serial=0;self.generation=0
    async def start(self):
        self.server=await asyncio.start_unix_server(self.plant.accept,path=str(self.root/'plant.sock'))
        self.safety=self.child(['-m','tests.safety_process_fixture','--runtime-dir',str(self.runtime),'--plant-socket',str(self.root/'plant.sock')])
        await self.until(lambda:(self.runtime/'safety.sock').exists(),3)
        with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        self.origin=f'http://127.0.0.1:{port}'
        self.application=self.child(['-m','bridge','--simulate','--port',str(port),'--runtime-dir',str(self.runtime),'--state-dir',str(self.root/'state')])
        await self.until(lambda:(self.runtime/'control.sock').exists(),4)
        self.session=ClientSession()
        async with self.session.get(self.origin+'/api/bootstrap') as response:info=await response.json()
        self.ws=await self.session.ws_connect(self.origin+'/api/ws',origin=self.origin)
        await self.ws.send_json(dict(v=1,op='authorize',token=info['token']))
        hello=await self.ws.receive_json();self.generation=hello['generation']
    def child(self,args):
        log=open(self.root/f'child-{len(self.children)}.log','w+');self.logs.append(log)
        env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]))
        proc=subprocess.Popen([sys.executable,'-u',*args],cwd=Path(__file__).resolve().parents[1],env=env,stdout=log,stderr=log)
        self.children.append(proc);return proc
    async def until(self,predicate,seconds):
        end=time.monotonic()+seconds
        while not predicate():
            if time.monotonic()>=end:
                for log in self.logs:log.flush();log.seek(0);print(log.read()[-2500:])
                raise AssertionError('Synthetic process condition timed out')
            await asyncio.sleep(.02)
    async def app_request(self,op,args=None):
        self.serial+=1;key=str(self.serial)
        # Refresh generation without consuming arbitrary queued old responses.
        if op!='observe':
            view=await self.app_request('observe');self.generation=view['generation']
        await self.ws.send_json(dict(v=1,id=key,op=op,generation=self.generation,args=args or {}))
        while True:
            m=await asyncio.wait_for(self.ws.receive_json(),8)
            self.generation=m.get('generation',self.generation)
            if m.get('id')==key:
                if not m.get('ok'):raise ValueError(m.get('error'))
                return m.get('result')
    async def start_minimum(self):
        devices=(await self.app_request('discover'))['devices']
        await self.app_request('connect',{'device_id':devices[0]['id']})
        await self.app_request('start',{'speed':1000});await self.until(lambda:self.plant.speed==1000,1)
    async def snapshot(self):
        r,w=await asyncio.open_unix_connection(str(self.runtime/'safety.sock'))
        w.write(b'{"v":1,"op":"hello","kind":"helper"}\n');await w.drain()
        try:return json.loads(await asyncio.wait_for(r.readline(),1))['snapshot']
        finally:w.close();await w.wait_closed()
    async def until_stopped(self,timeout):await self.until(lambda:self.plant.speed==0,timeout)
    async def kill_application(self):self.application.kill();await asyncio.to_thread(self.application.wait,2)
    async def freeze_application(self):self.application.send_signal(signal.SIGSTOP)
    async def resume_application(self):self.application.send_signal(signal.SIGCONT)
    async def kill_safety(self):self.safety.kill();await asyncio.to_thread(self.safety.wait,2)
    async def freeze_safety(self):self.safety.send_signal(signal.SIGSTOP)
    async def close(self):
        # Only our Popen children; no native desktop, systemd unit or hardware.
        for p in self.children:
            if p.poll() is None:p.send_signal(signal.SIGCONT)
        if self.ws:await self.ws.close()
        if self.session:await self.session.close()
        for p in reversed(self.children):
            if p.poll() is None:p.terminate()
        for p in self.children:
            if p.poll() is None:
                try:await asyncio.to_thread(p.wait,7)
                except subprocess.TimeoutExpired:p.kill();await asyncio.to_thread(p.wait,2)
        if hasattr(self,'server'):self.server.close();await self.server.wait_closed()
        await self.plant.close()
        for log in self.logs:log.close()
        self.tmp.cleanup()
