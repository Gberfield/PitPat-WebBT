import asyncio,tempfile,unittest
from pathlib import Path
from bridge import safety_client
from bridge.safety_core import SafetyCore
from bridge.safety_ipc import SafetyServer
from bridge.backends import SimulatorBackend
class ClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_attach_is_observer_and_health_is_independent_of_motion(self):
        self.assertTrue(hasattr(safety_client,'SafetyClient'),'application safety client missing')
        with tempfile.TemporaryDirectory() as d:
            server=SafetyServer(SafetyCore(SimulatorBackend()),Path(d)/'s')
            await server.serve();client=safety_client.SafetyClient(server.runtime,'application')
            try:
                await client.open();await asyncio.sleep(.05)
                self.assertTrue(server.core.health.healthy)
                self.assertIsNone(server.core.grant_id)
                self.assertFalse(server.core.connected)
                devices=await client.request('discover',{})
                self.assertEqual(devices['devices'][0]['id'],'simulator-ba09')
            finally:await client.close();await server.close()

    async def test_concurrent_opens_share_one_authorized_connection(self):
        with tempfile.TemporaryDirectory() as d:
            server=SafetyServer(SafetyCore(SimulatorBackend()),Path(d)/'s')
            await server.serve();client=safety_client.SafetyClient(server.runtime,'application')
            try:
                await asyncio.gather(client.open(),client.open(),client.open())
                await asyncio.sleep(.05)
                self.assertTrue(client.available)
                self.assertTrue(server.core.health.healthy)
                self.assertIsNone(server.core.grant_id)
                self.assertFalse(server.core.connected)
            finally:await client.close();await server.close()
