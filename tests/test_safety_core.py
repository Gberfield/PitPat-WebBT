import asyncio
import unittest
from bridge import safety_core
from bridge.protocol import encode_command
from tests.test_bridge_controller import FakeBackend,report
from tests.test_safety_health import Clock

class SafetyCoreTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.assertTrue(hasattr(safety_core,'SafetyCore'),'independent safety core missing')
        self.clock=Clock();self.backend=FakeBackend();self.core=safety_core.SafetyCore(self.backend,clock=self.clock)
        self.core.attach_application('app');self.core.accept_health(self.core.health.issue_challenge())
        await self.core.discover()
        task=asyncio.create_task(self.core.connect_device('synthetic'))
        await self.flush();self.backend.packet(report());await self.flush();self.backend.packet(report())
        await task;self.backend.writes.clear()
    async def asyncTearDown(self):
        if hasattr(self,'core'):
            for t in list(self.core.tasks):t.cancel()
            await asyncio.gather(*list(self.core.tasks),return_exceptions=True)
    async def flush(self):
        for _ in range(30):await asyncio.sleep(0)
    def assert_packet_blocked(self,packet,expected,state='ready'):
        events=[];unsubscribe=self.core.subscribe(events.append)
        try:self.backend.packet(packet)
        finally:unsubscribe()
        self.assertIs(self.core.blocked,expected)
        self.assertEqual(events[-1]['event'],'state')
        self.assertEqual(events[-1]['data'],dict(state=state,connected=True,blocked=self.core.blocked))
    async def test_state_block_matches_with_latched_fault(self):
        self.core.trip('test failure');await self.flush();self.backend.packet(report());await self.flush()
        self.assertIsNotNone(self.core.fault_id)
        self.assert_packet_blocked(report(),True)
    async def test_state_block_matches_without_grant(self):
        self.assertIsNone(self.core.grant_id)
        self.assert_packet_blocked(report(),True)
    async def test_state_block_matches_granted_stopped_report(self):
        await self.arm()
        self.assertIsNotNone(self.core.grant_id)
        self.assert_packet_blocked(report(),False)
    async def test_state_block_matches_moving_report_while_stopping(self):
        await self.arm()
        task=asyncio.create_task(self.core.stop('user'));await self.flush()
        self.assertFalse(task.done())
        # A pending Stop blocks at dispatch; the report gate still follows the grant.
        self.assert_packet_blocked(report(1000,1),False,state='stopping')
        self.assertTrue(self.core.recovery)
        self.backend.packet(report());self.assertTrue((await task)['confirmed'])
    async def test_fault_latch_survives_stopped_report(self):
        self.core.trip('test failure');await self.flush();self.backend.packet(report());await self.flush()
        self.assertEqual(self.core.snapshot()['authorization_state'],'fault-latched')
        self.assertIn(encode_command('stop'),self.backend.writes)
    async def test_application_expiry_stops_without_owner_renewal(self):
        self.clock.advance(2.05);await self.core.tick();await self.flush()
        self.assertIn(encode_command('stop'),self.backend.writes)
        self.backend.packet(report());await self.flush()
        self.assertIsNotNone(self.core.snapshot()['fault_id'])
    async def test_write_and_fresh_report_required(self):
        t=asyncio.create_task(self.core.stop('user',latch=False));await self.flush()
        self.backend.packet(report(1000,3));await self.flush();self.assertFalse(t.done())
        self.backend.packet(report());self.assertEqual((await t)['outcome'],'stopped_confirmed')
    async def arm(self):
        a=self.core.authority()
        await self.core.handle_application('recording_ready',a,{'ready':True,'revision':1,'fault_id':None})
        await self.review(False,1)
        await self.core.handle_application('acquire',self.core.authority(),{'owner_id':'owner','owner_kind':'browser'})
    async def review(self,review,revision):
        return await self.core.handle_application('recording_review',self.core.authority(),dict(review=review,revision=revision))
    async def test_review_accepts_stale_link_epoch_and_fault_generation(self):
        from unittest.mock import patch
        revision=0
        for field in ('link_epoch','fault_generation'):
            with self.subTest(field=field):
                authority=self.core.authority();setattr(self.core,field,getattr(self.core,field)+1)
                with patch.object(self.core,'trip',wraps=self.core.trip) as trip,patch.object(self.core,'detach_application',wraps=self.core.detach_application) as detach:
                    for review in (False,True):
                        revision+=1;generation=self.core.motion_generation
                        result=await self.core.handle_application('recording_review',authority.json(),dict(review=review,revision=revision))
                        self.assertIs(result['recording_review'],review)
                        self.assertEqual(self.core.motion_generation,generation+int(review))
                    trip.assert_not_called();detach.assert_not_called()
                self.assertIsNone(self.core.fault_id);self.assertEqual(self.core.health.bridge_id,'app')
                with self.assertRaisesRegex(ValueError,'Obsolete recording review'):
                    await self.core.handle_application('recording_review',authority,dict(review=False,revision=revision))
    async def test_review_rejects_wrong_application_or_safety_identity(self):
        from dataclasses import replace
        for field in ('bridge_id','safety_id'):
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'Obsolete safety authority'):
                await self.core.handle_application('recording_review',replace(self.core.authority(),**{field:'other'}),dict(review=False,revision=1))
        self.assertTrue(self.core.recording_review);self.assertEqual(self.core.review_revision,-1)
        self.assertEqual(self.core.health.bridge_id,'app');self.assertIsNone(self.core.fault_id)
    async def test_other_operations_still_reject_stale_link_and_fault_authority(self):
        from bridge.safety_messages import ARGS
        for field in ('link_epoch','fault_generation'):
            authority=self.core.authority();setattr(self.core,field,getattr(self.core,field)+1)
            for op in ARGS:
                if op=='recording_review':continue
                with self.subTest(field=field,op=op),self.assertRaisesRegex(ValueError,'Obsolete safety authority'):
                    await self.core.handle_application(op,authority,{})
    async def test_review_cancels_queued_motion_without_revoking_authority(self):
        await self.arm();grant=self.core.grant_id
        await self.core.lock.acquire()
        motion=asyncio.create_task(self.core.handle_application('set_speed',self.core.authority(),{'speed':2000}))
        try:
            await self.flush();self.assertTrue(self.core.motion_pending)
            await self.review(True,2)
            # Clearing review before the writer runs must not revive old motion.
            await self.review(False,3)
        finally:self.core.lock.release()
        with self.assertRaises(safety_core.CommandCancelled):await motion
        self.assertEqual([p for p in self.backend.writes if len(p)==23],[]);self.assertEqual(self.core.target_speed,1000)
        self.assertIsNone(self.core.fault_id);self.assertEqual(self.core.grant_id,grant)
        self.assertFalse(self.core.blocked);self.assertFalse(self.core.recovery)
        self.assertFalse(self.core.stop_task and not self.core.stop_task.done())
        await self.core.handle_application('set_speed',self.core.authority(),{'speed':2000})
    async def test_review_blocks_motion_but_allows_renewal_and_stop(self):
        await self.arm();grant=self.core.grant_id
        self.backend.packet(report(1000,1));await self.flush();self.backend.writes.clear()
        renewed=self.core.renewed;last_valid=self.core.last_valid;health=self.core.health.__dict__.copy()
        self.assertTrue((await self.review(True,2))['recording_review'])
        self.assertEqual(self.core.renewed,renewed);self.assertEqual(self.core.last_valid,last_valid)
        self.assertEqual(self.core.health.__dict__,health)
        for op in ('start','pause','set_speed'):
            with self.assertRaisesRegex(ValueError,'review'):await self.core.handle_application(op,self.core.authority(),{'speed':1000})
        await self.core.handle_application('renew',self.core.authority(),{'renewal_seq':1})
        self.assertEqual([p for p in self.backend.writes if len(p)==23],[]);self.assertIsNone(self.core.fault_id)
        self.assertEqual(self.core.grant_id,grant)
        stop=asyncio.create_task(self.core.handle_application('stop',self.core.authority(),{}))
        await self.flush();self.backend.packet(report())
        self.assertTrue((await stop)['confirmed']);self.assertIsNone(self.core.fault_id)
        self.assertEqual(self.core.grant_id,grant)
    async def test_review_does_not_block_acquire_or_explicit_recovery(self):
        await self.core.handle_application('recording_ready',self.core.authority(),dict(ready=True,revision=1,fault_id=None))
        owner=dict(owner_id='owner',owner_kind='browser')
        await self.core.handle_application('acquire',self.core.authority(),owner)
        self.assertTrue(self.core.recording_review);self.assertIsNotNone(self.core.grant_id)
        with self.assertRaisesRegex(ValueError,'review'):await self.core.handle_application('start',self.core.authority(),{'speed':1000})
        self.core.trip('Synthetic fault');await self.flush();self.backend.packet(report());await self.flush()
        await self.core.handle_application('recording_ready',self.core.authority(),dict(ready=True,revision=2,fault_id=self.core.fault_id))
        await self.core.handle_application('recover',self.core.authority(),dict(**owner,fault_id=self.core.fault_id,stop_confirmation_id=self.core.stop_confirmation_id))
        self.assertTrue(self.core.recording_review);self.assertIsNone(self.core.fault_id);self.assertIsNotNone(self.core.grant_id)
    async def test_review_revisions_and_application_reset(self):
        self.assertTrue(self.core.snapshot()['recording_review'])
        await self.review(False,5)
        for revision in (4,5):
            with self.assertRaisesRegex(ValueError,'Obsolete'):await self.review(True,revision)
        self.assertFalse(self.core.recording_review)
        # Disconnect only the application; avoid conflating reset with the existing link-loss fault.
        self.core.connected=False
        self.core.detach_application('other');self.assertFalse(self.core.recording_review)
        self.core.detach_application('app');self.assertTrue(self.core.recording_review)
        self.core.attach_application('next');self.assertTrue(self.core.recording_review)
        await self.review(False,0);self.assertFalse(self.core.recording_review)
    async def test_renewals_do_not_exhaust_motion_command_budget(self):
        from dataclasses import replace
        await self.arm()
        a=replace(self.core.authority(),command_seq=1500)
        try:result=await self.core.handle_application('start',a,{'speed':1000})
        except ValueError as e:self.fail('Health traffic exhausted motion budget: '+str(e))
        self.assertEqual(result['outcome'],'written')
    async def test_early_renewal_adds_no_credit_and_does_not_kill_owner(self):
        await self.arm()
        await self.core.handle_application('renew',self.core.authority(),{'renewal_seq':1})
        self.clock.advance(.999)
        result=await self.core.handle_application('renew',self.core.authority(),{'renewal_seq':2})
        self.assertFalse(result.get('renewed',True))
        self.assertEqual(self.core.renewed,0)
        self.assertIsNotNone(self.core.grant_id)
    async def test_evidence_pages_fit_wire_limit(self):
        import json
        for _ in range(256):self.backend.packet(report())
        page=self.core.evidence(0,256)
        self.assertLess(len(json.dumps(page)),15872)
        self.assertGreater(len(page['samples']),0)
    async def test_motion_after_confirmed_stop_invalidates_confirmation(self):
        self.assertIsNotNone(self.core.stop_confirmation_id)
        self.backend.packet(report(1000,1))
        self.assertIsNone(self.core.stop_confirmation_id)
    async def test_uncertain_late_motion_write_cannot_confirm_stop(self):
        from unittest.mock import patch
        await self.arm()
        self.backend.write_gate=asyncio.Event()
        events=[];self.core.subscribe(events.append)
        with patch('bridge.control_core.STOP_TIMEOUT',.02):
            with self.assertRaises(Exception):
                await self.core.handle_application('start',self.core.authority(),{'speed':1000})
        self.backend.write_gate.set();await self.flush()
        t=asyncio.create_task(self.core.stop('retry'))
        await self.flush();self.backend.packet(report());result=await t
        self.assertEqual(result['outcome'],'unconfirmed')
        self.assertFalse(any(e.get('data',{}).get('confirmed') for e in events))
    async def test_old_grant_and_duplicate_authority_never_write(self):
        await self.arm();a=self.core.authority()
        await self.core.handle_application('pause',a,{'speed':1000})
        writes=len(self.backend.writes)
        with self.assertRaises(ValueError):await self.core.handle_application('start',a,{'speed':1000})
        self.assertEqual(len(self.backend.writes),writes)
        self.core.trip('lost');await self.flush();self.backend.packet(report());await self.flush()
        with self.assertRaises(ValueError):await self.core.handle_application('start',a,{'speed':1000})
    async def test_transfer_cannot_cross_submitted_motion_write(self):
        await self.arm();self.backend.write_gate=asyncio.Event()
        motion=asyncio.create_task(self.core.handle_application('start',self.core.authority(),{'speed':1000}))
        await self.flush()
        try:
            with self.assertRaises(ValueError):
                await self.core.handle_application('acquire',self.core.authority(),{'owner_id':'other','owner_kind':'tray'})
        finally:self.backend.write_gate.set();await motion
