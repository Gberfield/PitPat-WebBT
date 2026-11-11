import asyncio
import io
import json
import threading
import unittest
from unittest.mock import patch

from bridge.safety_core import SafetyCore
from bridge.backends import SimulatorBackend
from tests.test_bridge_controller import FakeBackend, report
from tests.test_safety_health import Clock


class StopLogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.lines = []
        self.log = patch('bridge.safety_core.stop_log', side_effect=lambda event, **data: self.lines.append(dict(event=event, **data)))
        self.log.start(); self.addCleanup(self.log.stop)
        self.clock = Clock(); self.backend = FakeBackend()
        self.core = SafetyCore(self.backend, clock=self.clock)
        self.core.connected = True; self.core.link_state = 'connected'
        await self.backend.connect('synthetic', lambda raw: self.core.packet(raw, 0), lambda: self.core.lost(0))

    async def asyncTearDown(self):
        for task in list(self.core.tasks): task.cancel()
        await asyncio.gather(*list(self.core.tasks), return_exceptions=True)

    async def flush(self):
        for _ in range(30): await asyncio.sleep(0)

    def events(self, event): return [line for line in self.lines if line['event'] == event]

    async def test_confirmed_and_window(self):
        self.backend.packet(report(1000, 1))
        task = asyncio.create_task(self.core.handle_application('stop', self.core.authority(), {}))
        await self.flush(); self.backend.packet(report())
        self.assertTrue((await task)['confirmed'])
        request = self.events('stop_request')[0]; result = self.events('stop_result')[0]
        self.assertEqual((request['source'], request['state'], request['speed_raw']), ('application', 1, 1000))
        self.assertEqual((result['outcome'], result['state'], result['speed_raw']), ('stopped_confirmed', 3, 0))
        self.assertEqual(request['stop_id'], result['stop_id'])
        self.clock.advance(15); self.backend.packet(report(1000, 3))
        self.assertEqual(len(self.events('stop_report')), 2)
        self.assertEqual(self.events('stop_report')[-1]['speed_raw'], 1000)
        self.clock.advance(.001); self.backend.packet(report())
        self.assertEqual(len(self.events('stop_report')), 2)

    async def test_shared_stop_keeps_one_write_and_logs_both_callers(self):
        first = asyncio.create_task(self.core.stop('first', source='helper'))
        second = asyncio.create_task(self.core.stop('second', source='application'))
        await self.flush(); self.backend.packet(report())
        self.assertTrue((await first)['confirmed']); self.assertTrue((await second)['confirmed'])
        self.assertEqual(len([p for p in self.backend.writes if len(p) == 23]), 1)
        self.assertEqual(len(self.events('stop_request')), 2)
        self.assertEqual(len(self.events('stop_result')), 2)
        self.assertEqual([r['stop_id'] for r in self.events('stop_request')], [r['stop_id'] for r in self.events('stop_result')])

    async def test_write_failure_is_observed_without_retry(self):
        self.backend.write = unittest.mock.AsyncMock(side_effect=OSError('fake writer failed'))
        result = await self.core.stop('write failed')
        self.assertFalse(result['confirmed'])
        self.assertEqual(self.events('stop_result')[0]['unconfirmed_reason'], 'write_failed')
        self.assertEqual(self.backend.write.await_count, 1)

    async def test_timeout_and_window(self):
        with patch('bridge.control_core.STOP_TIMEOUT', .02):
            task = asyncio.create_task(self.core.stop('test timeout'))
            await self.flush(); self.backend.packet(report(1000, 1))
            self.assertFalse((await task)['confirmed'])
        result = self.events('stop_result')[0]
        self.assertEqual(result['unconfirmed_reason'], 'timeout')
        self.assertIsNone(result['state'])
        self.assertEqual(self.events('stop_request')[0]['reason'], 'test timeout')
        self.clock.advance(14.9); self.backend.packet(report())
        self.assertEqual(len(self.events('stop_report')), 2)
        self.clock.advance(.2); self.backend.packet(report())
        self.assertEqual(len(self.events('stop_report')), 2)
        self.assertEqual(len(self.backend.writes), 2)  # Stop and normal heartbeat

    async def test_helper_over_memory_ipc(self):
        from bridge.safety_ipc import SafetyServer
        from tests.test_safety_ipc import MemoryWriter
        import os
        incoming = asyncio.StreamReader(); outgoing = asyncio.StreamReader()
        self.core.backend = SimulatorBackend()
        self.core.backend.on_packet = lambda raw: self.core.packet(raw, 0)
        self.core.attach_application('healthy'); self.core.accept_health(self.core.health.issue_challenge())
        server = SafetyServer(self.core, '/tmp/unused-stop-log')
        with patch('bridge.safety_ipc.peer_uid', return_value=os.getuid()):
            task = asyncio.create_task(server.accept(incoming, MemoryWriter(outgoing)))
            incoming.feed_data(b'{"v":1,"op":"hello","kind":"helper"}\n')
            incoming.feed_data(b'{"v":1,"id":"s","op":"stop","authority":null,"args":{}}\n')
            while True:
                line = json.loads(await asyncio.wait_for(outgoing.readline(), 1))
                if line.get('id') == 's': break
            self.assertTrue(line['result']['confirmed'])
            incoming.feed_eof(); await task
        self.assertEqual(self.events('stop_request')[0]['source'], 'helper')
        self.assertTrue(self.events('stop_result')[0]['confirmed'])
        self.clock.advance(15); self.core.backend.emit()
        self.assertEqual(len(self.events('stop_report')), 2)
        self.clock.advance(.001); self.core.backend.emit()
        self.assertEqual(len(self.events('stop_report')), 2)

    async def test_failed_and_blocked_log_write_preserves_stop(self):
        from bridge.stop_log import StopLog
        entered = threading.Event(); release = threading.Event()
        class Sink:
            def write(self, line):
                entered.set(); release.wait(2); raise OSError('broken stderr')
            def flush(self): raise AssertionError('write failed')
        logger = StopLog(Sink(), capacity=1)
        logger('block'); self.assertTrue(entered.wait(1))
        try:
            with patch('bridge.safety_core.stop_log', logger):
                task = asyncio.create_task(self.core.stop('broken sink'))
                await self.flush(); self.backend.packet(report())
                self.assertTrue((await asyncio.wait_for(task, .5))['confirmed'])
                from bridge.protocol import encode_command
                self.assertEqual([p for p in self.backend.writes if len(p) == 23], [encode_command('stop')])
        finally: release.set()
        logger.queue.join()

    async def test_fault_and_recovery(self):
        self.core.trip('synthetic trip'); await self.flush(); self.backend.packet(report()); await self.flush()
        fault_id = self.core.fault_id
        self.assertEqual(self.events('fault_trip')[0]['id'], fault_id)
        self.core.attach_application('app'); self.core.accept_health(self.core.health.issue_challenge())
        self.core.recording_ready = True
        await self.core.handle_application('recover', self.core.authority(), dict(fault_id=fault_id,
            stop_confirmation_id=self.core.stop_confirmation_id, owner_id='owner', owner_kind='browser'))
        self.assertEqual(self.events('recovery_ack')[0]['id'], fault_id)
        self.assertEqual(self.events('recovery_ack')[0]['reason'], 'synthetic trip')

    async def test_writer_uncertain(self):
        self.core.writer_uncertain = True
        task = asyncio.create_task(self.core.stop('uncertain'))
        await self.flush(); self.backend.packet(report())
        self.assertFalse((await task)['confirmed'])
        self.assertEqual(self.events('stop_result')[0]['unconfirmed_reason'], 'writer_uncertain')

    async def test_link_change(self):
        task = asyncio.create_task(self.core.stop('lost'))
        await self.flush(); self.core.lost(0)
        self.assertFalse((await task)['confirmed'])
        self.assertEqual(self.events('stop_result')[0]['unconfirmed_reason'], 'link_change')


class LogSinkTests(unittest.TestCase):
    def test_json_and_failed_write(self):
        from bridge.stop_log import StopLog
        class Sink(io.StringIO):
            fail = True
            def write(self, line):
                if self.fail: self.fail = False; raise OSError('broken stderr')
                return super().write(line)
        sink = Sink(); logger = StopLog(sink)
        logger('discarded'); logger('stop_request', reason='line\nbreak')
        logger.queue.join()
        data = json.loads(sink.getvalue())
        self.assertEqual(data['event'], 'stop_request')
        self.assertTrue(data['timestamp'].endswith('Z'))
        self.assertEqual(len(sink.getvalue().splitlines()), 1)

    def test_blocked_sink_never_blocks_stop(self):
        from bridge.stop_log import StopLog
        entered = threading.Event(); release = threading.Event()
        class Sink:
            def write(self, line): entered.set(); release.wait(2)
            def flush(self): pass
        logger = StopLog(Sink(), capacity=1)
        logger('blocked'); self.assertTrue(entered.wait(1))
        try:
            logger('queued')
            for _ in range(10): logger('overflow')
        finally: release.set()
        logger.queue.join()
