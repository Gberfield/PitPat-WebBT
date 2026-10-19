"""BA09-B wire format. All measurements retain device units."""
from dataclasses import dataclass

SERVICE_UUID = '0000fba0-0000-1000-8000-00805f9b34fb'
NOTIFY_UUID = '0000fba2-0000-1000-8000-00805f9b34fb'
WRITE_UUID = '0000fba1-0000-1000-8000-00805f9b34fb'
HEARTBEAT = bytes.fromhex('6a05fdf843')


@dataclass(frozen=True)
class Telemetry:
    speed_raw: int
    state: int
    unit_mode: int
    distance: int
    steps: int
    calories: int
    duration: int
    packet: bytes

    @property
    def stopped(self):
        return self.state == 3 and self.speed_raw == 0


def parse_telemetry(packet: bytes) -> Telemetry:
    if not 31 <= len(packet) <= 255:
        raise ValueError('Invalid telemetry size')
    checksum = 0
    for value in packet[1:-2]:
        checksum ^= value
    if (packet[0] != 0x67 and not (packet[0] == 0x66 and len(packet) == 53)
            or packet[1] != len(packet) or packet[-1] != 0x43 or packet[-2] != checksum):
        raise ValueError('Invalid telemetry framing')
    flags = packet[26]
    u = lambda offset, size: int.from_bytes(packet[offset:offset + size], 'big')
    return Telemetry(u(3, 2), {24: 0, 8: 1, 16: 2, 0: 3}[flags & 24],
                     int(bool(flags & 128)), u(7, 4), u(14, 4), u(18, 2), u(20, 4), bytes(packet))


def encode_command(op: str, speed: int = 1000) -> bytes:
    if op not in ('start', 'pause', 'stop', 'set_speed'):
        raise ValueError('Unknown command')
    if type(speed) is not int or not 1000 <= speed <= 6000 or speed % 100:
        raise ValueError('Speed must be 1000–6000 in steps of 100')
    packet = bytearray(23)
    packet[0:2] = bytes([0x6a, 23])
    packet[6:8] = speed.to_bytes(2, 'big')
    packet[8] = 5 if op == 'set_speed' else 1
    packet[10] = 80
    packet[12] = 0 if op == 'stop' else 2 if op == 'pause' else 4
    packet[13:21] = (58965456623).to_bytes(8, 'big')
    for value in packet[1:21]:
        packet[21] ^= value
    packet[22] = 0x43
    return bytes(packet)
