"""Single BLE owner and conservative, telemetry-confirmed stopping."""
import asyncio
import time

from .protocol import parse_telemetry, encode_command, HEARTBEAT

STOP_TIMEOUT = 5


class CommandCancelled(ValueError):
    pass


class Controller:
    def __init__(self, backend, clock=time.monotonic, recorder=None):
        self.backend, self.clock = backend, clock
        self.owner = None
        self.clients = {}
        self.link_epoch = 0
        self.target_speed = 1000
        self.generation = 0
        self.sequence = 0
        self.connected = False
        self.connecting = False
        self.blocked = True
        self.recovery = False
        self.scanning = False
        self.devices = {}
        self.last = None
        self.last_valid = None
        self.renewed = 0
        self.motion_generation = 0
        self.seen = set()
        self.lock = asyncio.Lock()
        self.tasks = set()
        self.subscribers = set()
        self.stop_task = None
        self.stop_report = None
        self.stop_min_sequence = None
        self.heartbeat_pending = False
        self.stale_handled = False
        self.initial_report = True
        self.abandoning = False
        self.tracking_review = False
        self.storage_fault = None
        self.recording = None
        if recorder is not None:
            from .recorder import RecordingWorker
            self.recording = RecordingWorker(recorder, self.recording_failed,
                                             self.recorded)

    def register_client(self, client_id, kind):
        if kind not in ('browser', 'tray', 'helper'):
            raise ValueError('Invalid client kind')
        self.clients[client_id] = kind

    async def unregister_client(self, client_id):
        await self.client_lost(client_id)
        self.clients.pop(client_id, None)

    def snapshot_for(self, client_id):
        stale = self.last_valid is None or self.clock() - self.last_valid >= 5
        pending_stop = bool(self.stop_task and not self.stop_task.done())
        return dict(generation=self.generation, connected=self.connected,
                    metrics={k:getattr(self.last,k) for k in ('speed_raw','state','unit_mode','distance','steps','calories','duration')} if self.last else None,
                    connecting=self.connecting, is_owner=self.owner == client_id,
                    owner_kind=self.clients.get(self.owner), owner_present=self.owner is not None,
                    target_speed=self.target_speed, blocked=self.blocked or bool(self.storage_fault),
                    recovery=self.recovery, storage_fault=self.storage_fault, stale=stale,
                    stopping=pending_stop, telemetry=self.last.packet.hex() if self.last else None,
                    session=self.session_summary())

    def session_summary(self):
        row = self.recording.recorder.snapshot() if self.recording else None
        if row:
            return {k: v for k, v in row.items() if k not in ('speedSamples', 'sourceTelemetry')}
        return None

    def recorded(self, row):
        if row and row['status'] == 'interrupted': self.tracking_review = True
        elif not self.recording.queue.qsize(): self.tracking_review = False
        self.emit('walk', session=self.session_summary())

    def prepare_start(self):
        if not self.record('before_start', self.last):
            raise CommandCancelled('Walk recording unavailable')

    def recording_failed(self, message):
        self.storage_fault = message
        self.blocked = True
        self.motion_generation += 1
        self.emit('storage_fault', message=message)
        if self.connected:
            self.spawn(self.stop())

    def record(self, kind, payload=None):
        if self.recording:
            if kind == 'interrupt': self.tracking_review = True
            return self.recording.offer(kind, payload)
        return True

    def spawn(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    def subscribe(self, callback):
        self.subscribers.add(callback)
        return lambda: self.subscribers.discard(callback)

    def emit(self, event, **data):
        self.sequence += 1
        message = dict(v=1, generation=self.generation, seq=self.sequence, event=event, data=data)
        # Subscribers are nonblocking queue publishers; BLE processing never awaits I/O.
        for callback in tuple(self.subscribers):
            try:
                callback(message)
            except Exception:
                self.subscribers.discard(callback)

    async def dispatch(self, client_id, request):
        op, args = request['op'], request.get('args', {})
        if op == 'observe':
            return self.snapshot_for(client_id)
        if self.clients.get(client_id) == 'helper' and op not in ('stop', 'stop_disconnect'):
            raise ValueError('Helpers may observe or request Stop only')
        if op == 'take_control':
            if type(request.get('generation')) is not int or request['generation'] != self.generation:
                raise ValueError('Obsolete connection generation')
            if (not self.connected or self.connecting or self.abandoning or self.recovery or self.storage_fault
                    or self.stop_task and not self.stop_task.done() or not self.owner
                    or self.last_valid is None or self.clock() - self.last_valid >= 5
                    or not self.last or not self.last.stopped):
                raise ValueError('Take control requires fresh confirmed stopped state without faults')
            self.motion_generation += 1
            self.generation += 1
            self.owner = client_id
            self.renewed = self.clock()
            self.target_speed = 1000
            self.seen.clear()
            self.emit('ownership', owner_kind=self.clients.get(client_id))
            return self.snapshot_for(client_id)
        if op == 'discover':
            if self.owner or self.connected or self.connecting or self.scanning:
                raise ValueError('Controller busy; finish the current connection first')
            self.scanning = True
            try:
                devices = await asyncio.wait_for(self.backend.discover(5), 6)
                self.devices = {d['id']: d for d in devices[:32]}
                return {'devices': list(self.devices.values())}
            finally:
                self.scanning = False
        if op == 'connect':
            if type(request.get('generation')) is not int or request['generation'] != self.generation:
                raise ValueError('Obsolete connection generation; refresh discovery')
            if self.owner or self.connecting or self.abandoning:
                raise ValueError('Controller busy')
            if self.connected:
                if args.get('recover') is not True:
                    raise ValueError('Unconfirmed orphaned connection; explicitly recover Stop control')
                self.owner = client_id
                self.renewed = self.clock()
                self.recovery = self.blocked = True
                self.seen.clear()
                self.emit('state', state='orphaned', connected=True, blocked=True)
                return {'generation': self.generation, 'recovery': True}
            if args.get('device_id') not in self.devices:
                raise ValueError('Select a device from the current discovery')
            self.owner = client_id
            self.renewed = self.clock()
            self.connecting = True
            self.generation += 1
            self.link_epoch += 1
            epoch = self.link_epoch
            generation = self.generation
            self.target_speed = 1000
            self.last = None
            self.last_valid = None
            self.blocked = True
            self.recovery = False
            self.seen.clear()
            early_packet = None
            def receive(packet):
                nonlocal early_packet
                if epoch != self.link_epoch:
                    return
                if self.connected:
                    self.packet(packet, epoch)
                else:
                    early_packet = bytes(packet)
            self.emit('state', state='connecting', connected=False, blocked=True)
            try:
                await asyncio.wait_for(self.backend.connect(args['device_id'],
                    receive,
                    lambda: self.lost(epoch)), 20)
                if generation != self.generation:
                    await self.backend.disconnect()
                    raise ValueError('Connection lost during establishment')
                self.connected = True
                self.last_valid = self.clock()  # Start the initial telemetry deadline.
                self.stale_handled = False
                self.initial_report = True
                self.emit('state', state='awaiting_telemetry', connected=True, blocked=True)
                if early_packet is not None:
                    self.packet(early_packet, epoch)
                if self.owner != client_id:
                    await self.abandon()
                return {'generation': generation}
            except Exception:
                self.blocked = True
                if self.owner == client_id:
                    self.owner = None
                # BleakBackend cleans up partial establishment on cancellation/failure.
                self.connected = False
                self.emit('lost', message='Bluetooth connection failed; motion is unconfirmed.')
                raise ValueError('Bluetooth connection failed; check adapter and device availability') from None
            finally:
                self.connecting = False
        if type(request.get('generation')) is not int or request['generation'] != self.generation:
            raise ValueError('Obsolete connection generation')
        if op in ('stop', 'stop_disconnect') and (client_id in self.clients or self.owner == client_id):
            confirmed = await self.stop()
            if confirmed and op == 'stop_disconnect':
                await self.disconnect()
            return {'confirmed': confirmed}
        if self.owner != client_id:
            raise ValueError('Controller busy or not owned by this client')
        if op == 'resolve_session':
            if not self.recording or self.storage_fault:
                raise ValueError('Walk recording unavailable')
            await self.recording.submit('resolve', (args.get('session_id'), args.get('choice')))
            return self.snapshot_for(client_id)
        if op == 'renew':
            self.renewed = self.clock()
            return {}
        if op in ('stop', 'stop_disconnect', 'release'):
            confirmed = await self.stop()
            if confirmed and op != 'stop':
                await self.disconnect()
            return {'confirmed': confirmed}
        if op not in ('start', 'pause', 'set_speed'):
            raise ValueError('Unknown operation')
        packet = encode_command(op, args.get('speed', 1000))
        if self.tracking_review or (self.recording and self.recording.recorder.walk and self.recording.recorder.walk['status'] == 'interrupted'):
            raise ValueError('Resolve interrupted tracking before motion')
        if not self.connected or self.blocked or self.storage_fault or self.stop_task and not self.stop_task.done():
            raise ValueError('Motion blocked; obtain fresh confirmed state or request Stop')
        if self.clock() - self.renewed >= 6:
            self.spawn(self.client_lost(client_id))
            raise ValueError('Controller lease expired')
        if request['id'] in self.seen or len(self.seen) >= 1024:
            raise ValueError('Duplicate motion request or connection request limit reached')
        self.seen.add(request['id'])
        try:
            await self.write(packet, self.generation, self.motion_generation,
                             before_write=self.prepare_start if op == 'start' else None)
        except CommandCancelled:
            raise
        except Exception:
            self.blocked = self.recovery = True
            self.emit('safety', confirmed=False, message='Bluetooth command failed; belt state is unconfirmed. Use the physical stop control if needed.')
            raise ValueError('Bluetooth command failed or queued motion was cancelled') from None
        if op == 'set_speed': self.target_speed = args['speed']
        return {'written': True}

    async def write(self, packet, generation, motion=None, before_write=None):
        async with self.lock:
            if not self.connected or generation != self.generation:
                raise CommandCancelled('Bluetooth connection lost')
            if motion is not None and (motion != self.motion_generation or self.blocked):
                raise CommandCancelled('Queued motion cancelled')
            if before_write:
                before_write()
            await asyncio.wait_for(self.backend.write(packet), STOP_TIMEOUT)

    def packet(self, packet, epoch):
        if epoch != self.link_epoch or not self.connected:
            return
        try:
            report = parse_telemetry(packet)
        except ValueError:
            self.record('interrupt', 'Invalid telemetry; continuity needs review')
            self.blocked = self.recovery = True
            self.emit('safety', confirmed=False, message='Invalid treadmill telemetry. Readings are stale; Stop is unconfirmed.')
            return
        self.record('observe', report)
        self.last = report
        self.last_valid = self.clock()
        self.stale_handled = False
        self.emit('telemetry', hex=packet.hex())
        if (self.stop_report and not self.stop_report.done() and self.stop_min_sequence is not None
                and self.sequence > self.stop_min_sequence and report.stopped):
            self.stop_report.set_result(True)
        stopping = self.stop_task and not self.stop_task.done()
        if not stopping:
            if report.stopped:
                self.blocked = bool(self.storage_fault)
                self.recovery = False
            elif self.initial_report and not self.recovery:
                self.blocked = bool(self.storage_fault)
            self.initial_report = False
        self.emit('state', state='stopping' if stopping else 'ready', connected=True, blocked=self.blocked)
        if not self.heartbeat_pending:
            self.heartbeat_pending = True
            self.spawn(self.heartbeat(self.generation))

    async def heartbeat(self, generation):
        try:
            # Stop must reach the writer before any new heartbeat.
            if self.stop_task and not self.stop_task.done() and self.stop_min_sequence is None:
                return
            await self.write(HEARTBEAT, generation)
        except Exception:
            if self.connected and generation == self.generation:
                self.blocked = self.recovery = True
                self.emit('safety', confirmed=False, message='Bluetooth write failed; belt state is unconfirmed. Use the physical stop control if needed.')
        finally:
            self.heartbeat_pending = False

    async def stop(self):
        if self.stop_task and not self.stop_task.done():
            return await asyncio.shield(self.stop_task)
        self.blocked = True
        self.recovery = True
        self.motion_generation += 1
        self.stop_task = self.spawn(self.perform_stop(self.generation))
        return await asyncio.shield(self.stop_task)

    async def perform_stop(self, generation):
        self.stop_report = asyncio.get_running_loop().create_future()
        self.stop_min_sequence = None
        self.emit('state', state='stopping', connected=self.connected, blocked=True)
        def begin():
            self.stop_min_sequence = self.sequence
        async def operation():
            await self.write(encode_command('stop'), generation, before_write=begin)
            fresh_stop = await self.stop_report
            return bool(fresh_stop and self.connected and generation == self.generation and self.last and self.last.stopped)
        try:
            confirmed = await asyncio.wait_for(operation(), STOP_TIMEOUT)
        except Exception:
            confirmed = False
        finally:
            if not self.stop_report.done(): self.stop_report.cancel()
        self.blocked = not confirmed or bool(self.storage_fault)
        self.recovery = not confirmed
        self.emit('safety', confirmed=confirmed,
            message='Treadmill reported stopped with zero speed.' if confirmed else
            'Stop unconfirmed. Use the physical stop control. Bluetooth is kept open if available.')
        self.emit('state', state='ready' if confirmed else 'orphaned', connected=self.connected, blocked=self.blocked)
        return confirmed

    async def disconnect(self):
        if not self.connected:
            return
        self.connected = False
        self.owner = None
        self.blocked = True
        self.motion_generation += 1
        self.generation += 1
        self.link_epoch += 1
        await asyncio.wait_for(self.backend.disconnect(), 5)
        self.emit('disconnected', confirmed=True, message='Stopped confirmed before Bluetooth disconnected.')

    def lost(self, epoch):
        if epoch != self.link_epoch:
            return
        self.record('interrupt', 'Bluetooth lost; continuity needs review')
        self.connected = False
        self.blocked = self.recovery = True
        self.owner = None
        self.motion_generation += 1
        self.generation += 1
        self.link_epoch += 1
        if self.stop_report and not self.stop_report.done():
            self.stop_report.set_result(False)
        self.emit('lost', message='Bluetooth lost; belt state is unknown. Use the physical stop control.')

    async def abandon(self):
        self.abandoning = True
        try:
            confirmed = await self.stop()
            if confirmed:
                await self.disconnect()
            else:
                self.emit('state', state='orphaned', connected=self.connected, blocked=True)
        finally:
            self.abandoning = False

    async def client_lost(self, client_id):
        if self.owner != client_id:
            return
        self.owner = None
        self.blocked = self.recovery = True
        self.motion_generation += 1
        if self.connected:
            await self.abandon()

    async def tick(self):
        if self.owner and self.clock() - self.renewed >= 6:
            await self.client_lost(self.owner)
        elif (self.connected and self.last_valid is not None and
              self.clock() - self.last_valid >= 5 and not self.stale_handled):
            self.stale_handled = True
            self.record('interrupt', 'Telemetry gap; continuity needs review')
            await self.stop()

    async def shutdown(self):
        if self.connected:
            await self.abandon()
        for task in tuple(self.tasks):
            task.cancel()
        await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        if self.recording:
            self.record('interrupt', 'Bridge shut down; continuity needs review')
            await self.recording.close()
