import asyncio,json,tempfile,unittest
from pathlib import Path
from bridge import safety_ipc
from bridge.native import RuntimeLock
from bridge.safety_core import SafetyCore
from bridge.backends import SimulatorBackend
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
                await client.request('acquire',{'owner_id':'owner','owner_kind':'browser'})
                await client.request('start',{'speed':1000})
                # Control queue fills synchronously, independent of client's reads.
                for _ in range(80):core.emit('state',state='ready')
                await safety_stop(server.runtime)
                self.assertTrue(core.last.stopped);self.assertIsNotNone(core.fault_id)
                self.assertIsNone(core.grant_id)
            finally:await client.close();await server.close()
