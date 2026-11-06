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

class InterruptedRecordTests(unittest.IsolatedAsyncioTestCase):
    # A walk left open by a bridge restart withholds recording readiness, so Connect gets no
    # grant. With no fault there is no recovery to acknowledge: the tray claims, resolves the
    # record and then takes control. The tray's "Claim control to resolve record" relies on this.
    async def asyncSetUp(self):
        from bridge.recorder import Recorder
        from bridge.store import WalkStore
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        store=WalkStore(root/'state'/'walks.sqlite3')
        store.save(dict(schemaVersion=2,sessionId='left-open',date=1000,startedAt='1970-01-01T00:00:01Z',
                        status='running',coverage='complete',lastObservedAt=2000,duration=1,steps=1,distanceMiles=0,calories='0 Cal'),True)
        self.server=SafetyServer(SafetyCore(SimulatorBackend()),root/'s');await self.server.serve()
        self.facade=Controller(SafetyClient(self.server.runtime,'app'),recorder_factory=lambda:Recorder(store))
        self.facade.register_client('tray','tray');await self.facade.initialize();self.serial=0
    async def asyncTearDown(self):await self.facade.shutdown();await self.server.close();self.tmp.cleanup()
    async def call(self,op,args=None):
        self.serial+=1
        return await self.facade.dispatch('tray',dict(id=str(self.serial),op=op,generation=self.facade.generation,args=args or {}))
    async def test_tray_claims_resolves_and_takes_control_without_a_fault(self):
        devices=await self.call('discover')
        with self.assertRaisesRegex(ValueError,'recording readiness'):await self.call('connect',{'device_id':devices['devices'][0]['id']})
        view=self.facade.snapshot_for('tray')
        self.assertTrue(view['connected']);self.assertFalse(view['owner_present']);self.assertFalse(view['recovery']);self.assertIsNone(view['fault_id'])
        self.assertEqual(view['session']['status'],'interrupted');self.assertFalse(view['can_resolve_session'])
        with self.assertRaises(ValueError):await self.call('resolve_session',{'session_id':'left-open','choice':'new'})
        with self.assertRaises(ValueError):await self.call('take_control')
        await self.call('connect',{'recover':True})
        view=self.facade.snapshot_for('tray')
        self.assertTrue(view['is_recovery_claimant']);self.assertTrue(view['can_resolve_session'])
        await self.call('resolve_session',{'session_id':'left-open','choice':'new'})
        view=self.facade.snapshot_for('tray')
        # No grant yet: the bridge still reports motion blocked, but control can now be taken.
        self.assertIsNone(view['session']);self.assertFalse(view['owner_present']);self.assertTrue(view['blocked'])
        self.assertEqual(view['authorization_state'],'unarmed')
        await self.call('take_control')
        self.assertTrue(self.facade.snapshot_for('tray')['is_owner'])
        self.assertEqual(self.server.core.backend.state,3)
