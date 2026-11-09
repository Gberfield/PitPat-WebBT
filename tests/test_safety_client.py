import asyncio,tempfile,unittest
from pathlib import Path
from bridge import safety_client
from bridge.safety_core import SafetyCore
from bridge.safety_ipc import SafetyServer
from bridge.backends import SimulatorBackend

class NotificationTests(unittest.TestCase):
    def client(self):
        from unittest.mock import Mock
        client=safety_client.SafetyClient('/unused','app');client.available=True
        client.snapshot=dict(safety_id='s',link_epoch=1,fault_generation=0,grant_id='g')
        client.writer=Mock();client.writer.is_closing.return_value=False
        client.writer.transport.get_write_buffer_size.return_value=0
        return client
    def test_notification_writes_synchronously_and_rejection_fails_closed(self):
        import json
        from bridge.safety_messages import validate_frame
        client=self.client()
        client.notify('recording_review',dict(review=True,revision=1))
        frame=json.loads(client.writer.write.call_args.args[0])
        self.assertEqual(validate_frame(frame,'application')['args'],dict(review=True,revision=1))
        self.assertEqual(len(client.pending),0)
        client.accept(dict(id=frame['id'],ok=False,error='rejected'))
        self.assertFalse(client.available);client.writer.close.assert_called_once()
        self.assertEqual(client.notifications,set())
    def test_failed_notification_send_fails_closed(self):
        client=self.client();client.writer.write.side_effect=OSError('lost')
        with self.assertRaises(OSError):client.notify('recording_review',dict(review=True,revision=1))
        self.assertFalse(client.available);self.assertEqual(client.notifications,set())

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
