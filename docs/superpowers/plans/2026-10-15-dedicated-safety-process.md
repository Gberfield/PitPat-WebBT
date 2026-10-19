# Dedicated Safety Process Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Stop the BA09-B on application-bridge crash/freeze through an independent Bluetooth-owning safety process, then require explicit recovery without replaying motion.

**Architecture:** Extract the validated Stop/writer/telemetry behavior into a small safety process. The existing HTTP/native application becomes an authenticated client and remains the only walk recorder. Separate health and controller leases, fault generations and a direct Stop helper preserve independent failure handling.

**Tech Stack:** Existing Python >=3.11, asyncio, aiohttp, Bleak, Unix sockets/SO_PEERCRED/flock, SQLite recording worker, vanilla JavaScript, existing Quickshell/Omarchy plugin and user systemd. No new third-party dependency is planned.

**Spec:** [Approved dedicated safety process specification](../specs/2026-10-15-dedicated-safety-process-design.md). Read that entire document and [physical evidence](../../safety-failure-tests.md) before execution.

**Status (October 19, 2026):** Tasks 1–9 implemented and software-verified. Task 10 activation, application crash/freeze stopping, automatic IPC reconnect visibility and explicit tray recovery completed with dated evidence. Other physical failure domains and unperformed acceptance items are deferred; this is partial physical acceptance, not a universal Stop guarantee. Execution method is already constrained to the current chat, without additional agents/model calls. Approval to write this plan does not activate services or arm a physical test.

## Global Constraints

- "Safety deadlines and BLE processing never await recording, logs or UI output."
- "One application role may attach at a time; another application cannot displace it."
- "A later stopped packet must not automatically clear a watchdog fault latch."
- "Neither service automatically restarts in the initial release."
- "Neither unit is enabled at login."
- "No automatic resume" applies to startup, reconnect, service recovery and acknowledgment.
- Application challenges: 250 ms; response expiry: 2 seconds; deadline evaluation: at most 50 ms.
- Controller renewal/expiry: 1 second / 6 seconds. Valid telemetry expiry: 5 seconds.
- Stop deadline: 5 seconds total, including writer wait, write completion and fresh confirmation.
- CLOCK_BOOTTIME drives expiry; no hard real-time or physical-stop latency guarantee.
- Frames: at most 16 KiB; eight pending application requests; one pending application command at the GATT writer; 256 retained telemetry samples.
- Protocol speed: integer 1000–6000, increments of 100; keep existing MPH, miles and Cal behavior.
- Runtime directory 0700; socket/lock 0600; peer UID, symlink and ownership checks.
- Preserve HTTP Host/Origin/token protection and the existing dashboard origin `http://127.0.0.1:8766/`.
- No automatic BLE reconnection, speculative commands, firmware changes, adapter resets, host suspend, login startup or exercise uploads.
- No physical treadmill access during automated tests; no desktop/shell interruption in this plan.
- Safety-process failure and Bluetooth loss remain uncovered delivery failures, distinct from application failure.
- Human-readable dates/times use America/New_York; retain machine instants and provenance in records.

## Review Focus

1. A resumed application's buffered health/Start messages must not clear an expired fault — Tasks 3, 4 and 7.
2. A recovered application must be able to resolve an interrupted record before obtaining motion ownership, without a recovery deadlock — Tasks 5 and 6.
3. A timed-out GATT write may finish late; cancellation must not be reported as retracting a command — Tasks 2 and 7.
4. A rolled-back legacy bridge must not start beside the safety BLE owner — Task 8.
5. Killing a simulator's BLE-owning process must not be mistaken for an observed belt stop because its simulator vanished too — Task 7.

## File structure and ownership

All paths below are relative to `/home/gabe/Projects/PitPat-WebBT`.

| File | Responsibility |
| --- | --- |
| `bridge/safety_messages.py` | Strict safety IPC types, schemas, constants and authority representation |
| `bridge/safety_health.py` | Boot-time clock, challenges and application/controller lease evaluation |
| `bridge/safety_core.py` | Sole BLE writer, validated telemetry, grants, fault latch, Stop and evidence ring |
| `bridge/safety_ipc.py` | Private socket server, roles, bounded queues and prioritized Stop |
| `bridge/safety_main.py` | Safety service entry point, runtime lock and isolated simulator selection |
| `bridge/safety_client.py` | Application IPC client, challenge responses, evidence cursor and request matching |
| `bridge/controller.py` | Application-facing controller facade, ownership routing and recording integration |
| `bridge/__main__.py`, `server.py`, `native.py`, `messages.py` | Guarded startup, existing endpoints, explicit recovery and locks |
| `bridge/protocol.py`, `backends.py` | Existing validated wire format and real/synthetic BLE backends |
| `bridge/recorder.py`, `store.py` | Existing canonical walk store; gap/fault provenance and durable readiness |
| `bridge/desktop.py` | Fixed-argument Stop directly through safety IPC |
| `transports.js`, `treadmill.js`, `index.html` | Browser fault display, interrupted-record resolution and recovery acknowledgment |
| `integration/omarchy/gabe.pitpat/{Service.qml,Model.js,Widget.qml}` | Native recovery, stale presentation and grant-based motion controls |
| `integration/systemd/pitpat-{bridge,safety}.service` | Independent user processes and on-demand ordering |
| `scripts/install-omarchy.py` | Versioned, reversible per-user installation payloads; no service management |
| `tests/safety_harness.py`, `tests/safety_process_fixture.py` | Reusable synthetic fixtures and exact child-process identity management |
| `tests/test_safety_*.py` | Contract, core, health, IPC, client and actual process-failure tests |
| `tests/safety-recovery.test.cjs` | Browser recovery behavior |
| `docs/dedicated-safety-acceptance.md` | Release evidence, explicit activation/rollback and physical acceptance procedure |

## Execution and checkpoint rules

Keep all current staged, unstaged and untracked work. The accepted implementation
is largely uncommitted; HEAD alone is not a usable baseline. Before product edits,
follow using-git-worktrees guidance, preserve the complete source/configuration
preimage under ignored `.superpowers/sdd/2026-10-15-dedicated-safety/`, and record
the active checkout, file hashes and intended edit set. Use an isolated checkout on branch `codex/dedicated-safety` containing this
preserved working state; do not create a bare-HEAD worktree and silently omit
the accepted product. Keep dependency environments/private health files outside
the source snapshot. Do not switch or edit the installed service's source checkout
during implementation; apply reviewed source only at the activation gate.

The chat previously returned `repeat_entry: false` for the coding trial; do not
retry enrollment. Apply applicable BERF checks to authorized synthetic checks
at execution time, without workers/model calls or physical fault commands.

Every task follows red/green verification. A red result must be the intended
missing behavior, not a dependency, import or syntax mistake. Finish each task
with a source diff review and a scoped checkpoint. If a real Git author identity
is available, commit only that task's named paths, preserving unrelated staged
changes. Otherwise record hashes/results in the ignored progress ledger; do not
invent an author or change Git configuration. Do not create speculative tests
that merely repeat implementation constants; exercise authority and outcomes.

## Safety IPC contract used by all tasks

Define these names in Task 1; later tasks must not invent alternate spellings.

- `Authority`: immutable fields `safety_id: str`, `link_epoch: int`,
  `fault_generation: int`, `bridge_id: str`, `grant_id: str | None`,
  `command_seq: int`. All counters are nonnegative integers, excluding bool.
- `SafetySnapshot`: `safety_id`, `link_epoch`, `fault_generation`, `fault_id`,
  `link_state`, `authorization_state`, `bridge_healthy`, `owner_id`, `owner_kind`,
  `grant_id`, `target_speed`, `telemetry_seq`, `telemetry_hex`, `stale`,
  `stop_confirmation_id`, `stop_outcome`, `recording_ready`, `ring_first_seq`,
  `ring_last_seq`, `ring_overflow`. Missing physical values remain null/unknown.
- Hello: `{v:1,op:"hello",kind:"application",bridge_id}` or
  `{v:1,op:"hello",kind:"helper"}`. IDs are opaque random strings, 1–64 chars.
- Authorized event: `{v:1,event:"authorized",snapshot:SafetySnapshot}`.
- Application request: `{v:1,id,op,authority,args}`. Application-scoped authority
  has `grant_id:null` before acquiring a grant; helper requests have authority
  null and permit only `observe`, `evidence`, `stop`.
- Operations: `observe`, `evidence`, `discover`, `connect`, `acquire`, `renew`,
  `release`, `start`, `pause`, `set_speed`, `stop`, `stop_disconnect`,
  `recording_ready`, `recover`. Reject extra fields and unknown operations.
- Command args: connect `{device_id}`; acquire `{owner_id,owner_kind}`;
  renew `{renewal_seq}`; set_speed `{speed}`; start/pause `{speed}` with existing
  validated minimum default; evidence `{after_seq,limit}` (limit 1–256);
  recording_ready `{ready,revision,fault_id}`; recover
  `{fault_id,stop_confirmation_id,owner_id,owner_kind}`; other args empty.
- Reply: `{v:1,id,ok,result,error,snapshot}`; result contains `outcome` from
  `accepted|written|stopped_confirmed|unconfirmed` where applicable. A successful
  discover/observe response is not labeled a written command.
- Challenge event: `{v:1,event:"challenge",safety_id,bridge_id,challenge_seq,nonce}`.
  Health reply: `{v:1,op:"health",safety_id,bridge_id,challenge_seq,nonce}`.
  Nonce: 128 unpredictable bits encoded as 32 lowercase hex characters.
- Other events: `{v:1,event,seq,snapshot,data}` with event
  `telemetry|state|fault|safety`; telemetry data includes its sequence and hex.
  Client event sequence and telemetry sequence are separate counters.

Socket framing is UTF-8 newline-delimited JSON; 16 KiB includes the newline.
Never put browser tokens or personal workout exports into this protocol.

### Task 1: Define contract, clock and authority validation

**Files:** Create `bridge/safety_messages.py`, `bridge/safety_health.py`, `tests/test_safety_messages.py`, `tests/test_safety_health.py`.

**Interfaces:** Produce `Authority`, `SafetySnapshot` TypedDict, `validate_frame(frame: dict, role: str) -> dict`, `boot_seconds() -> float`. Reuse `bridge.messages.load_json` and `bridge.protocol.encode_command` for shared parsing/bounds. `boot_seconds` calls `time.clock_gettime(time.CLOCK_BOOTTIME)` and fails startup if unavailable; no silent monotonic-clock fallback.

- [x] **1. Write failing contract/clock tests.** Include strict unknown/duplicate fields, bool counters, nonfinite JSON, empty/long IDs, helper motion denial and invalid speed bounds. Clock test patches clock_gettime and asserts the actual CLOCK_BOOTTIME argument.

```python
def test_helper_cannot_submit_motion(self):
    with self.assertRaises(ValueError):
        validate_frame(self.valid_start_frame, role='helper')

def test_bool_is_not_a_generation(self):
    frame = self.start_with_authority(fault_generation=True)
    with self.assertRaises(ValueError):
        validate_frame(frame, role='application')
```

- [x] **2. Run red:** `.venv/bin/python -m unittest tests.test_safety_messages tests.test_safety_health -v`. Expect failures for the new contract/clock behavior after minimal test discovery is present.
- [x] **3. Implement** the contract above, exported timing/size constants, dataclass authority conversion and typed snapshots. Require a helper's null authority and reject application health frames on helper connections.
- [x] **4. Run green:** same command; all contract and clock cases pass. Run existing `tests.test_bridge_protocol` as a wire-format regression.
- [x] **5. Checkpoint:** review/checkpoint only this task's four files.

### Task 2: Extract the BLE Stop core and latched recovery state

**Files:** Create `bridge/safety_core.py`, `tests/safety_harness.py`, `tests/test_safety_core.py`; reference `bridge/controller.py`, `bridge/protocol.py`, `tests/test_bridge_controller.py`. Leave installed startup unchanged.

**Interfaces:** Produce `SafetyCore(backend, *, clock=boot_seconds)`, synchronous `snapshot() -> SafetySnapshot`, `receive_packet(packet: bytes, link_epoch: int) -> None`, `lose_link(link_epoch: int) -> None`, `trip(reason: str) -> None`, and async `discover() -> list[dict]`, `connect_device(device_id: str) -> dict`, `stop(reason: str, *, latch: bool) -> dict`, `disconnect_confirmed() -> bool`, `close() -> None`. Core exposes typed event subscription without subscriber I/O. Test harness produces `CoreHarness` with `.core`, `.backend`, `.clock`, `async connect_stopped()`, `async flush()`, `async close()` and `.report(speed,state)`; fake backend records writes and can gate/fail each write independently.

- [x] **1. Write failing tests** adapting the current validated Stop cases to the new core: fresh zero after write, simultaneous Stop callers, no disconnect on timeout, cancellation of queued motion and latch persistence after fresh stopped telemetry.

```python
async def test_zero_telemetry_does_not_clear_fault(self):
    self.h.core.trip('bridge_timeout')
    await self.h.flush()
    self.h.report(0, 3)
    await self.h.flush()
    self.assertEqual(self.h.core.snapshot()['authorization_state'], 'fault-latched')

async def test_stop_uses_existing_literal_packet(self):
    task = asyncio.create_task(self.h.core.stop('user', latch=False))
    await self.h.flush()
    self.assertIn(encode_command('stop'), self.h.backend.writes)
    self.h.report(0, 3)
    self.assertEqual((await task)['outcome'], 'stopped_confirmed')
```

- [x] **2. Run red:** `.venv/bin/python -m unittest tests.test_safety_core -v`; confirm intended core behavior is missing.
- [x] **3. Extract** the writer/generation/parser/Stop logic into SafetyCore. Keep fault latch separate from telemetry and normal Stop. Store 256 telemetry samples plus latest/fault snapshots; implement bounded `evidence(after_seq: int, limit: int) -> dict`. Start the five-second Stop deadline before acquiring the writer. Retain one pending application write; Stop invalidates it before queueing itself using an internal cancellation epoch
independent of a normal Stop's still-valid controller grant. Treat uncertain late write completion as unconfirmed until a safe Stop and new report prove stopping.
- [x] **4. Run green:** core tests plus `tests.test_bridge_protocol`; add `test_late_start_write_is_not_retracted_by_cancel`, `test_hung_write_uses_total_stop_budget`, `test_old_link_callback_ignored`, `test_ring_overflow_is_explicit` and initial-connect Stop/zero gating. Assert no automatic latch clearing or additional Start after releasing a hung writer.
- [x] **5. Checkpoint:** core/harness/tests only; no accepted service replacement yet.

### Task 3: Add independent health, ownership and recovery authority

**Files:** Modify `bridge/safety_health.py`, `bridge/safety_core.py`, `tests/safety_harness.py`; extend `tests/test_safety_health.py`, `tests/test_safety_core.py`.

**Interfaces:** Produce `HealthMonitor(clock=boot_seconds)` with `attach(bridge_id: str)`, `issue_challenge() -> dict`, `accept_health(frame: dict) -> bool`, `expired() -> bool`, `detach() -> None`. SafetyCore adds `async handle_application(op: str, authority: Authority, args: dict) -> dict`, `attach_application(bridge_id: str) -> None`, `detach_application(bridge_id: str) -> None`, `accept_health(frame: dict) -> bool`, `async tick() -> None`. Core owns grant/renewal/recording-readiness fields; test harness adds `async arm(owner_kind='browser') -> Authority`, `advance(seconds: float)`, and `health_reply(challenge: dict) -> dict`.

- [x] **1. Write failing lease/recovery tests.** Drive the fake clock, not wall sleeps. Assert trip by 2.05 seconds, immediate app detach, six-second owner expiry, five-second telemetry expiry, old/duplicate health denial and independent owner/application leases.

```python
async def test_deadline_checked_before_buffered_health(self):
    challenge = self.monitor.issue_challenge()
    self.clock.advance(2.05)
    self.assertFalse(self.monitor.accept_health(self.reply(challenge)))
    self.assertTrue(self.monitor.expired())

async def test_late_zero_and_renew_cannot_rearm(self):
    old = await self.h.arm()
    self.h.advance(2.05)
    await self.h.core.tick()
    self.h.report(0, 3)
    with self.assertRaises(ValueError):
        await self.h.core.handle_application('start', old, {'speed': 1000})
```

- [x] **2. Run red:** health/core unittest modules; expect lease/grant assertions to fail.
- [x] **3. Implement** nonce/sequence/expiry matching, one active application and one owner grant, single-use command sequence and received-time expiry. Pace owner renewals at least one second apart; reject burst credits. Check expiry again under the writer immediately before motion. `recover` requires current fault, a new Stop confirmation within five seconds, recording-ready revision for that fault, and explicit owner acknowledgment. It returns a new minimum-speed grant but never sends Start. Fresh zero or a matching session choice alone cannot recover.
- [x] **4. Run green:** include old incarnations, repeated recover, race between recovery/Stop, stale confirmation, startup grace (two seconds from authenticated attach, no motion before first valid response), suspended clock jump, and owner transfer only while stopped. No unbounded request-ID history: grant expires before 1024 accepted motion commands and trips Stop rather than
leaving a moving belt with an exhausted command allowance; Stop remains available.
- [x] **5. Checkpoint:** health/core delta and tests, recording all timing assertions in the ledger.

### Task 4: Serve the safety socket and standalone safety process

**Files:** Create `bridge/safety_ipc.py`, `bridge/safety_main.py`, `tests/test_safety_ipc.py`; modify `bridge/native.py` only for named lock support; extend `tests/test_bridge_native.py`.

**Interfaces:** Produce `SafetyServer(core: SafetyCore, runtime_dir: Path, guard: RuntimeLock)` with async `serve()`, `close()`. Extend `RuntimeLock(runtime_dir, name='service.lock')` to allow only `service.lock` and `bridge.lock`. Safety entry `main(argv=None) -> int` accepts `--simulate`, `--runtime-dir`, `--state-dir` only for private optional diagnostics (no SQLite). Default runtime real `.../pitpat`, simulator `.../pitpat-simulator`. Production entry is `.venv/bin/python -m bridge.safety_main`.

- [x] **1. Write failing socket tests:** permissions, UID rejection, second application refusal, oversized/incomplete frames, non-UTF8 data, helper Stop while app queue is full, and peer disappearance while connected.

```python
async def test_helper_stop_bypasses_full_application_queue(self):
    await self.fill_application_pending(8)
    reply = await self.helper_request('stop')
    self.assertEqual(reply['result']['outcome'], 'stopped_confirmed')
    self.assertEqual(reply['snapshot']['grant_id'], self.original_grant_id)
```

- [x] **2. Run red:** `.venv/bin/python -m unittest tests.test_safety_ipc tests.test_bridge_native -v`.
- [x] **3. Implement** strict hello/role admission, output queue limits (64 control events plus one coalesced telemetry slot), eight application requests, independent helper admission, nonblocking core callbacks and a deadline task that wakes at most every 50 ms. Cap connections at 16, reserve four helper slots and evict no active owner to accept a second application. On control-output overflow trip/detach the application; never await its writer in the safety tick. Put Stop outside the application semaphore/backlog. Acquire original `service.lock` before any backend initialization; use `safety.sock`. Signal shutdown attempts core Stop within its five-second budget.
- [x] **4. Run green:** verify slow consumers cannot delay expiry/Stop, locks refuse legacy coexistence, stale socket inode cleanup is guarded, startup emits no discover/connect/write and simulator construction never imports/initializes Bleak. Keep the current direct protocol constants unchanged.
- [x] **5. Checkpoint:** socket/entry/lock files and relevant tests.

### Task 5: Connect the application facade and canonical recorder

**Files:** Create `bridge/safety_client.py`, `tests/test_safety_client.py`; modify `bridge/controller.py`, `bridge/__main__.py`, `bridge/server.py`, `bridge/native.py`, `bridge/recorder.py`; update `tests/test_bridge_controller.py`, `tests/test_bridge_server.py`, `tests/test_bridge_recorder.py`.

**Interfaces:** `SafetyClient(runtime_dir: Path, bridge_id: str)` exposes async `open()`, `request(op: str, args: dict, authority: Authority | None) -> dict`, `close()` and synchronous `subscribe(callback) -> Callable[[],None]`. Use `Controller(safety_client: SafetyClient, *, recorder=None, clock=boot_seconds)`.
Retain `Controller`'s current server/native facade methods: `register_client`, `unregister_client`, `snapshot_for`, `subscribe`, `spawn`, `dispatch`, `tick`, `shutdown`; replace backend ownership with a SafetyClient and the existing RecordingWorker. Add `Recorder.safety_evidence(snapshot: dict, samples: list[dict]) -> None` as an async operation supported by RecordingWorker.

- [x] **1. Write failing tests** for bridge attachment without ownership, challenge replies on the actual bridge event loop, read-only guardian snapshots, app-client identity to grant routing, unchanged web auth, and interrupted record persistence before readiness.

```python
async def test_resolve_record_before_motion_recovery(self):
    await self.attach_after_fault_with_interrupted_walk()
    await self.facade_request('resolve_session', choice='new')
    self.assertFalse(self.guard_snapshot()['recording_ready'])
    await self.drain_recorder_and_publish_readiness()
    self.assertTrue(self.guard_snapshot()['recording_ready'])
    self.assertIsNone(self.guard_snapshot()['grant_id'])
```

- [x] **2. Run red:** `.venv/bin/python -m unittest tests.test_safety_client tests.test_bridge_controller tests.test_bridge_server tests.test_bridge_recorder -v`.
- [x] **3. Implement** request correlation, authority tracking and challenge replies in SafetyClient on the same loop as command forwarding. No auxiliary health thread/process. Migrate old controller/server/native test
fixtures to a fake SafetyClient or real temporary safety server; do not retain a
legacy real-BLE fallback just to satisfy tests. Facade owns no backend or GATT writer; normal events preserve client-facing `generation/seq/snapshot` shape while carrying new safety fields. Remove the application watchdog's BLE responsibility; `Controller.tick` may update application/recording state but cannot renew grants itself. Guarded startup uses `bridge.lock`, fails closed if safety is absent, and removes all real/simulator backend construction from `bridge.__main__`.
- [x] **4. Implement recording reconciliation** by `(safety_id,link_epoch,telemetry_seq)`. Duplicates never increase totals or speed samples. Gaps/ring loss keep partial coverage; preserve existing session ID. Persist interruption and explicit Continue/New resolution before sending `recording_ready:true` for the current fault/revision; false readiness trips Stop. Use existing explicit `connect {recover:true}` to claim record/recovery control
inside the facade, separately from the guardian motion grant. Expose
`is_recovery_claimant` and `can_resolve_session` in per-client snapshots. Only
one current authenticated claimant may resolve tracking while the motion grant
is absent; its disconnect/six-second inactivity releases that claim without
clearing the fault. Other observers/helpers cannot resolve it. Do not automatically convert a faulted walk to completed from a later zero report.
- [x] **5. Run green:** same command plus store tests. Include DB write failure/stall, evidence replay, stale app response, dropped safety socket, reconnect without grant, bridge reboot with missed ring samples and owner loss while other clients remain. Existing successful tab-close behavior must remain covered.
- [x] **6. Checkpoint:** facade/client/recording/startup and test changes; no live service start.

### Task 6: Add explicit recovery controls and independent emergency Stop

**Files:** Modify `bridge/messages.py`, `bridge/controller.py`, `bridge/desktop.py`, `transports.js`, `treadmill.js`, `index.html`, `integration/omarchy/gabe.pitpat/{Service.qml,Model.js,Widget.qml}`. Create `tests/safety-recovery.test.cjs`; update `tests/test_bridge_desktop.py`, `tests/transports.test.cjs`, `tests/omarchy-model.test.cjs`, `tests/dashboard-ui.test.cjs`.

**Interfaces:** Existing client request schema adds `acknowledge_recovery` args `{fault_id,stop_confirmation_id}`; facade validates claimant and delegates safety `recover`. `BridgeTransport.acknowledgeRecovery(faultId,confirmationId) -> Promise<snapshot>`; QML `acknowledgeRecovery()` uses latest matching values. `bridge.desktop.safety_stop(runtime: Path) -> None` opens only safety.sock as helper, requests Stop and requires `stopped_confirmed`; `main(['stop'])` calls it instead of native_stop.

- [x] **1. Write failing UI/helper tests:** current fault stays visible after zero telemetry, late generation acknowledgment is rejected, track resolution is possible without motion ownership, acknowledgment does not emit Start, and helper succeeds with no application socket.

```javascript
test('stopped telemetry preserves fault recovery gate', () => {
    const view = Model.view(faultedStoppedSnapshot, true);
    assert.equal(view.canStartPause, false);
    assert.equal(view.canAdjust, false);
    assert.equal(view.canStop, true);
});
```

- [x] **2. Run red:** `node --test tests/safety-recovery.test.cjs tests/transports.test.cjs tests/omarchy-model.test.cjs`; `.venv/bin/python -m unittest tests.test_bridge_desktop -v`.
- [x] **3. Implement** “Acknowledge recovery” in web and tray after successful Stop and record resolution. Expose safety availability/fault ID/grant status through facade snapshots; ensure `handleNotification` cannot unblock bridge motion based solely on zero telemetry. Record-choice controls use `can_resolve_session`, not motion-owner status;
acknowledgment requires the current recovery claimant. Keep direct Web Bluetooth
behavior separate. Stale values say stale, not live speed. Preserve popup-close semantics and existing Super+F9/F10 commands.
- [x] **4. Implement helper** with bounded connect/auth and five-second Stop confirmation plus a small IPC allowance (eight-second overall response timeout). It must not call systemctl, discover, connect, acquire or resume a process; failures print Stop unconfirmed and physical-stop guidance. QML warning on bridge loss remains local even when no final event arrives.
- [x] **5. Run green:** commands above plus `node --test tests/dashboard-ui.test.cjs` and facade recovery cases. Assert separate explicit Start after acknowledgment, minimum target reset, and no automatic export. No live QML reload is part of this task.
- [x] **6. Checkpoint:** UI/helper/schema files only.

### Task 7: Verify actual process isolation with a persistent synthetic plant

**Files:** Create `tests/safety_process_fixture.py`, `tests/test_safety_processes.py`; extend `tests/safety_harness.py`; modify `tests/check_qml_service.py`, `tests/qml/shell.qml` for the two-service simulator.

**Interfaces:** Test-only `ProcessPairFixture` provides async `start()`, `connect_and_arm()`, `start_minimum()`, `snapshot()`, `plant_state()`, `kill_application()`, `freeze_application()`, `resume_application()`, `kill_safety()`, `freeze_safety()`, `close()`. Its parent test process hosts a fake GATT plant over a private temporary socket; `.plant_state()` stays observable when either child dies. Child safety uses a test-only RPC backend from `tests.safety_process_fixture`, not a production raw-transport flag. Child application runs actual guarded startup. Fixture tracks Popen/pidfd identities and signals only its own children.

- [x] **1. Write failing two-process tests** with plant starting/running state independent of safety lifetime. Signals must be actual SIGKILL/SIGSTOP. Assert Stop bytes and zero plant speed for application failure, safety child still running, and fault latch after app SIGCONT/restart.

```python
async def test_application_freeze_stops_persistent_plant(self):
    await self.pair.start_minimum()
    await self.pair.freeze_application()
    await self.until_stop_or_deadline(2.05, scheduling_allowance=0.5)
    self.assertEqual((await self.pair.plant_state())['speed'], 0)
    self.assertEqual((await self.pair.snapshot())['authorization_state'], 'fault-latched')

async def test_safety_crash_is_not_a_fake_stop_pass(self):
    await self.pair.start_minimum()
    await self.pair.kill_safety()
    self.assertGreater((await self.pair.plant_state())['speed'], 0)
    self.assertFalse(await self.application_reports_motion_ready())
```

- [x] **2. Run red:** `.venv/bin/python -m unittest tests.test_safety_processes -v`. A disappearing simulator is a harness failure, never proof of Stop.
- [x] **3. Implement fixture/tests** for independent process health and bounded condition polling. Fake-clock tests retain exact 2.05-second software assertions; process tests allow the explicitly reported 0.5-second scheduler margin, not a claimed physical bound. Test app recovery, buffered Start, flooded requests/slow observer, helpers with no application, safety freeze, link loss, no startup BLE and record persistence. Always resume a frozen test child before graceful cleanup or terminate that exact child if needed; no host processes/desktops.
- [x] **4. Adapt QML offscreen check** to start isolated safety then application with explicit temporary paths; preserve failed-initial-socket/two-views/last-view-release assertions and add recovery acknowledgment without Start. Run `.venv/bin/python tests/check_qml_service.py`. Offscreen synthetic execution is not physical or hidden-desktop acceptance.
- [x] **5. Run green:** all process and QML checks; record measured synthetic timing/allowances and remaining hardware limits. Clean only fixture-owned temporary sockets/processes.
- [x] **6. Checkpoint:** harness/fixture/process/QML tests and evidence ledger.

### Task 8: Stage independent services and reversible installation

**Files:** Create `integration/systemd/pitpat-safety.service`; modify `integration/systemd/pitpat-bridge.service`, `scripts/install-omarchy.py`, `tests/test_omarchy_install.py`, `tests/test_bridge_native.py`. Create `tests/test_safety_units.py`.

**Interfaces:** Safety unit runs `@PYTHON_UNIT@ -u -m bridge.safety_main`; bridge retains its module/port. Both `Restart=no`, `UMask=0077`, no Install section; safety `TimeoutStopSec=10`, bridge retains 35. Bridge declares `Wants=pitpat-safety.service`, `After=pitpat-safety.service`; safety declares no PartOf/BindsTo/StopWhenUnneeded relation to the application. Application startup waits at most three seconds for authenticated safety readiness then fails closed. `install-omarchy.plan` emits manifest version 2 with the added safety unit; `validate/apply/rollback` retain version-1 manifest compatibility with its original target set.

- [x] **1. Write failing unit/installer tests:** independent kill domains, startup-only dependency, no restart/login enablement, legacy `service.lock` conflicts in both start orders, version-1 rollback and version-2 drift refusal before any writes.

```python
def test_safety_lifetime_is_not_bound_to_application(self):
    text = self.safety_unit_text()
    for forbidden in ('PartOf=', 'BindsTo=', 'StopWhenUnneeded=yes', 'Restart=always'):
        self.assertNotIn(forbidden, text)
    self.assertNotIn('[Install]', text)
```

- [x] **2. Run red:** `.venv/bin/python -m unittest tests.test_safety_units tests.test_omarchy_install tests.test_bridge_native -v`.
- [x] **3. Implement** exact unit templates and version-aware allowlists/preimages. Preserve before/after hashes and idempotent rollback; unchanged ordinary shell configuration stays unchanged. Installer never starts/stops/reloads services or the shell. Guarded frontend holds bridge.lock; safety holds original service.lock, blocking an old unmodified bridge before BLE/database startup. Do not add a real-mode bypass flag to the new installed frontend.
- [x] **4. Run green** using disposable homes and rendered unit files. Run `systemd-analyze --user verify` on temporary rendered units where the user bus permits; if unavailable record it as unverified rather than using live service mutations. Stage an installation manifest under ignored task state only; do not apply it.
- [x] **5. Checkpoint:** unit templates/installer/tests. Review the target diff against current installed bytes read-only before proposing activation.

### Task 9: Whole-change verification, acceptance procedure and support handoff

**Files:** Create `docs/dedicated-safety-acceptance.md`; update `README.md`, `docs/safety-failure-tests.md`, `docs/firefox-bridge-acceptance.md`, `docs/omarchy-controls-acceptance.md` with new behavior while retaining historical evidence. Update tests only when new findings justify it.

**Interfaces:** Acceptance document records source/preimage hashes, actual checks, measured synthetic timings, failed/held cases, installed state, exact activation/rollback commands and the distinction between application and sole-BLE-owner failures. It links the spec's unsent manufacturer inquiry; no new outbound message tool is used.

- [x] **1. Run complete authorized synthetic checks:**

```bash
.venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/*.test.cjs
.venv/bin/python tests/check_qml_service.py
uv lock --check --offline
git diff --check
```

- [x] **2. Review** boundaries in this chat: no BLE constructor in application startup, no SQLite/HTTP in safety, no background health masking, no auto-clear/replay, global helper Stop independent of app backlog, recording gap handling, and lock compatibility with the actual legacy source. Fix findings with a failing focused test before rerunning affected checks.
- [x] **3. Write acceptance procedure** with explicit readiness/arming per physical case, empty belt/minimum target, physical fallback within five seconds of fault indication, no inferred physical Stop from telemetry alone, and restoration only after stopped confirmation. Leave actual sleep deferred. Separate tests for application and safety PIDs and include the safety-process uncovered-failure warning.
- [x] **4. Prepare support packet** from spec section 12 without sending it. Ask for exact stopped-device label/firmware evidence only when that investigation is resumed; do not expose serial numbers or claim original manuals were verified. No speculative firmware commands/settings are an implementation dependency.
- [x] **5. Record checkpoint**: automated readiness is not deployment or physical acceptance. Present the exact staged file/unit changes and remaining live steps for user review.

### Task 10: Separately authorized activation, physical acceptance and rollback

**Files:** Update only `docs/dedicated-safety-acceptance.md` and ignored private receipts; installation applies only the reviewed manifest's exact user-owned paths. Runtime/database files are not Git artifacts.

**Interfaces:** Activation inputs are approved manifest/preimage hashes, confirmation of stopped/disconnected belt and preserved/resolved record, exact old/new unit identities and a reviewed rollback receipt. This task remains held until its specific live authorization/readiness is supplied.

- [ ] **1. Verify preconditions** read-only and preserve the accepted source/configuration preimage. With the bridge stopped after authorization, copy the closed SQLite database and sidecars if present to a private 0700 backup, files 0600; record hashes and verify a copied database with `PRAGMA integrity_check`. Preserve raw histories. No passphrase/credential collection or retention pruning.
- [ ] **2. Activate only after approval:** stop the old PitPat bridge; apply the reviewed installer manifest; `systemctl --user daemon-reload`; start safety then application and verify both active, no device connection, no owner and HTTP200. Match each unit's MainPID/cmdline/cwd to reviewed sources. Do not enable login startup, restart the shell or open/control a host browser automatically. If changed QML requires a shell restart, stage it and request that separate interruption approval.
- [ ] **3. Conduct separately armed tests** for application SIGKILL, application SIGSTOP/resume, independent helper Stop, explicit web/tray recovery and normal walking/record export. Keep the safety process alive in application tests. Record user belt observations separately from write/telemetry timestamps. Do not reuse earlier arming approvals or mark safety-process failure protected. Any requested safety-process fault test needs its own arming/fallback. No host suspend.
- [ ] **4. On failure, preserve evidence** and keep motion blocked. After physical stopped/disconnected confirmation, stop the new application and safety units, verify their identities are gone, restore reviewed accepted source and the matching installer preimages, daemon-reload and start only the legacy bridge. Verify HTTP200, no owner/connection, no automatic Start and intact history. Never run legacy beside safety or rollback while the belt is moving. Retain the documented legacy crash/freeze limits.
- [ ] **5. Record release disposition** only from actual results. Mark the new application-failure mitigation accepted only after physical passes; retain Bluetooth-loss, safety-process, sleep and power-loss limitations and the original failed observations. Update the existing Notion safety task/epic with verified results through the authorized tracking workflow; no exercise upload from these tests.

## Self-review and handoff

Coverage: spec sections 1–2 map to constraints/acceptance; 3–4 to Tasks 2–6;
5–7 to Tasks 1–4; 8 to Task 5; 9 to Task 6; 10 to Tasks 7–8 and 10;
11 to Tasks 2–10; 12 to Task 9; 13 to this review gate. Review Focus cases each
have a named owning task and an outcome assertion. Interface names above are
shared contracts; changes during execution require updating dependent tasks and
tests together, not silently inventing an alternate API.

The specification and plan were approved by Gabe. Implementation was performed
in the current chat without additional agents/model calls. Software verification
is recorded in the dedicated safety acceptance document. Live activation and
physical acceptance remain separately gated; the installed system is unchanged.
