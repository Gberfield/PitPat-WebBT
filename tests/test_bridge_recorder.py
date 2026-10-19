"""Literal cumulative-counter fixtures catch double counting and reset data loss."""
import asyncio
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from bridge.recorder import Recorder, RecordingWorker
from bridge.store import WalkStore
from bridge.protocol import Telemetry, encode_command
from bridge.control_core import Controller
from tests.test_bridge_controller import FakeBackend, report


def sample(state=1, duration=600000, steps=1000, distance=500, calories=30, speed=2000):
    return Telemetry(speed if state == 1 else 0, state, 1, distance, steps, calories, duration, b'')


class RecorderTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = WalkStore(Path(self.temp.name) / 'state' / 'walks.sqlite3')
        self.now = 10000
        self.rec = Recorder(self.store, clock_ms=lambda: self.now)

    async def asyncTearDown(self): self.temp.cleanup()

    async def test_two_cumulative_walks_and_pause_resume(self):
        self.rec.before_start(sample(3, 0, 0, 0, 0))
        await self.rec.observe(sample())
        sid = self.rec.snapshot()['sessionId']
        await self.rec.observe(sample(2))
        await self.rec.observe(sample())
        self.assertEqual(self.rec.snapshot()['sessionId'], sid)
        await self.rec.observe(sample(3))
        self.assertIsNone(self.rec.snapshot())
        self.rec.before_start(sample(3))
        await self.rec.observe(sample(1, 660000, 1100, 600, 35))
        await self.rec.observe(sample(3, 660000, 1100, 600, 35))
        rows = self.store.page(50, None)['walks']
        self.assertEqual(len(rows), 2)
        by_id = {r['sessionId']: r for r in rows}
        self.assertEqual(by_id[sid]['duration'], 600)
        second = next(r for r in rows if r['sessionId'] != sid)
        self.assertEqual((second['duration'], second['steps'], second['calories']), (60, 100, '5 Cal'))
        self.assertAlmostEqual(second['distanceMiles'], 0.1)
        self.assertEqual(second['coverage'], 'complete')
        self.assertEqual(by_id[sid]['speedCount'], 2)
        self.assertAlmostEqual(by_id[sid]['avgSpeed'], 2)

    async def test_countdown_stop_does_not_count_walk(self):
        self.rec.before_start(sample(3, 0, 0, 0, 0))
        await self.rec.observe(sample(0, 0, 0, 0, 0))
        await self.rec.observe(sample(3, 0, 0, 0, 0))
        self.assertEqual(self.store.page(50, None)['walks'], [])

    async def test_resets_preserve_nonzero_totals_and_mark_partial(self):
        await self.rec.observe(sample())
        self.assertEqual(self.rec.snapshot()['coverage'], 'partial')
        await self.rec.observe(sample(1, 10000, 10, 10, 1))
        self.assertEqual(self.rec.snapshot()['duration'], 610)
        await self.rec.observe(sample(3, 0, 0, 0, 0))
        row = self.store.page(50, None)['walks'][0]
        self.assertEqual((row['duration'], row['steps'], row['status']), (610, 1010, 'completed'))
        self.assertEqual(row['coverage'], 'partial')

    async def test_restart_and_explicit_continuity_choices_preserve_evidence(self):
        await self.rec.observe(sample())
        sid = self.rec.snapshot()['sessionId']
        rec = Recorder(self.store, clock_ms=lambda: self.now)
        await rec.initialize()
        self.assertEqual(rec.snapshot()['status'], 'interrupted')
        await rec.observe(sample(1, 660000, 1100, 600, 35))
        self.assertEqual(rec.snapshot()['duration'], 600)
        with self.assertRaises(ValueError): await rec.resolve('wrong', 'continue')
        await rec.resolve(sid, 'continue')
        await rec.observe(sample(1, 660000, 1100, 600, 35))
        self.assertEqual((rec.snapshot()['sessionId'], rec.snapshot()['duration']), (sid, 660))
        await rec.interrupt('Link lost')
        await rec.resolve(sid, 'new')
        await rec.observe(sample(1, 720000, 1200, 700, 40))
        self.assertNotEqual(rec.snapshot()['sessionId'], sid)
        self.assertEqual(rec.snapshot()['duration'], 60)
        self.assertEqual(len(self.store.page(50, None)['walks']), 2)
        self.assertEqual(self.store.page(50, None)['walks'][1]['coverage'], 'partial')

    async def test_failed_commit_does_not_publish_saved_completion(self):
        updates, faults = [], []
        worker = RecordingWorker(self.rec, faults.append, updates.append)
        worker.offer('observe', sample())
        await worker.drain()
        saved = self.store.current()
        with patch.object(self.store, 'save', side_effect=OSError('disk full')):
            worker.offer('observe', sample(3))
            await worker.drain()
        self.assertEqual(len(faults), 1)
        self.assertEqual(self.store.current(), saved)
        self.assertFalse(any(u and u['status'] == 'completed' for u in updates))
        self.assertFalse(worker.offer('observe', sample()))
        await worker.close()

    async def test_queue_overflow_faults_once_without_blocking(self):
        faults = []
        worker = RecordingWorker(self.rec, faults.append, lambda _: None)
        for _ in range(256): self.assertTrue(worker.offer('observe', sample()))
        self.assertFalse(worker.offer('observe', sample()))
        self.assertEqual(len(faults), 1)
        await worker.close()

    async def test_stalled_commit_does_not_block_stop(self):
        backend = FakeBackend()
        ctrl = Controller(backend, recorder=self.rec)
        await ctrl.dispatch('one', dict(op='discover'))
        await ctrl.dispatch('one', dict(op='connect', generation=0, args={'device_id': 'synthetic'}))
        backend.packet(report())
        await ctrl.recording.drain()
        gate, entered = threading.Event(), threading.Event()
        original = self.store.save
        def stalled(*args, **kwargs):
            entered.set(); gate.wait(3); return original(*args, **kwargs)
        try:
            with patch.object(self.store, 'save', stalled):
                backend.packet(report(2000, 1))
                self.assertTrue(await asyncio.to_thread(entered.wait, 1))
                stop = asyncio.create_task(ctrl.stop())
                for _ in range(40): await asyncio.sleep(0)
                self.assertIn(encode_command('stop'), backend.writes)
                backend.packet(report())
                self.assertTrue(await asyncio.wait_for(stop, 1))
                self.assertFalse(gate.is_set())
        finally:
            gate.set()
            await ctrl.recording.drain()
            await ctrl.disconnect()
            await ctrl.shutdown()

    async def test_controller_storage_failure_blocks_motion_but_keeps_stop(self):
        backend = FakeBackend()
        ctrl = Controller(backend, recorder=self.rec)
        events = []; ctrl.subscribe(events.append)
        await ctrl.dispatch('one', dict(op='discover'))
        await ctrl.dispatch('one', dict(op='connect', generation=0, args={'device_id':'synthetic'}))
        backend.packet(report())
        await ctrl.recording.drain()
        try:
            with patch.object(self.store, 'save', side_effect=OSError('full')):
                backend.packet(report(1000, 1))
                await ctrl.recording.drain()
            for _ in range(40): await asyncio.sleep(0)
            backend.packet(report())
            for _ in range(40): await asyncio.sleep(0)
            self.assertTrue(ctrl.blocked)
            self.assertTrue(any(e['event'] == 'storage_fault' for e in events))
            self.assertIn(encode_command('stop'), backend.writes)
            with self.assertRaises(ValueError):
                await ctrl.dispatch('one', dict(op='start', id='no', generation=ctrl.generation))
            self.assertEqual(self.store.page(50,None)['walks'], [])
        finally:
            await ctrl.disconnect(); await ctrl.shutdown()

    async def test_single_counter_reset_does_not_double_other_counters(self):
        await self.rec.observe(sample())
        await self.rec.observe(sample(1, 10000, 1010, 510, 31))
        row = self.rec.snapshot()
        self.assertEqual((row['duration'], row['steps'], row['calories']), (610,1010,'31 Cal'))
        self.assertAlmostEqual(row['distanceMiles'], .51)

    async def test_two_views_receive_one_canonical_walk(self):
        backend=FakeBackend(); ctrl=Controller(backend, recorder=self.rec)
        first,second=[],[]; ctrl.subscribe(first.append); ctrl.subscribe(second.append)
        ctrl.register_client('one','tray'); ctrl.register_client('two','browser')
        await ctrl.dispatch('one',dict(op='discover'))
        await ctrl.dispatch('one',dict(op='connect',generation=0,args={'device_id':'synthetic'}))
        backend.packet(report()); await ctrl.recording.drain()
        await ctrl.dispatch('one',dict(op='start',generation=ctrl.generation,id='start'))
        backend.packet(report(1000,1)); await ctrl.recording.drain()
        sid=ctrl.snapshot_for('one')['session']['sessionId']
        observer=await ctrl.dispatch('two',dict(op='observe'))
        self.assertEqual(observer['session']['sessionId'],sid)
        backend.packet(report()); await ctrl.recording.drain()
        self.assertEqual(len(self.store.page(50,None)['walks']),1)
        self.assertEqual(self.store.page(50,None)['walks'][0]['coverage'],'complete')
        self.assertEqual([e for e in first if e['event']=='walk'],[e for e in second if e['event']=='walk'])
        await ctrl.disconnect(); await ctrl.shutdown()

    async def test_stale_telemetry_marks_source_gap_and_requires_tracking_choice(self):
        backend=FakeBackend();now=[0]
        ctrl=Controller(backend,clock=lambda:now[0],recorder=self.rec)
        await ctrl.dispatch('one',dict(op='discover'))
        await ctrl.dispatch('one',dict(op='connect',generation=0,args={'device_id':'synthetic'}))
        backend.packet(report(1000,1));await ctrl.recording.drain()
        now[0]=5
        tick=asyncio.create_task(ctrl.tick())
        try:
            for _ in range(40):await asyncio.sleep(0)
            backend.packet(report());await tick;await ctrl.recording.drain()
            row=self.store.page(50,None)['walks'][0]
            self.assertEqual(row['status'],'interrupted')
            self.assertEqual(row['coverage'],'partial')
            with self.assertRaises(ValueError):
                await ctrl.dispatch('one',dict(op='start',generation=ctrl.generation,id='gap-start'))
        finally:await ctrl.disconnect();await ctrl.shutdown()

    async def test_first_running_reset_after_start_uses_new_counter_segment(self):
        self.rec.before_start(sample(3))
        await self.rec.observe(sample(1,60000,100,100,5))
        row=self.rec.snapshot()
        self.assertEqual((row['duration'],row['steps'],row['calories']),(60,100,'5 Cal'))
        self.assertEqual(row['coverage'],'partial')

class SafetyEvidenceTests(RecorderTests):
    async def test_fault_evidence_does_not_double_count_or_complete_walk(self):
        self.assertTrue(hasattr(self.rec,'safety_evidence'),'safety evidence reconciliation missing')
        await self.rec.observe(sample());before=self.rec.snapshot()
        snapshot={'safety_id':'s','link_epoch':1,'fault_id':'f','fault':{'reason':'bridge crashed'},'telemetry_seq':8,'ring_overflow':True}
        await self.rec.safety_evidence(snapshot,[{'seq':8,'hex':'00'}])
        after=self.rec.snapshot()
        self.assertEqual(after['sessionId'],before['sessionId'])
        self.assertEqual(after['duration'],600);self.assertEqual(after['status'],'interrupted')
        self.assertEqual(after['safetyEvidence']['fault_id'],'f')
    async def test_continue_record_waits_for_new_start_not_zero_telemetry(self):
        await self.rec.observe(sample())
        await self.rec.interrupt('watchdog')
        sid=self.rec.snapshot()['sessionId']
        await self.rec.resolve(sid,'continue')
        await self.rec.observe(sample(3))
        self.assertIsNotNone(self.rec.snapshot(),'Continue choice was completed before the next Start')
        self.assertEqual(self.rec.snapshot()['sessionId'],sid)
