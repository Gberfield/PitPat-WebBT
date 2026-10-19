"""One telemetry-driven recorder; disk work never runs in the BLE event loop."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import time
import uuid


def instant(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc).isoformat().replace('+00:00', 'Z')


def counters(report):
    return dict(duration=report.duration / 1000, steps=report.steps, calories=report.calories,
                distanceMiles=report.distance / 1000 / (1 if report.unit_mode else 1.609344))


class Recorder:
    def __init__(self, store, clock_ms=lambda: int(time.time() * 1000)):
        self.store, self.clock_ms = store, clock_ms
        self.walk = store.current()  # Startup only, before accepting any clients.
        self.restarted = self.walk is not None
        if self.walk:
            self.walk['status'] = 'interrupted'
            self.walk['coverage'] = 'partial'
            self.walk['endReason'] = 'Bridge restarted; continuity needs review'
        self.baseline = None
        self.latest = None
        self.new_boundary = False
        self.continuity_waiting = False

    async def initialize(self):
        if self.restarted:
            await self._save(self.walk, True)
            self.restarted = False

    def snapshot(self): return deepcopy(self.walk)

    def before_start(self, report):
        self.continuity_waiting = False
        # This is offered at the serialized Start write boundary, not at click time.
        if not self.walk and report and report.stopped:
            self.baseline = counters(report)
            self.new_boundary = False

    async def _save(self, row, current):
        await asyncio.to_thread(self.store.save, deepcopy(row), current)

    async def observe(self, report):
        self.latest = report
        if self.continuity_waiting and report.stopped:return
        if self.continuity_waiting and report.state in (0,1):self.continuity_waiting=False
        if self.walk and self.walk['status'] == 'interrupted': return
        now, raw = self.clock_ms(), counters(report)
        row = deepcopy(self.walk)
        if row is None:
            if report.state != 1: return
            baseline = self.baseline or dict.fromkeys(raw, 0)
            row = dict(schemaVersion=2, trackingVersion=1, sessionId=str(uuid.uuid4()), date=now,
                       startedAt=instant(now), startBasis='Observed pre-start counters' if self.baseline else 'First running observation',
                       coverage='complete' if self.baseline is not None and not self.new_boundary else 'partial',
                       counterBaseline=deepcopy(baseline), counterOffsets=dict.fromkeys(raw, 0),
                       speedSum=0, speedCount=0, speedUnit='mph', maxSpeedMph=0,
                       activeDurationSeconds=None, energyBasis='unknown', speedSamples=[])
        if 'lastCounters' not in row and any(raw[k] + 1e-5 < row['counterBaseline'][k] for k in raw):
            row['coverage'] = 'partial'
            for k in raw:
                if raw[k] + 1e-5 < row['counterBaseline'][k]: row['counterBaseline'][k] = 0
        previous = row.get('lastCounters')
        reset = previous and any(raw[k] + 1e-5 < previous[k] for k in raw)
        if reset:
            row['coverage'] = 'partial'
            # Preserve every prior segment. Stopped reset is a boundary report,
            # not a zero-total replacement; a moving reset begins a new segment.
            for k in raw:
                if raw[k] + 1e-5 < previous[k]:
                    row['counterOffsets'][k] += max(0, previous[k] - row['counterBaseline'][k])
                    row['counterBaseline'][k] = 0
        row['lastCounters'] = raw
        totals = {k: row['counterOffsets'][k] + max(0, raw[k] - row['counterBaseline'][k]) for k in raw}
        row.update(duration=totals['duration'], steps=totals['steps'], distanceMiles=totals['distanceMiles'],
                   calories=f"{totals['calories']:g} Cal", lastObservedAt=now,
                   status={0: 'starting', 1: 'running', 2: 'paused', 3: 'stopping'}[report.state])
        row['sourceTelemetry'] = dict(current_speed=report.speed_raw, running_state=report.state,
                                     distance=report.distance, duration=report.duration, steps=report.steps,
                                     calories=report.calories, speed_unit='mph' if report.unit_mode else 'kph',
                                     distance_unit='mi' if report.unit_mode else 'km', packetHex=report.packet.hex())
        if report.state == 1:
            mph = report.speed_raw / 1000 / (1 if report.unit_mode else 1.609344)
            row['speedSum'] += mph * 1000
            row['speedCount'] += 1
            row['maxSpeedMph'] = max(row['maxSpeedMph'], mph)
            if not row['speedSamples'] or now - row['speedSamples'][-1]['at'] >= 5000:
                row['speedSamples'].append(dict(at=now, mph=mph, sourceSpeed=report.speed_raw,
                                                sourceUnit='mph' if report.unit_mode else 'kph'))
        row['avgSpeed'] = row['speedSum'] / row['speedCount'] / 1000 if row['speedCount'] else None
        row['observedElapsedSeconds'] = max(0, (now - row['date']) / 1000)
        if report.stopped:
            row.update(status='completed', endReason='Stopped', endedAt=instant(now))
        await self._save(row, not report.stopped)
        self.walk = None if report.stopped else row
        if report.stopped:
            self.baseline = None
            self.new_boundary = False

    async def interrupt(self, reason):
        if not self.walk: return
        row = deepcopy(self.walk)
        row.update(status='interrupted', coverage='partial', endReason=reason,
                   endedAt=instant(row['lastObservedAt']))
        await self._save(row, True)
        self.walk = row

    async def safety_evidence(self, snapshot, samples):
        if not self.walk:return
        row=deepcopy(self.walk)
        row.update(status='interrupted',coverage='partial',endReason='Safety interruption; continuity needs review',endedAt=instant(row['lastObservedAt']))
        row['safetyEvidence']={k:deepcopy(snapshot.get(k)) for k in ('safety_id','link_epoch','fault_id','fault','telemetry_seq','ring_overflow')}
        # Evidence is provenance, not another counted stream of workout samples.
        row['safetyEvidence']['samples']=deepcopy(samples[-256:])
        await self._save(row,True);self.walk=row

    async def resolve(self, session_id, choice):
        if not self.walk or self.walk['sessionId'] != session_id or self.walk['status'] != 'interrupted':
            raise ValueError('No matching interrupted record')
        if choice not in ('continue', 'new'): raise ValueError('Invalid continuity choice')
        row = deepcopy(self.walk)
        if choice == 'continue':
            self.continuity_waiting=True
            row.update(status='paused', endReason=None, endedAt=None, coverage='partial')
            await self._save(row, True)
            self.walk = row
        else:
            self.continuity_waiting=False
            await self._save(row, False)
            self.walk = None
            self.baseline = counters(self.latest) if self.latest else None
            self.new_boundary = True


class RecordingWorker:
    def __init__(self, recorder, on_fault, on_update):
        self.recorder, self.on_fault, self.on_update = recorder, on_fault, on_update
        self.queue = asyncio.Queue(maxsize=256)
        self.task = None
        self.fault = None
        self.closed = False

    def fail(self, error):
        if self.fault is None:
            self.fault = str(error)
            self.on_fault('Walk recording failed; motion blocked. ' + self.fault)

    def offer(self, kind, payload=None, future=None):
        if self.fault or self.closed: return False
        try: self.queue.put_nowait((kind, payload, future))
        except asyncio.QueueFull:
            self.fail('Recording queue overflow')
            return False
        if self.task is None or self.task.done(): self.task = asyncio.create_task(self.run())
        return True

    async def submit(self, kind, payload):
        future = asyncio.get_running_loop().create_future()
        if not self.offer(kind, payload, future): raise ValueError('Walk recording unavailable')
        return await asyncio.shield(future)

    async def run(self):
        while not self.queue.empty():
            kind, payload, future = self.queue.get_nowait()
            try:
                if self.fault: raise OSError('Walk recording unavailable')
                if kind == 'before_start': self.recorder.before_start(payload)
                elif kind == 'resolve': await self.recorder.resolve(*payload)
                elif kind == 'initialize': await self.recorder.initialize()
                elif kind == 'observe': await self.recorder.observe(payload)
                elif kind == 'interrupt': await self.recorder.interrupt(payload)
                elif kind == 'safety_evidence': await self.recorder.safety_evidence(*payload)
                else: raise ValueError('Unknown recording operation')
                self.on_update(self.recorder.snapshot())
                if future and not future.done(): future.set_result(True)
            except Exception as exc:
                if future and not future.done(): future.set_exception(exc)
                if not (kind == 'resolve' and isinstance(exc, ValueError)):
                    self.fail(exc)
            finally: self.queue.task_done()

    async def drain(self): await self.queue.join()

    async def close(self):
        self.closed = True
        await self.drain()
        if self.task: await self.task
