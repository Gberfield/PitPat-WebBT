import asyncio
import enum
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
from bridge import backends
from bridge.protocol import NOTIFY_UUID, SERVICE_UUID, WRITE_UUID

UUID_ID = '9A1C4F2E-6B7D-4E3A-8C21-0F5B9D7E3A10'


class Reason(enum.Enum):
    NO_BLUETOOTH = 1
    NO_BLE_CENTRAL_ROLE = 2
    POWERED_OFF = 3
    DENIED_BY_USER = 4
    DENIED_BY_SYSTEM = 5
    DENIED_BY_UNKNOWN = 6
    UNKNOWN = 7


class NotAvailable(Exception):
    def __init__(self, msg, reason):
        super().__init__(msg, reason)

    @property
    def reason(self): return self.args[1]


def fake_bleak(discover=None, client=None):
    bleak = types.ModuleType('bleak');exc = types.ModuleType('bleak.exc')
    exc.BleakBluetoothNotAvailableError = NotAvailable;exc.BleakBluetoothNotAvailableReason = Reason
    bleak.exc = exc;bleak.BleakScanner = MagicMock(discover=discover or AsyncMock(return_value={}))
    bleak.BleakClient = client or MagicMock()
    return {'bleak': bleak, 'bleak.exc': exc}


def run(coro): return asyncio.run(coro)


class BleakBackendTests(unittest.TestCase):
    def discover_raising(self, reason):
        scan = AsyncMock(side_effect=NotAvailable('synthetic', reason))
        with patch.dict(sys.modules, fake_bleak(scan)):
            return run(backends.BleakBackend().discover(5))

    def test_powered_off_has_fixed_message(self):
        with self.assertRaises(ValueError) as caught:self.discover_raising(Reason.POWERED_OFF)
        self.assertEqual(str(caught.exception), backends.POWERED_OFF)

    def test_every_denial_has_permission_message(self):
        for reason in (Reason.DENIED_BY_USER, Reason.DENIED_BY_SYSTEM, Reason.DENIED_BY_UNKNOWN):
            with self.subTest(reason=reason), self.assertRaises(ValueError) as caught:self.discover_raising(reason)
            self.assertEqual(str(caught.exception), backends.PERMISSION_DENIED)

    def test_other_reasons_keep_bleak_error(self):
        for reason in (Reason.NO_BLUETOOTH, Reason.UNKNOWN):
            with self.subTest(reason=reason), self.assertRaises(NotAvailable):self.discover_raising(reason)

    def test_uuid_address_round_trips_from_discover_to_connect(self):
        device = types.SimpleNamespace(address=UUID_ID, name=None)
        advert = types.SimpleNamespace(service_uuids=[SERVICE_UUID.upper()])
        client = MagicMock(connect=AsyncMock(), start_notify=AsyncMock(), disconnect=AsyncMock())
        client.services.get_characteristic.return_value = object()
        factory = MagicMock(return_value=client)
        with patch.dict(sys.modules, fake_bleak(AsyncMock(return_value={UUID_ID: (device, advert)}), factory)):
            backend = backends.BleakBackend()
            found = run(backend.discover(5))
            self.assertEqual(found, [dict(id=UUID_ID, name='PitPat treadmill')])
            run(backend.connect(found[0]['id'], lambda packet: None, lambda: None))
        self.assertIs(factory.call_args.args[0], device)
        client.services.get_characteristic.assert_called_with(WRITE_UUID)
        self.assertEqual(client.start_notify.call_args.args[0], NOTIFY_UUID)


if __name__ == '__main__':
    unittest.main()
