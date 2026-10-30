import asyncio
import unittest
from unittest.mock import patch

from bridge.control_core import Controller
from bridge.protocol import encode_command


def report(speed=0, state=3):
    packet = bytearray(31)
    packet[0:2] = b'\x67\x1f'
    packet[3:5] = speed.to_bytes(2, 'big')
    packet[26] = (24, 8, 16, 0)[state]
    for b in packet[1:-2]: packet[-2] ^= b
    packet[-1] = 0x43
    return bytes(packet)


class FakeBackend:
    def __init__(self):
        self.writes = []
        self.disconnects = 0
        self.gate = None
        self.write_gate = None
        self.fail = False

    async def discover(self, timeout):
        return [{'id': 'synthetic', 'name': 'Test treadmill'}]

    async def connect(self, device_id, on_packet, on_lost):
        self.packet, self.lost = on_packet, on_lost
        if self.gate: await self.gate.wait()

    async def write(self, packet):
        self.writes.append(packet)
        if self.fail: raise OSError('synthetic failure')
        if self.write_gate: await self.write_gate.wait()

    async def disconnect(self):
        self.disconnects += 1


class ControllerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.now = 0
        self.backend = FakeBackend()
        self.controller = Controller(self.backend, clock=lambda: self.now)
        self.serial = 0
        self.events = []
        self.controller.subscribe(self.events.append)
        await self.call('discover')
        await self.call('connect', {'device_id': 'synthetic'})
        self.backend.packet(report())
        await self.flush()
        self.backend.writes.clear()

    async def asyncTearDown(self):
        # Do not run production shutdown (which legitimately waits for hardware).
        for task in list(self.controller.tasks): task.cancel()
        await asyncio.gather(*self.controller.tasks, return_exceptions=True)

    async def flush(self):
        for _ in range(20): await asyncio.sleep(0)

    async def call(self, op, args=None, owner='one', request_id=None, generation=None):
        self.serial += 1
        return await self.controller.dispatch(owner, dict(v=1, id=request_id or str(self.serial), op=op,
            generation=self.controller.generation if generation is None else generation, args=args or {}))

    async def test_single_owner_and_bounds(self):
        with self.assertRaises(ValueError): await self.call('start', owner='two')
        for speed in (999, 6001, True, 1050, '1000'):
            with self.assertRaises(ValueError): await self.call('set_speed', {'speed': speed})
        self.assertEqual(self.backend.writes, [])
        await self.call('set_speed', {'speed': 6000})
        self.assertEqual(self.backend.writes, [encode_command('set_speed', 6000)])

    async def test_duplicate_or_old_motion_never_replays(self):
        await self.call('start', request_id='same')
        with self.assertRaises(ValueError): await self.call('start', request_id='same')
        with self.assertRaises(ValueError): await self.call('start', generation=0)
        self.assertEqual(len(self.backend.writes), 1)

    async def test_obsolete_connection_request_cannot_reclaim_controller(self):
        self.backend.fail = True
        await self.controller.client_lost('one')
        with self.assertRaises(ValueError):
            await self.call('connect', {'recover':True}, owner='two', generation=0)
        self.assertIsNone(self.controller.owner)

    async def test_stop_requires_write_and_new_zero_report(self):
        self.backend.write_gate = asyncio.Event()
        task = asyncio.create_task(self.call('stop'))
        await self.flush()
        self.backend.packet(report(1000, 3))
        await self.flush(); self.assertFalse(task.done())
        self.backend.packet(report())
        await self.flush(); self.assertFalse(task.done())
        self.backend.write_gate.set()
        result = await task
        self.assertTrue(result['confirmed'])
        self.assertEqual(self.backend.disconnects, 0)

    async def test_stop_disconnect_waits_for_confirmation(self):
        task = asyncio.create_task(self.call('stop_disconnect'))
        await self.flush(); self.assertEqual(self.backend.disconnects, 0)
        self.backend.packet(report())
        self.assertTrue((await task)['confirmed'])
        self.assertEqual(self.backend.disconnects, 1)
        self.assertIsNone(self.controller.owner)

    async def test_hung_stop_is_unconfirmed_and_keeps_link(self):
        self.backend.write_gate = asyncio.Event()
        with patch('bridge.control_core.STOP_TIMEOUT', 0.02):
            result = await self.call('stop_disconnect')
        self.assertFalse(result['confirmed'])
        self.assertEqual(self.backend.disconnects, 0)
        with self.assertRaises(ValueError): await self.call('start')

    async def test_failed_write_is_unconfirmed(self):
        self.backend.fail = True
        self.assertFalse((await self.call('stop'))['confirmed'])
        self.assertEqual(self.backend.disconnects, 0)

    async def test_failed_motion_write_blocks_further_motion(self):
        self.backend.fail = True
        with self.assertRaises(ValueError): await self.call('start')
        self.backend.fail = False
        with self.assertRaises(ValueError): await self.call('start')

    async def test_lease_expiry_requests_stop_without_disconnect(self):
        self.now = 6
        task = asyncio.create_task(self.controller.tick())
        await self.flush()
        self.assertEqual(self.backend.writes, [encode_command('stop')])
        self.assertEqual(self.backend.disconnects, 0)
        self.backend.packet(report())
        await task
        self.assertEqual(self.backend.disconnects, 1)

    async def test_orphan_recovery_blocks_motion(self):
        self.backend.fail = True
        await self.controller.client_lost('one')
        self.assertIsNone(self.controller.owner)
        self.assertEqual(self.backend.disconnects, 0)
        self.backend.fail = False
        with self.assertRaises(ValueError): await self.call('connect', {'device_id': 'synthetic'}, owner='two')
        await self.call('connect', {'recover': True}, owner='two')
        with self.assertRaises(ValueError): await self.call('start', owner='two')
        self.backend.packet(report())
        await self.flush()
        await self.call('start', owner='two')
        self.assertEqual(self.backend.writes[-1], encode_command('start'))

    async def test_late_connect_after_owner_loss(self):
        # Use an independent controller to hold establishment at the BLE boundary.
        backend = FakeBackend(); backend.gate = asyncio.Event()
        controller = Controller(backend)
        await controller.dispatch('x', dict(v=1, id='d', op='discover', generation=0, args={}))
        connect = asyncio.create_task(controller.dispatch('x', dict(v=1,id='c',op='connect',generation=0,args={'device_id':'synthetic'})))
        await self.flush()
        await controller.client_lost('x')
        backend.gate.set()
        await self.flush()
        self.assertIn(encode_command('stop'), backend.writes)
        backend.packet(report())
        await connect
        self.assertEqual(backend.disconnects, 1)

    async def test_first_report_during_subscription_is_not_lost(self):
        class ImmediateBackend(FakeBackend):
            async def connect(self, device_id, on_packet, on_lost):
                await super().connect(device_id, on_packet, on_lost)
                on_packet(report())
        self.backend = ImmediateBackend()
        self.controller = Controller(self.backend)
        await self.call('discover')
        await self.call('connect', {'device_id':'synthetic'})
        await self.call('start')
        self.assertIn(encode_command('start'), self.backend.writes)

    async def test_recovery_cannot_take_over_while_browser_loss_is_stopping(self):
        task = asyncio.create_task(self.controller.client_lost('one'))
        await self.flush()
        with self.assertRaises(ValueError): await self.call('connect', {'recover':True}, owner='two')
        self.backend.packet(report())
        await task

    async def test_invalid_and_stale_telemetry_block_motion(self):
        self.backend.packet(b'bad')
        with self.assertRaises(ValueError): await self.call('start')
        self.now = 5
        task = asyncio.create_task(self.controller.tick())
        await self.flush(); self.assertIn(encode_command('stop'), self.backend.writes)
        self.backend.packet(report())
        await task

    async def test_old_notifications_and_link_loss_never_enable_motion(self):
        packet = self.backend.packet
        self.backend.lost()
        packet(report())
        with self.assertRaises(ValueError): await self.call('start')
        self.assertEqual(self.backend.writes, [])

    async def test_stop_cancels_queued_motion(self):
        self.backend.write_gate = asyncio.Event()
        first = asyncio.create_task(self.call('set_speed', {'speed': 2000}))
        await self.flush()
        queued = asyncio.create_task(self.call('start'))
        stop = asyncio.create_task(self.call('stop'))
        await self.flush(); self.backend.write_gate.set()
        await first
        with self.assertRaises(ValueError): await queued
        await self.flush(); self.backend.packet(report()); await stop
        self.assertEqual([p for p in self.backend.writes if len(p) == 23],
                         [encode_command('set_speed', 2000), encode_command('stop')])

class OwnershipTests(unittest.IsolatedAsyncioTestCase):
    call = ControllerTests.call
    flush = ControllerTests.flush
    asyncTearDown = ControllerTests.asyncTearDown
    async def asyncSetUp(self):
        await ControllerTests.asyncSetUp(self)
        self.controller.register_client('one', 'browser')
        self.controller.register_client('two', 'tray')
        self.controller.register_client('helper', 'helper')

    async def test_observer_cannot_move_or_renew_and_loss_is_harmless(self):
        view = await self.call('observe', owner='two')
        self.assertFalse(view['is_owner'])
        self.assertEqual(view['owner_kind'], 'browser')
        for op in ('start','pause','set_speed','renew'):
            with self.assertRaises(ValueError): await self.call(op, owner='two')
        await self.controller.client_lost('two')
        self.assertEqual(self.controller.owner, 'one')
        self.assertEqual(self.backend.writes, [])

    async def test_transfer_cancels_old_motion_and_renewals(self):
        old = self.controller.generation
        await self.controller.lock.acquire()
        queued = asyncio.create_task(self.call('start', generation=old))
        await self.flush()
        transferred = await self.call('take_control', owner='two')
        self.assertTrue(transferred['is_owner'])
        self.assertEqual(transferred['target_speed'],1000)
        self.assertGreater(self.controller.generation, old)
        self.controller.lock.release()
        with self.assertRaises(ValueError): await queued
        with self.assertRaises(ValueError): await self.call('renew', generation=old)
        self.assertNotIn(encode_command('start'), self.backend.writes)
        # Original BLE callback must still work after control generation changes.
        self.backend.packet(report(1000,1))
        self.assertEqual(self.controller.last.speed_raw,1000)
        await self.call('set_speed', {'speed':2000}, owner='two')
        self.assertIn(encode_command('set_speed',2000), self.backend.writes)

    async def test_transfer_requires_fresh_confirmed_stop_and_no_fault(self):
        for speed,state in [(1000,1),(0,2),(0,0),(1000,3)]:
            self.backend.packet(report(speed,state))
            with self.assertRaises(ValueError): await self.call('take_control', owner='two')
        self.backend.packet(report())
        self.now = 5
        with self.assertRaises(ValueError): await self.call('take_control', owner='two')
        self.now = 0
        self.controller.recovery=True
        with self.assertRaises(ValueError): await self.call('take_control', owner='two')
        self.controller.recovery=False
        self.controller.storage_fault='disk full'
        with self.assertRaises(ValueError): await self.call('take_control', owner='two')
        self.controller.storage_fault=None
        with self.assertRaises(ValueError): await self.call('take_control', owner='helper')

    async def test_global_helper_stop_never_acquires_motion(self):
        stop = asyncio.create_task(self.call('stop', owner='helper'))
        await self.flush()
        self.backend.packet(report())
        self.assertTrue((await stop)['confirmed'])
        self.assertEqual(self.controller.owner,'one')
        with self.assertRaises(ValueError): await self.call('start', owner='helper')

    async def test_owner_loss_stops_even_when_observers_remain(self):
        await self.call('observe',owner='two')
        lost = asyncio.create_task(self.controller.client_lost('one'))
        await self.flush()
        self.backend.packet(report())
        await lost
        self.assertFalse(self.controller.connected)
        self.assertIn(encode_command('stop'), self.backend.writes)
