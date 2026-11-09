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
    async def test_initialize_and_reconnect_publish_review_without_acquiring(self):
        self.assertFalse(self.server.core.recording_review)
        await self.facade.safety.close()
        async with asyncio.timeout(1):
            while self.server.application is not None:await asyncio.sleep(.001)
        self.assertTrue(self.server.core.recording_review)
        await self.facade.reconnect_safety()
        self.assertTrue(self.facade.safety.available);self.assertFalse(self.server.core.recording_review)
        self.assertIsNone(self.server.core.grant_id);self.assertIsNotNone(self.server.core.fault_id)

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

class ReviewWriterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from bridge.recorder import Recorder
        from bridge.store import WalkStore
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name)
        self.server=SafetyServer(SafetyCore(SimulatorBackend()),root/'s');await self.server.serve()
        self.facade=Controller(SafetyClient(self.server.runtime,'app'),recorder=Recorder(WalkStore(root/'walks.sqlite3')))
        self.facade.register_client('browser','browser');await self.facade.initialize();self.serial=0
        devices=await self.call('discover');await self.call('connect',{'device_id':devices['devices'][0]['id']})
    async def asyncTearDown(self):await self.facade.shutdown();await self.server.close();self.tmp.cleanup()
    async def call(self,op,args=None):
        self.serial+=1
        return await self.facade.dispatch('browser',dict(id=str(self.serial),op=op,generation=self.facade.generation,args=args or {}))
    async def wait_until(self,predicate):
        async with asyncio.timeout(1):
            while not predicate():await asyncio.sleep(.001)
    async def test_telemetry_gap_cancels_queued_speed_until_record_resolved(self):
        from bridge.protocol import encode_command
        from unittest.mock import patch
        core=self.server.core;backend=core.backend;grant=core.grant_id
        # Inject a running simulator observation, without waiting for its countdown.
        backend.state=1;backend.speed=1000;backend.emit()
        await self.wait_until(lambda:self.facade.session_summary() and self.facade.session_summary()['status']=='running')
        await self.facade.recording.drain()
        with patch.object(backend,'write',wraps=backend.write) as write:
            await core.lock.acquire()
            motion=asyncio.create_task(self.call('set_speed',{'speed':2000}))
            try:
                await self.wait_until(lambda:core.motion_pending)
                core.telemetry_seq+=1;backend.emit() # One missing telemetry sequence on the real IPC stream.
                await self.wait_until(lambda:self.facade.tracking_review)
                await self.facade.recording.drain()
                self.assertEqual(self.facade.session_summary()['status'],'interrupted')
            finally:core.lock.release()
            with self.assertRaisesRegex(ValueError,'Queued motion cancelled'):await motion
            self.assertNotIn(encode_command('set_speed',2000),[c.args[0] for c in write.call_args_list])
            self.assertEqual(backend.speed,1000);self.assertEqual(core.grant_id,grant);self.assertIsNone(core.fault_id)
            with self.assertRaisesRegex(ValueError,'Resolve interrupted tracking'):await self.call('start')
            sid=self.facade.session_summary()['sessionId']
            await self.call('resolve_session',{'session_id':sid,'choice':'continue'})
            self.assertFalse(core.recording_review)
            await self.call('set_speed',{'speed':2000})
            self.assertEqual(backend.speed,2000)

class FakeSafetyClient:
    def __init__(self):
        self.available=True;self.calls=[];self.notifications=[]
        self.snapshot=dict(owner_id='browser',grant_id='grant',authorization_state='ready')
    def subscribe(self,callback):return lambda:None
    async def request(self,op,args):self.calls.append(op);return {}
    def notify(self,op,args):self.calls.append(op);self.notifications.append((op,args))

class RecordingControllerTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from bridge.recorder import Recorder
        from bridge.store import WalkStore
        from tests.test_bridge_recorder import sample
        self.tmp=tempfile.TemporaryDirectory()
        self.rec=Recorder(WalkStore(Path(self.tmp.name)/'walks.sqlite3'))
        await self.rec.observe(sample())
        self.ctrl=await self.make_controller();self.serial=0
        self.ctrl.register_client('browser','browser')
    async def make_controller(self):return Controller(FakeSafetyClient(),recorder=self.rec)
    async def asyncTearDown(self):
        await self.ctrl.recording.close()
        for task in list(self.ctrl.tasks):task.cancel()
        await asyncio.gather(*list(self.ctrl.tasks),return_exceptions=True)
        self.tmp.cleanup()
    async def call(self,op,args=None):
        self.serial+=1
        return await self.ctrl.dispatch('browser',dict(id=str(self.serial),op=op,generation=self.ctrl.generation,args=args or {}))
    async def assert_motion_blocked(self):
        for op in ('start','pause','set_speed'):
            with self.assertRaisesRegex(ValueError,'Resolve interrupted tracking'):await self.call(op,{'speed':1000})
    def interrupt(self,kind):
        payload='Safety telemetry gap; coverage partial' if kind=='interrupt' else ({'fault_id':'synthetic'},[])
        self.assertTrue(self.ctrl.record(kind,payload))
    async def check_queued_interrupt(self,kind,choice):
        # No yield between offer and dispatch: the recording worker has not run.
        self.ctrl.record('before_start',None)
        self.interrupt(kind)
        await self.assert_motion_blocked()
        self.assertEqual(self.rec.snapshot()['status'],'running')
        self.assertEqual(self.ctrl.recording.pending_interrupts,1)
        updates=[];self.ctrl.subscribe(lambda e:updates.append(self.ctrl.tracking_review) if e['event']=='walk' else None)
        await self.ctrl.recording.drain()
        self.assertTrue(all(updates),'An earlier non-interrupted update cleared the queued interrupt')
        await self.assert_motion_blocked()
        await self.call('resolve_session',{'session_id':self.rec.snapshot()['sessionId'],'choice':choice})
        self.assertFalse(self.ctrl.tracking_review)
        self.assertEqual(self.ctrl.recording.pending_interrupts,0)
        await self.call('set_speed',{'speed':1000})
class QueuedInterruptTests(RecordingControllerTestCase):
    async def test_queued_interrupt_blocks_until_continue(self):await self.check_queued_interrupt('interrupt','continue')
    async def test_queued_safety_evidence_blocks_until_new(self):await self.check_queued_interrupt('safety_evidence','new')
    async def test_resolution_cannot_clear_a_later_interrupt(self):
        self.interrupt('interrupt');await self.ctrl.recording.drain()
        sid=self.rec.snapshot()['sessionId'];updates=[]
        self.ctrl.subscribe(lambda e:updates.append((self.rec.snapshot(),self.ctrl.tracking_review,self.ctrl.recording.pending_interrupts,self.ctrl.recording.queue.qsize())) if e['event']=='walk' else None)
        self.ctrl.record('resolve',(sid,'continue'))
        self.interrupt('safety_evidence')
        self.ctrl.record('before_start',None)
        await self.ctrl.recording.drain()
        self.assertEqual(updates[0][0]['status'],'paused');self.assertTrue(updates[0][1]);self.assertEqual(updates[0][2],1)
        await self.assert_motion_blocked()
        # Unrelated work behind a successful resolution must not keep the gate latched.
        updates.clear();self.ctrl.record('resolve',(sid,'new'));self.ctrl.record('before_start',None)
        await self.ctrl.recording.drain()
        self.assertIsNone(updates[0][0]);self.assertFalse(updates[0][1]);self.assertGreater(updates[0][3],0)
        await self.call('set_speed',{'speed':1000})
    async def test_rejected_interrupt_offer_keeps_motion_blocked(self):
        await self.ctrl.recording.close()
        self.assertFalse(self.ctrl.record('interrupt','Closed recorder'))
        await self.assert_motion_blocked()

class ReviewPublicationTests(RecordingControllerTestCase):
    async def test_received_gap_sends_review_before_callback_returns(self):
        from tests.test_bridge_controller import report
        self.ctrl.last_key=('safety',1,1)
        self.ctrl.safety.snapshot.update(safety_id='safety',link_epoch=1,telemetry_seq=3,telemetry_hex=report(1000,1).hex())
        self.ctrl.received(dict(event='telemetry'))
        self.assertEqual(self.ctrl.safety.notifications,[('recording_review',dict(review=True,revision=1))])
        self.assertEqual(self.rec.snapshot()['status'],'running')
        await self.ctrl.recording.drain()
        await self.call('resolve_session',{'session_id':self.rec.snapshot()['sessionId'],'choice':'continue'})
        self.assertFalse(self.ctrl.safety.notifications[-1][1]['review'])
    async def test_readiness_republishes_latched_review_after_unavailable_send(self):
        self.ctrl.safety.available=False;self.interrupt('interrupt')
        self.assertEqual(self.ctrl.safety.notifications,[])
        self.ctrl.safety.available=True;await self.ctrl.publish_readiness()
        self.assertTrue(self.ctrl.safety.notifications[-1][1]['review'])
        self.assertNotIn('recording_ready',self.ctrl.safety.calls)

class KernelQueuedInterruptTests(QueuedInterruptTests):
    async def make_controller(self):
        from bridge.control_core import Controller as KernelController
        from tests.test_bridge_controller import FakeBackend,report
        backend=FakeBackend();ctrl=KernelController(backend,clock=lambda:0,recorder=self.rec)
        await ctrl.dispatch('browser',dict(op='discover'))
        await ctrl.dispatch('browser',dict(op='connect',generation=0,args={'device_id':'synthetic'}))
        backend.packet(report(1000,1));await ctrl.recording.drain()
        return ctrl
    async def test_queued_interrupt_cancels_motion_waiting_for_writer(self):
        from bridge.control_core import CommandCancelled
        from bridge.protocol import encode_command
        for kind in ('interrupt','safety_evidence'):
            with self.subTest(kind=kind):
                await self.ctrl.lock.acquire()
                motion=asyncio.create_task(self.call('set_speed',{'speed':2000}))
                try:
                    for _ in range(20):await asyncio.sleep(0)
                    self.assertFalse(motion.done())
                    self.interrupt(kind);await self.ctrl.recording.drain()
                finally:self.ctrl.lock.release()
                with self.assertRaises(CommandCancelled):await motion
                self.assertNotIn(encode_command('set_speed',2000),self.ctrl.backend.writes)
                await self.call('resolve_session',{'session_id':self.rec.snapshot()['sessionId'],'choice':'continue'})
