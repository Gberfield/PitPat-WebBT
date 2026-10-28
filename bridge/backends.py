"""The only module that can access real Bluetooth; imports Bleak lazily."""
import asyncio

from .protocol import SERVICE_UUID, NOTIFY_UUID, WRITE_UUID

POWERED_OFF = 'Bluetooth is off. Turn it on in Control Center.'
PERMISSION_DENIED = ('Bluetooth permission denied. Allow it in System Settings → Privacy & Security → '
                     'Bluetooth for the app running PitPat.')


class BleakBackend:
    def __init__(self):
        self.devices = {}
        self.client = None

    async def discover(self, timeout):
        from bleak import BleakScanner
        from bleak.exc import BleakBluetoothNotAvailableError, BleakBluetoothNotAvailableReason as Reason
        try:
            found = await BleakScanner.discover(timeout=timeout, return_adv=True, service_uuids=[SERVICE_UUID])
        except BleakBluetoothNotAvailableError as exc:
            if exc.reason == Reason.POWERED_OFF:
                raise ValueError(POWERED_OFF) from None
            if exc.reason in (Reason.DENIED_BY_USER, Reason.DENIED_BY_SYSTEM, Reason.DENIED_BY_UNKNOWN):
                raise ValueError(PERMISSION_DENIED) from None
            raise
        self.devices = {device.address: device for device, advert in found.values()
                        if SERVICE_UUID in [uuid.lower() for uuid in (advert.service_uuids or [])]}
        return [dict(id=key, name=device.name or 'PitPat treadmill') for key, device in self.devices.items()][:32]

    async def connect(self, device_id, on_packet, on_lost):
        from bleak import BleakClient
        if device_id not in self.devices:
            raise ValueError('Unknown device')
        client = BleakClient(self.devices[device_id], disconnected_callback=lambda _: on_lost())
        self.client = client
        try:
            await client.connect()
            # Fail establishment if either fixed characteristic is absent.
            if not client.services.get_characteristic(WRITE_UUID):
                raise ValueError('Write characteristic unavailable')
            await client.start_notify(NOTIFY_UUID, lambda _, packet: on_packet(bytes(packet)))
        except BaseException:
            try:
                await asyncio.wait_for(client.disconnect(), 3)
            except Exception:
                pass
            if self.client is client:
                self.client = None
            raise

    async def write(self, packet):
        if not self.client or not self.client.is_connected:
            raise ConnectionError('Bluetooth unavailable')
        # Equivalent to the existing Web Bluetooth writeValue default when the
        # characteristic advertises write-with-response. Never send unchecked UUIDs.
        characteristic = self.client.services.get_characteristic(WRITE_UUID)
        response = 'write' in characteristic.properties
        await self.client.write_gatt_char(characteristic, packet, response=response)

    async def disconnect(self):
        client, self.client = self.client, None
        if client:
            await client.disconnect()


class SimulatorBackend:
    def __init__(self):
        self.task = None
        self.state = 3
        self.speed = 0
        self.target = 1000
        self.duration = 0
        self.distance = 0
        self.steps = 0
        self.countdown = 0

    async def discover(self, timeout):
        return [dict(id='simulator-ba09', name='SIMULATOR — no physical treadmill')]

    async def connect(self, device_id, on_packet, on_lost):
        if device_id != 'simulator-ba09':
            raise ValueError('Unknown simulator')
        self.on_packet = on_packet
        self.task = asyncio.create_task(self.run())

    async def run(self):
        await asyncio.sleep(0)
        while True:
            self.emit()
            await asyncio.sleep(0.5)
            if self.countdown:
                self.countdown -= 1
                if not self.countdown:
                    self.state, self.speed = 1, self.target
            if self.state == 1:
                self.duration += 500
                self.steps += 1
                self.distance += self.speed / 7200

    def emit(self):
        packet = bytearray(53)
        packet[0:2] = b'\x66\x35'
        packet[3:5] = self.speed.to_bytes(2, 'big')
        packet[7:11] = int(self.distance).to_bytes(4, 'big')
        packet[14:18] = self.steps.to_bytes(4, 'big')
        packet[18:20] = (self.steps // 30).to_bytes(2, 'big')
        packet[20:24] = self.duration.to_bytes(4, 'big')
        packet[26] = (24, 8, 16, 0)[self.state]
        for value in packet[1:-2]: packet[-2] ^= value
        packet[-1] = 0x43
        self.on_packet(bytes(packet))

    async def write(self, packet):
        if len(packet) != 23:
            return  # Notification heartbeat does not itself produce a notification.
        self.target = int.from_bytes(packet[6:8], 'big')
        if packet[12] == 0:
            self.state, self.speed, self.countdown = 3, 0, 0
        elif packet[12] == 2:
            self.state, self.speed, self.countdown = 2, 0, 0
        elif packet[8] == 5:
            if self.state == 1: self.speed = self.target
        else:
            self.state, self.countdown = 0, 6
        self.emit()

    async def disconnect(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)
            self.task = None
