# Dedicated PitPat safety process

Date: October 15, 2026 (America/New_York, EDT)

Status: written specification approved by Gabe on October 15, 2026 (EDT).
This document authorizes no implementation, installation or physical test.

Related specification: [Omarchy controls and shared recording](2026-10-15-omarchy-controls-design.md).
Physical evidence: [BA09-B failure-path tests](../../safety-failure-tests.md).
Notion safety task: https://www.notion.so/3faa4f6701628144b7b3d17a3d38f922

## 1. Purpose and evidence

Stop the DeerRun PitPat BA09-B when the application bridge crashes or freezes,
provided a separate safety process, BlueZ, the computer and the Bluetooth link
remain functional. Preserve the interrupted walk, report confirmation honestly,
and require a deliberate user action before allowing motion again.

Gabe approved a dedicated Bluetooth-owning process instead of a watchdog that
must reclaim Bluetooth after failure. The approved design retains the validated
Stop packet, serialized writes and fresh stopped/zero-speed confirmation.

Supervised tests on October 15 established:

| Existing system test | Observed result |
| --- | --- |
| Controlling browser tab closes; bridge and BLE survive | Gabe reported that the belt stopped and stayed stopped after reconnect |
| Deliberate treadmill-only Bluetooth disconnect | Belt kept moving; Gabe stopped it physically |
| Abrupt bridge SIGKILL | Belt kept moving; Gabe stopped it physically |
| Bridge SIGSTOP freeze | Belt kept moving; Gabe stopped it physically |
| Actual host suspend/resume | Not performed; Gabe deferred it to avoid interrupting other work |

The initial automatic-stop selection for the freeze test was explicitly corrected
by Gabe and is not a pass. Exact physical stop latencies were not reported.
The old application's crash test killed the sole BLE owner. Under this design,
application-bridge failure and safety-process failure are different tests; both
must remain visible in reporting.

## 2. Scope and limits

Included: independent application-health monitoring, sole Bluetooth ownership,
Stop on application failure, explicit fault recovery, direct emergency Stop IPC,
compatible web/tray behavior, interrupted-record reconciliation and isolated
simulator verification followed by separately armed physical acceptance.

The safety process is a software mitigation, not a certified safety interlock.
Its own crash/freeze, computer suspension/power loss, BlueZ failure and radio loss
can prevent Stop delivery. No hardware watchdog, RF-loss timeout or manufacturer
firmware capability has been verified. The physical stop control remains needed.

Excluded: automatic BLE reconnection, automatic motion replay, device firmware
changes, speculative BLE commands, adapter-wide resets, host sleep hooks, smart
plugs, electrical modifications, automatic exercise uploads and login startup.
This specification changes the earlier sole-BLE-owner assignment from the
application bridge to the safety process; it preserves the earlier user-control
and recording requirements except where explicitly tightened below.

## 3. Components and responsibility

### Safety process: `pitpat-safety.service`

A separate user service and process owns the Bleak client, validated protocol
parser, device discovery results, link lifecycle and the only GATT writer. It
enforces bridge health, controller ownership/lease, telemetry freshness, command
generations and a latched fault state. It implements Stop and its confirmation.

It serves a private Unix socket at `$XDG_RUNTIME_DIR/pitpat/safety.sock`. It has
no HTTP listener, Notion client, SQLite connection, browser renderer, QML engine,
subprocess-based recovery routine or arbitrary command execution interface.
Safety deadlines and BLE processing never await recording, logs or UI output.

### Application bridge: `pitpat-bridge.service`

The existing service retains `127.0.0.1:8766`, browser authentication, native
web/tray routing, UI ownership decisions, session recording and export. It uses
typed IPC to the safety process and cannot open a real Bleak client in this mode.
The native control socket remains the normal tray entry point.

Bridge state may describe requested ownership but cannot override the safety
process's authoritative grant, fault latch, connection generation or readiness.
The guardian is the final authority at the write boundary.

### Existing clients and emergency helper

Firefox and the Omarchy tray retain their existing controls and display units.
Their commands pass through the bridge. Closing the tray popup alone still does
not end tray ownership; disappearance of its owning client still requests Stop.

Super+F11's fixed-argument helper targets the safety socket directly. Its role
permits Observe and Stop only, without application availability or a motion grant.
It never starts a service that silently connects to a treadmill. If the safety
process/link is unavailable it returns an unconfirmed result and directs the
user to the physical stop. No shell restart or binding change is implied.

## 4. Reuse of the existing Stop core

Extract the safety-relevant behavior from `bridge/controller.py` into the safety
process, rather than maintaining a competing Stop implementation. Reuse
`bridge/protocol.py` for packet generation, telemetry validation and the stopped
predicate. Keep wire-level limits and the existing notification-driven heartbeat.

The following invariants survive the extraction:

1. All GATT writes use one serialized writer.
2. Stop invalidates queued motion before waiting for the writer.
3. Stop is confirmed only after its write succeeds and a validated telemetry
   packet received after the write began reports state 3 and speed zero.
4. A cached zero report, write acknowledgment, disconnected socket or process
   exit is never proof of physical stopping.
5. Timeout, failed write or link loss yields Stop unconfirmed. Keep the link open
   if it remains usable; never disconnect merely to make the UI appear finished.
6. Old connection callbacks, old grants and delayed motion requests cannot cross
   a connection or fault generation.

Unlike the current controller, a later stopped packet must not automatically
clear a watchdog fault latch. Physical state and permission to move are separate.

## 5. Health monitoring and deadlines

There are two independent leases. Application challenges establish that the
bridge's command-processing event loop is responsive. The existing controller
lease establishes that the particular browser/tray motion owner is still present.
Neither lease may stand in for the other.

| Deadline | Initial specified value | Meaning |
| --- | --- | --- |
| Application challenge cadence | 250 ms | Safety process issues a new unpredictable challenge |
| Application response expiry | 2 seconds | Missing timely valid response triggers latched Stop |
| Deadline evaluation cadence | At most 50 ms | Evaluate application/owner/telemetry deadlines independently of output queues |
| Controller renewal cadence / expiry | 1 second / 6 seconds | Preserve existing owner-loss stopping behavior |
| Valid telemetry expiry | 5 seconds | A stale link blocks motion and requests Stop |
| Stop operation deadline | 5 seconds total | Includes writer wait, Stop write and fresh confirmation |

These are software deadlines, not a maximum physical stopping time or a hard
real-time guarantee. Under a responsive safety process the target is to initiate
Stop no later than 2.05 seconds after the last accepted timely application-health
response. Process/socket closure triggers it as soon as that closure is observed.
Physical deceleration and actual fault-to-zero latency must be measured.

Challenge responses run in the same bridge event loop that accepts and forwards
commands. Do not put them in an independent thread or process that could keep a
frozen application looking healthy. A response must match an outstanding nonce,
bridge incarnation and safety generation, arrive before its deadline, and be
accepted once. Duplicates and older challenge responses cannot extend health.
All expiry checks use the safety process's receive time, not client timestamps.
Check deadlines before processing buffered responses and immediately before any
motion write: a backlog after a stall cannot revive an already expired grant.

Do not accept a single application-health response as renewal for the motion
owner. Owner renewals identify the active grant and monotonically increasing
renewal sequence; they are paced, not accumulated as future lease credit. Bridge
reconnection begins without an owner, and observers cannot renew either grant.

Use an elapsed-time clock that includes suspend (Linux `CLOCK_BOOTTIME`) for
safety expiry so an elapsed deadline stays expired on wake. This permits a Stop
attempt after wake; it provides no execution or protection while the host sleeps.

## 6. State and fault recovery

Represent link state and motion authorization separately. Link states are
disconnected, connecting, connected and lost. Authorization states are unarmed,
ready, stopping and fault-latched. Last physical telemetry has its own freshness.

| Event | Required transition/action |
| --- | --- |
| Safety-process startup/restart | New incarnation; disconnected/unarmed; no scan, connection or motion |
| Explicit selected-device connection | Connecting/unarmed, then verify with Stop and fresh zero telemetry before allowing a grant |
| Healthy bridge and explicit user control acquisition | Issue one ready grant when all readiness conditions hold |
| Application crash, IPC closure or health expiry while connected | Invalidate grant and queued motion; latch fault; request Stop |
| Controller loss/expiry, invalid/stale telemetry, recording fault | Invalidate grant; latch fault; request Stop while BLE is available |
| BLE loss | Invalidate grant; latch fault; motion unknown; no automatic reconnect |
| Stop confirmation | Update physical evidence to stopped; preserve any fault latch |
| Bridge resumes/restarts | Observe fault; cannot reclaim previous grant or replay old requests |
| Deliberate recovery | Require conditions below; create a new grant, without starting the belt |

Recovery requires a healthy current bridge, a usable selected BLE connection,
a new successful Stop confirmation, no recording/storage fault, resolution of
interrupted tracking and an explicit user acknowledgment referencing the current
fault ID and generation. Recovery resets the target to the minimum validated
speed. A separate deliberate Start is still required. Resolving a session or
acknowledging a warning alone does not clear all these conditions.

A normal user Stop need not create a fault. Normal Stop & Disconnect still waits
for confirmation before disconnecting. If either service is restarted during a
walk, treat continuity as interrupted even if counters later look plausible.

## 7. IPC, command authority and queue handling

Keep the current HTTP Host/Origin/token restrictions unchanged. No HTTP route
gains a raw BLE, process-signal or shell-execution capability.

The safety socket and exclusive lock use the existing private-runtime approach:
directory 0700, socket/lock 0600, ownership and symlink checks, peer UID validation
and a lock held before opening BLE. One application role may attach at a time;
another application cannot displace it. Helpers can observe/request Stop only.
This protects against unrelated websites and other users, not malicious code
running as Gabe. Authentication is not a certification boundary.

Define a separate versioned IPC contract; do not silently reinterpret existing
browser/native frames. Required operation families are:

- Attach/observe; challenge/response; bounded telemetry and fault events.
- Explicit discovery/selected-device connection and confirmed disconnection.
- Acquire/renew/release of the single controller grant, including owner identity.
- Validated Start/Pause/Set speed and global Stop.
- Recording-readiness updates and explicit fault recovery acknowledgment.

Every motion command carries a unique request ID, current safety incarnation,
link epoch, fault generation, bridge incarnation and controller grant. Reject
missing, old, duplicated or out-of-order authority. Neither acknowledgment nor
IPC delivery means a GATT write occurred; responses distinguish accepted,
written, stopped-confirmed and failed/unconfirmed outcomes.

Use strict schemas and the existing rejection of duplicate JSON keys/nonfinite
numbers. Bound frames to 16 KiB, pending application requests to eight, and keep
only one pending application command at the GATT writer. Coalesce notification
heartbeats. Use bounded output with latest-telemetry coalescing so slow observers
cannot stall deadlines. Stop and fault handling run outside the application
request backlog and must remain serviceable when that backlog is full. A helper
Stop is admitted independently of the application's eight-request allowance.

Already submitted GATT writes cannot be retracted by clearing a Python queue.
Stop supersedes all not-yet-submitted motion; the operation deadline includes
waiting for any submitted write. If cancellation leaves a write's completion
uncertain, keep motion inhibited and report Stop unconfirmed unless a subsequent
safe Stop write and fresh report establish otherwise. Never infer that backend
cancellation physically undid a command or replay Start after a timeout.

## 8. Recording and evidence

The bridge remains the only SQLite walk recorder; the safety process never opens
that database. Safety telemetry carries a process incarnation, link epoch and
monotonic sequence. The bridge detects gaps and marks coverage partial instead
of fabricating observations or merging records on counters alone.

The safety process retains a bounded in-memory ring of 256 telemetry samples,
the latest counters and one current fault record independently of any observer
queue. The fault record includes its identity/generation, trigger, last valid
telemetry sequence, Stop attempt and confirmation outcome. A new bridge can read
this evidence; it may not silently resume an old walk. Ring overflow is explicit.
Events can be written through a bounded worker for diagnostics, but disk output
is best effort and cannot delay Stop. If the safety process also dies, the ring
can be lost; the bridge's persisted record remains partial/interrupted.

The bridge persists interruption before marking recovery recording-ready. During
recording failure it withdraws readiness and the safety process requests Stop.
Application health is not proof of storage health. Normal session saving,
durable readiness acknowledgment and export stay outside the safety event loop.

Keep fault diagnostics private, preserve source measurements, use Eastern Time
for human-facing timestamps, and never automatically count/export safety-test
sessions as exercise. Retain current Continue/New record choices; either choice
is explicit and preserves the original interrupted evidence.

## 9. User-visible behavior

The dashboard and tray distinguish application unavailable, safety unavailable,
connecting, ready, stopping, stopped confirmed and Stop unconfirmed. Motion
controls require a current ready grant and fresh state. A persistent fault
message survives bridge reconnection; it states the failure and recovery action.
Stale retained speed must be labeled stale rather than displayed as live motion.

Emergency Stop remains usable through the safety helper when the application
bridge is dead or frozen. If the UI is unavailable, the helper prints the actual
confirmation outcome; it cannot promise a visual notification or belt stopping.
The tray's existing disconnect warning must not depend on receiving a final
message from a crashed bridge. Recovery acknowledgment is available in both web
and tray flows without starting motion.

## 10. Service lifecycle and migration

Keep separate user units and processes: starting the application starts the
safety dependency on demand and waits for authenticated readiness. Neither unit
is enabled at login. Do not make safety lifetime depend on application lifetime:
application exit, restart or freeze must leave safety running to attempt Stop.
Avoid dependency/kill settings that terminate both for an application-only fault.

Neither service automatically restarts in the initial release. A manually
restarted application attaches as an observer without ownership. A restarted
safety process never scans/connects on its own and rejects old grants. A restart
policy may be evaluated separately but is not an automatic-stop mechanism.

Graceful safety shutdown first latches motion off and attempts the bounded Stop
while BLE is usable. Allow that deadline before systemd termination. If safety
is killed/frozen, shutdown code cannot run: report this as the remaining sole
BLE-owner failure. Do not add a competing BLE writer, self-resume signal handler
or automatic adapter reset to hide it.

Installation must prevent the legacy single-process bridge and the new safety
process from owning BLE concurrently. Use one shared exclusive BLE-ownership
lock and disable legacy real-BLE startup in the installed safety mode. Existing
direct Web Bluetooth pages on another server cannot be constrained by that local
lock; document that they must remain disconnected during guarded operation.

Preserve source/configuration/database backups. Stage and test the split before
activation. Live activation and rollback require the belt physically stopped and
disconnected and the record resolved/preserved. Rollback restores the accepted
legacy unit/entry point with its documented crash/freeze limitations. No desktop
shutdown, shell restart, host suspend or automatic activation is authorized here.

Simulator mode has separate runtime/state paths for both processes and no real
Bleak initialization. Test supervisors may signal only their exact disposable
processes; never infer permission to signal the installed services.

## 11. Acceptance and verification

### Automated, no physical treadmill

Use the existing protocol fixtures and fake backend to prove identical Stop bytes
and fresh zero-state confirmation. Test the actual two-process boundary with an
isolated simulator; unit-only timer tests are insufficient for isolation claims.

Required cases:

- SIGKILL and SIGSTOP of the application only, while safety remains responsive:
  deadline-triggered Stop, no queued motion after fault, no automatic resume.
- Dead/frozen application while tray, browser and helper observers remain;
  observers and a background heartbeat task cannot mask bridge/owner loss.
- Late/duplicated challenges, buffered owner renewals, old incarnations and
  delayed Start around deadline expiry, restart and recovery.
- Saturated command/output queues, slow consumers, malformed frames and recording
  faults; emergency Stop and deadline evaluation remain available.
- Hung GATT write, lost link, invalid/stale telemetry, zero speed with running
  state, stopped state with nonzero speed, and stopped telemetry before Stop write.
- Resumption of the frozen application: fault latch persists and Start fails
  until explicit acknowledged recovery plus a separate Start request.
- Safety-process SIGKILL/SIGSTOP: application disables motion/reports unknown;
  results explicitly say no software Stop execution is assured.
- Helper Stop while the application is absent; helper cannot acquire motion.
- No BLE connection/Start on either service's startup; mutual exclusion with
  legacy mode; partial startup, service ordering, shutdown and rollback.
- Single canonical recording, replay/gap detection, partial coverage and existing
  Notion export deduplication; no automatic exercise upload.
- Clock advancement across a simulated suspend gap expires authority; this is a
  clock test, not actual suspend or physical safety acceptance.

### Separately supervised physical acceptance

Obtain per-test readiness and arming with Gabe beside an empty belt, clear area
and independent stop ready, as in the existing safety-test procedure. Start only
through Gabe's deliberate action at the minimum target. No unattended tests.

Test application crash and freeze separately; record application PID/identity,
safety process still responsive, fault-detection time, Stop write/confirmation
timing and Gabe's belt observation. Observe for at most five seconds after fault
indication; use physical stop immediately if necessary. Do not extend observation
to wait out a speculative firmware timer. Stop confirmation without an observed
belt stop is not a physical pass. Restart/resume only after stopped confirmation.

Then verify no automatic motion after application recovery, explicit recovery in
both interfaces, independent helper Stop and accepted normal controls/recording.
Retain Bluetooth-loss and safety-process-failure limitations; do not relabel the
old bridge crash/freeze failures as passes because the process roles changed.
Any new safety-process fault test requires its own explicit arming and physical
fallback. Actual host suspend remains deferred unless separately authorized.

Release requires automated evidence, independent self-review in this chat,
successful supervised application-failure tests and truthful remaining limits.
Passing tests establishes the tested configuration, not universal fail-safe
behavior. Work remains in this chat without additional agents/model calls.

## 12. Treadmill Bluetooth-loss safeguard investigation

Current disposition: **not verified; no setting or firmware command selected**.
The deliberate disconnect test required physical intervention before any longer
timeout could be established. Do not conclude that all firmware lacks a watchdog.

Research found a BA09/BA10 manual listing BA09-B. Publicly accessible material
did not establish a configurable BA09-B Bluetooth-loss stop. Generic communication
errors, a Bluetooth status icon, another model's unattended stop and an app
countdown are not evidence of a radio-loss safeguard for this treadmill.

Sources and limitations:

- [DeerRun official FAQ](https://deerruntreadmill.com/pages/faq): offers an electronic
  manual through support; it does not establish a BA09-B loss-of-link guarantee.
- [DeerRun official support](https://deerruntreadmill.com/pages/contact-us): lists
  `support@deerruntreadmill.com` as the after-sales contact.
- [BA09/BA10 manual listing](https://manuals.plus/m/9b833fce15b831298819c431dcbc89b4e821b5c69f9221450be45162326bd1e0):
  third-party conversion lists BA09-B; original PDF access was restricted. Treat
  this as a manual-discovery lead, not verified firmware instructions.
- [BA09 FCC manual listing](https://device.report/m/bf6e76840a2ec87ddf0747577aa0e7e1e4675649dd658b224111b317f11f9700):
  family-level lead only; regulatory identity has not been matched to Gabe's
  physical label. Direct PDF retrieval was refused. Another distributor's large
  multilingual PDF download timed out before completion and was not reviewed.

Prepare, but do not send, the following support inquiry:

> I have a DeerRun PitPat BA09-B. In supervised empty-belt tests, loss of the
> Bluetooth link and a stopped/crashed controlling application left the belt
> moving until I stopped it physically. Does this exact model and firmware have
> an automatic stop on Bluetooth disconnection or missing application heartbeat?
> If so, what enables it, what is the documented timeout and stopping behavior,
> and does it remain enabled after power cycling? Does it require a particular
> control mode, app command or firmware version? Please provide the model-specific
> manual and supported configuration/update instructions. Does reconnection ever
> resume motion without a separate Start? If unavailable, what independent stop
> mechanism is supported for this model?

The next evidence step is Gabe supplying model-label/firmware details through a
stopped-device, read-only workflow and a manufacturer response or exact original
manual. Keep serial numbers private. Any new device access, firmware update,
outbound message or physical experiment needs its own appropriate authorization.
Do not guess unknown protocol settings or modify firmware as part of this design.

## 13. Review boundary

This is a written design for review, not an implementation plan. After Gabe
approves this specification, prepare the implementation plan with exact source
boundaries, IPC schema, tests and reversible activation steps. Implementation and
live activation remain later stages. The current services and desktop stay as-is.
