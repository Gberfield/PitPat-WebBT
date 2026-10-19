import asyncio,tempfile,unittest
from pathlib import Path
from bridge.controller import Controller
from bridge.safety_client import SafetyClient
from bridge.safety_core import SafetyCore
from bridge.safety_ipc import SafetyServer
from bridge.backends import SimulatorBackend
class FacadeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.server=SafetyServer(SafetyCore(SimulatorBackend()),Path(self.tmp.name)/'s')
        await self.server.serve();self.facade=Controller(SafetyClient(self.server.runtime,'app'))
        self.facade.register_client('browser','browser');await self.facade.initialize();self.serial=0
        devices=await self.call('discover');await self.call('connect',{'device_id':devices['devices'][0]['id']})
    async def asyncTearDown(self):await self.facade.shutdown();await self.server.close();self.tmp.cleanup()
    async def call(self,op,args=None,request_id=None):
        self.serial+=1
        return await self.facade.dispatch('browser',dict(id=request_id or str(self.serial),op=op,generation=self.facade.generation,args=args or {}))
    async def test_production_facade_has_no_ble_writer(self):
        self.assertFalse(hasattr(Controller,'write'),'application still has GATT writer')
    async def test_connect_record_gate_and_explicit_recovery(self):
        self.assertTrue(self.facade.snapshot_for('browser')['is_owner'])
        self.server.core.trip('Synthetic freeze');await asyncio.sleep(.6)
        self.assertTrue(self.facade.snapshot_for('browser')['blocked'])
        await self.call('connect',{'recover':True});await self.call('stop');s=self.facade.snapshot_for('browser')
        await self.call('acknowledge_recovery',{'fault_id':s['fault_id'],'stop_confirmation_id':s['stop_confirmation_id']})
        self.assertTrue(self.facade.snapshot_for('browser')['is_owner']);self.assertEqual(self.server.core.backend.state,3)
    async def test_browser_motion_request_id_cannot_replay(self):
        await self.call('pause',{'speed':1000},request_id='duplicate')
        with self.assertRaises(ValueError):await self.call('pause',{'speed':1000},request_id='duplicate')
    async def test_owner_loss_latches_fault_even_with_live_bridge(self):
        await self.facade.client_lost('browser')
        self.assertIsNotNone(self.server.core.fault_id)
        self.assertIsNone(self.server.core.grant_id)

    async def test_shutdown_cancels_pending_safety_reconnect(self):
        await self.facade.safety.close()
        parked=self.server.path.with_name('parked.sock')
        self.server.path.rename(parked)
        try:
            await self.facade.tick()
            await asyncio.sleep(.01)
            await asyncio.wait_for(self.facade.shutdown(),1)
            self.assertFalse(self.facade.safety.available)
            self.assertIsNone(self.facade.safety.writer)
            self.assertFalse([task for task in self.facade.tasks if not task.done()])
        finally:parked.rename(self.server.path)
