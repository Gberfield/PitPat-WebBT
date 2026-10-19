import json
import unittest
from pathlib import Path

from bridge.protocol import parse_telemetry, encode_command, HEARTBEAT

FIXTURES = json.loads((Path(__file__).parent / 'fixtures/protocol.json').read_text())


class ProtocolTests(unittest.TestCase):
    def test_shared_reports(self):
        for fixture in FIXTURES:
            with self.subTest(fixture=fixture['name']):
                report = parse_telemetry(bytes.fromhex(fixture['hex']))
                self.assertEqual(report.speed_raw, fixture['speed'])
                self.assertEqual(report.state, fixture['state'])
                self.assertEqual(report.unit_mode, int(fixture['imperial']))
                self.assertEqual(report.steps, 1200)
                self.assertEqual(report.calories, 75)
                self.assertEqual(report.duration, 600000)

    def test_bad_frames_never_supply_state(self):
        good = bytes.fromhex(FIXTURES[0]['hex'])
        for index in (0, 1, 4, -2, -1):
            bad = bytearray(good); bad[index] ^= 1
            with self.assertRaises(ValueError):
                parse_telemetry(bytes(bad))
        for size in range(31):
            with self.assertRaises(ValueError):
                parse_telemetry(good[:size])

    def test_stopped_requires_zero_speed(self):
        report = parse_telemetry(bytes.fromhex(FIXTURES[2]['hex']))
        self.assertEqual(report.state, 3)
        self.assertEqual(report.speed_raw, 1000)
        self.assertFalse(report.stopped)

    def test_command_speed_validation(self):
        for invalid in (999, 6001, 1050, True, '1000', float('nan'), 1000.0):
            with self.assertRaises(ValueError):
                encode_command('start', invalid)
        with self.assertRaises(ValueError):
            encode_command('arbitrary')
        self.assertEqual(encode_command('start', 1000)[12], 4)
        self.assertEqual(encode_command('stop', 6000)[12], 0)
        self.assertEqual(encode_command('pause')[12], 2)
        self.assertEqual(encode_command('set_speed')[8], 5)
        self.assertEqual(encode_command('stop').hex(), '6a170000000003e801005000000000000dba9d76ef1e43')
        self.assertEqual(HEARTBEAT, bytes.fromhex('6a05fdf843'))
