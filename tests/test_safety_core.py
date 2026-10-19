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
        await self.core.handle_application('acquire',self.core.authority(),{'owner_id':'owner','owner_kind':'browser'})
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
