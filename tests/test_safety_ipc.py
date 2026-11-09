import asyncio,json,tempfile,unittest
from pathlib import Path
from bridge import safety_ipc
from bridge.native import RuntimeLock
from bridge.safety_core import SafetyCore
from bridge.backends import SimulatorBackend

class MemoryWriter:
    # Paired byte streams exercise the real IPC/client loops without an OS socket.
    def __init__(self,reader):self.reader=reader;self.closed=False;self.transport=self
    def write(self,raw):self.reader.feed_data(raw)
    async def drain(self):pass
    def close(self):
        if not self.closed:self.closed=True;self.reader.feed_eof()
    async def wait_closed(self):pass
    def is_closing(self):return self.closed
    def get_extra_info(self,name):return None
    def get_write_buffer_size(self):return 0

class ReviewBacklogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from bridge.safety_client import SafetyClient
        from unittest.mock import patch
        self.tmp=tempfile.TemporaryDirectory();self.core=SafetyCore(SimulatorBackend(),clock=lambda:0)
        self.server=safety_ipc.SafetyServer(self.core,Path(self.tmp.name)/'s')
        self.client=SafetyClient(self.server.runtime,'app');await self.open_connection()
        await self.wait_until(lambda:self.core.health.healthy)
        await self.client.request('discover',{})
        await self.client.request('connect',dict(device_id='simulator-ba09'))
        await self.client.request('recording_ready',dict(ready=True,revision=1,fault_id=None))
        await self.client.request('recording_review',dict(review=False,revision=1))
        await self.client.request('acquire',dict(owner_id='owner',owner_kind='browser'))
        self.gate=asyncio.Event();self.entered=0;self.requests=[];self.motion=None
        original=self.core.handle_application
        async def held_evidence(op,authority,args):
            if op=='evidence':self.entered+=1;await self.gate.wait()
            return await original(op,authority,args)
        self.hold=patch.object(self.core,'handle_application',held_evidence);self.hold.start()
    async def open_connection(self):await self.server.serve();await self.client.open()
    async def asyncTearDown(self):
        self.gate.set()
        if self.core.lock.locked():self.core.lock.release()
        await asyncio.gather(*self.requests,*([self.motion] if self.motion else []),return_exceptions=True)
        self.hold.stop()
        await self.client.close();await self.server.close();self.tmp.cleanup()
    async def wait_until(self,predicate):
        async with asyncio.timeout(1):
            while not predicate():await asyncio.sleep(0)
    async def saturate(self,*,motion=False):
        from bridge.safety_messages import MAX_PENDING
        if motion:
            await self.core.lock.acquire()
            self.motion=asyncio.create_task(self.client.request('set_speed',dict(speed=2000)))
            await self.wait_until(lambda:self.core.motion_pending)
        for _ in range(MAX_PENDING-int(motion)):
            self.requests.append(asyncio.create_task(self.client.request('evidence',dict(after_seq=0,limit=1))))
        await self.wait_until(lambda:self.entered==MAX_PENDING-int(motion))
        self.assertEqual(len(self.client.pending),MAX_PENDING)
    async def notify_review(self,review,revision):
        self.client.notify('recording_review',dict(review=review,revision=revision))
        await self.wait_until(lambda:not self.client.notifications or not self.client.available)
        self.assertTrue(self.client.available);self.assertIsNotNone(self.server.application)
        self.assertEqual(self.core.health.bridge_id,'app');self.assertIsNone(self.core.fault_id)
        self.assertIs(self.core.recording_review,review);self.assertIs(self.client.snapshot['recording_review'],review)
    async def finish_evidence(self):
        self.gate.set()
        for task in self.requests:self.assertIn('samples',await task)
        self.assertTrue(self.client.available);self.assertIsNone(self.core.fault_id)
    async def test_review_true_bypasses_full_backlog_and_cancels_queued_motion(self):
        await self.saturate(motion=True);grant=self.core.grant_id
        await self.notify_review(True,2)
        self.assertEqual(self.core.grant_id,grant);self.assertEqual(self.core.backend.target,1000)
        self.core.lock.release()
        with self.assertRaisesRegex(ValueError,'Queued motion cancelled'):await self.motion
        await self.finish_evidence()
    async def test_review_false_bypasses_full_backlog(self):
        await self.client.request('recording_review',dict(review=True,revision=2))
        await self.saturate();await self.notify_review(False,3);await self.finish_evidence()
    async def test_review_applies_before_next_motion_frame(self):
        self.client.notify('recording_review',dict(review=True,revision=2))
        with self.assertRaisesRegex(ValueError,'review'):await self.client.request('set_speed',dict(speed=2000))
        self.assertTrue(self.client.available);self.assertTrue(self.core.recording_review)
        self.assertIsNone(self.core.fault_id);self.assertEqual(self.core.backend.target,1000)
    async def test_obsolete_review_notification_still_fails_closed_when_saturated(self):
        await self.saturate()
        self.client.notify('recording_review',dict(review=False,revision=1))
        await self.wait_until(lambda:not self.client.available)
        self.assertTrue(self.client.writer.is_closing())
    async def test_ninth_ordinary_request_refused_but_urgent_stop_admitted(self):
        await self.saturate()
        # Bypass the client's own cap to exercise the server's ninth-request check.
        future=asyncio.get_running_loop().create_future();self.client.pending['ninth']=future
        try:
            self.client.send(dict(v=1,id='ninth',op='observe',authority=self.core.authority().json(),args={}))
            with self.assertRaisesRegex(ValueError,'Invalid or excessive safety request'):await asyncio.wait_for(future,1)
        finally:self.client.pending.pop('ninth',None)
        self.assertTrue((await self.client.request('stop',{}))['confirmed'])
        await self.finish_evidence()

class MemoryReviewBacklogTests(ReviewBacklogTests):
    async def open_connection(self):
        from unittest.mock import patch
        import os
        incoming=asyncio.StreamReader();outgoing=asyncio.StreamReader()
        peer=patch('bridge.safety_ipc.peer_uid',return_value=os.getuid());peer.start();self.addCleanup(peer.stop)
        self.accept_task=asyncio.create_task(self.server.accept(incoming,MemoryWriter(outgoing)))
        with patch('bridge.safety_client.asyncio.open_unix_connection',return_value=(outgoing,MemoryWriter(incoming))):
            await self.client.open()

class SafetyIPCTests(unittest.IsolatedAsyncioTestCase):
    async def test_helper_stop_without_application(self):
        self.assertTrue(hasattr(safety_ipc,'SafetyServer'),'safety server missing')
        with tempfile.TemporaryDirectory() as d:
            core=SafetyCore(SimulatorBackend());server=safety_ipc.SafetyServer(core,Path(d)/'runtime')
            await server.serve()
            try:
                r,w=await asyncio.open_unix_connection(str(server.path))
                w.write(b'{"v":1,"op":"hello","kind":"helper"}\n');await w.drain()
                hello=json.loads(await r.readline());self.assertEqual(hello['event'],'authorized')
                w.write(b'{"v":1,"id":"s","op":"stop","authority":null,"args":{}}\n');await w.drain()
                while True:
                    m=json.loads(await r.readline())
                    if m.get('id')=='s':break
                self.assertEqual(m['result']['outcome'],'unconfirmed')
                self.assertIsNone(core.grant_id);w.close();await w.wait_closed()
                self.assertEqual(server.path.stat().st_mode&0o777,0o600)
                with self.assertRaises(ValueError):RuntimeLock(server.runtime)
            finally:await server.close()
    async def test_slow_application_output_cannot_block_direct_helper_stop(self):
        from bridge.safety_client import SafetyClient
        from bridge.desktop import safety_stop
        with tempfile.TemporaryDirectory() as d:
            core=SafetyCore(SimulatorBackend());server=safety_ipc.SafetyServer(core,Path(d)/'runtime');await server.serve()
            client=SafetyClient(server.runtime,'app')
            try:
                await client.open();await asyncio.sleep(.03)
                await client.request('discover',{})
                await client.request('connect',{'device_id':'simulator-ba09'})
                await client.request('recording_ready',{'ready':True,'revision':1,'fault_id':None})
                await client.request('recording_review',{'review':False,'revision':1})
                await client.request('acquire',{'owner_id':'owner','owner_kind':'browser'})
                await client.request('start',{'speed':1000})
                # Control queue fills synchronously, independent of client's reads.
                for _ in range(80):core.emit('state',state='ready')
                await safety_stop(server.runtime)
                self.assertTrue(core.last.stopped);self.assertIsNotNone(core.fault_id)
                self.assertIsNone(core.grant_id)
            finally:await client.close();await server.close()
