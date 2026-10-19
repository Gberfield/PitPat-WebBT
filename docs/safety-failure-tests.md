# BA09-B failure-path safety checks

Prepared October 15, 2026 (EDT). Physical tests require Gabe present, an empty
belt, clear surrounding area and an independent physical stop/power control.
Gabe confirmed readiness and connected/stopped state for the first test.
No agent starts the physical belt. One failure is tested at a time at the lowest
target, with a maximum five-second observation before a physical stop if needed.
Never treat a disconnected UI as proof of a stopped belt.

| Check | What it establishes | What it does not establish |
| --- | --- | --- |
| Per-device BlueZ Disconnect, without Stop | Behavior after deliberate loss of the treadmill GATT link | All RF failures, crash behavior, or watchdog implementation |
| Abrupt bridge process exit | Behavior after the actual BLE application dies without graceful shutdown | Computer power loss or suspension |
| Bridge process freeze | Missing application heartbeat/processing while BlueZ remains alive | Actual system sleep |
| Actual computer suspend/resume | Behavior of this host/adapter/treadmill combination during sleep | Universal fail-safe stopping or power-loss behavior |

A graceful service stop exercises the software Stop path; it is not a crash test.
An empty-belt physical pass is evidence for that tested case, not a guaranteed
manufacturer watchdog. Reconnect/restart/resume must not issue Start or replay
motion. Save interrupted walk evidence and resolve tracking explicitly afterward.

Test 1 is scoped to the one verified connected PitPat service UUID/device. It
never toggles the adapter, affects other Bluetooth devices, or sends Stop before
the drop. Its one-shot record and target identity are private in the ignored
`.superpowers/safety-tests/` directory. Physical stopping and latency require
Gabe's observation because no telemetry remains after the link disappears.

Actual host sleep can interrupt all active chats, desktops, downloads and other
work. Do not initiate it without a separately agreed host-wide interruption and
resume procedure. No desktop shutdown, shell restart or automatic reconnect is
authorized by this test preparation. The safety task remains In progress until
results and any limits are documented. Results below distinguish physical observations from software events.

## Test 1 result — deliberate treadmill Bluetooth disconnect

**Failed automatic-stop behavior.** Gabe reported: “Kept moving; I stopped it
physically.” The device-specific BlueZ Disconnect returned success and the
bridge emitted its lost-link warning 2.166 seconds after the request began.
That timestamp measures software notification, not belt-stop latency. No Stop
command was sent before disconnect. Exact physical observation duration was not
reported. The computer’s adapter and other Bluetooth devices were untouched.

This establishes that the tested BA09-B continued moving after this deliberate
link drop and required physical intervention. It does not establish every RF
failure’s behavior or prove the presence/absence of a longer firmware watchdog.
Do not describe Bluetooth disconnect as a reliable automatic stop mechanism.
Test-session records are safety evidence; no exercise upload is authorized or
performed by these tests.

## Reconnect after test 1

Gabe reported “Reconnected; belt stayed stopped.” A read-only bridge snapshot
confirmed tray ownership, fresh stopped/zero-speed telemetry and the interrupted
record retained for an explicit tracking choice. No Start was sent by the agent.

## Test 2 result — abrupt bridge crash

**Failed automatic-stop behavior.** At Gabe’s explicit “Running—crash bridge
now” authorization, the verified PitPat main process received SIGKILL through
a PID-bound handle. Prechecks required the actual unit, Restart=no, repository
working directory, expected module/port and fresh tray-owned minimum-target
running state. No graceful Stop was sent. Gabe reported “Kept moving; I stopped
it physically.” Exact physical stop latency was not reported.

This verifies failure to stop before physical intervention for this application
crash. It does not establish behavior after actual system suspend or power loss.
Recovery is authorized only after Gabe’s stopped confirmation, without automatic
Bluetooth connect or Start. No desktop, shell or other application was stopped.

### Crash software receipts and recovery

User-systemd confirmed `Result=signal`, `ExecMainStatus=9`, `MainPID=0` and
failed state after SIGKILL, with Restart=no. Read-only BlueZ inspection showed
the PitPat link disconnected afterward. These are process/link observations,
not independent belt-stop evidence. Gabe supplied the physical observation.

After Gabe confirmed physical stopping, the manual bridge was restarted.
Readback: dashboard HTTP200, no BLE connection/owner, interrupted record retained,
no storage fault. Startup did not scan, reconnect or send Start. Bridge-freeze results are recorded below. Actual host sleep remains untested.

## Test 3 preparation — bridge freeze only

Gabe chose “Bridge freeze only—leave other work running.” Actual computer sleep
is expressly deferred; no host suspend or desktop interruption is authorized.
The next one-shot test will SIGSTOP only the verified PitPat main process, with
BlueZ and the rest of the computer running. Resume uses PID/start-time/boot-ID
checks and SIGCONT, only after physical-stop confirmation. No Start or Stop is
sent before the freeze, and no automatic resume or crash retry is scheduled.

## Test 3 result — bridge process freeze

**Failed automatic-stop behavior.** The identity-verified PitPat bridge received
SIGSTOP while the empty belt ran at the minimum target. Gabe corrected an initial
response explicitly: “no; i stopped it” and “it didnt stop by itself.” The belt
required physical intervention; exact physical stop latency was not reported.
The initial selection of automatic stopping is superseded by this correction.

After confirmation that the belt was stopped, the same process was resumed with
identity-checked SIGCONT. No Start command was sent. Read-only recovery checks
showed service active/running, dashboard HTTP200, no Bluetooth connection or owner,
no storage fault, and stale/blocked state. Retained running metrics are stale
and do not establish current physical belt motion. Explicit reconnection and
fresh telemetry are needed before considering controls ready.

Bluetooth link loss, bridge crash and bridge freeze each required a physical
stop in these supervised tests. Actual computer sleep was deliberately not
performed. These outcomes do not establish any longer firmware timeout.

## Web and tray Stop-path comparison

The successful web tab-close test removed a controlling client, leaving the
bridge and Bluetooth link available. In `bridge/server.py`, WebSocket cleanup
calls `Controller.unregister_client`; native socket cleanup in `bridge/native.py`
calls the same method. Both reach `client_lost` → `abandon` → `stop` →
`perform_stop`, waiting for a completed serialized Stop write and fresh stopped,
zero-speed telemetry before disconnecting. The tray also exposes the same
`stop_disconnect` command. Its lease expiry uses this controller as well.

The direct Web Bluetooth implementation in `treadmill.js` follows the same
write-plus-fresh-telemetry rule in `requestStop` / `disconnectBluetooth`; its
unexpected-disconnect handler warns that physical stopping is unconfirmed.
Both implementations use notification-driven heartbeat replies, without a
verified device-side loss-of-heartbeat stop configuration.

No missing web-only crash/link-loss stop mechanism was found in this comparison.
The three physical fault tests differ from client/tab closure: link loss removes
the write path, while SIGKILL/SIGSTOP prevents the bridge from executing Stop.
Copying the already-shared Stop path cannot fix those cases. A separate live
guard could attempt recovery for bridge-only failures, but requires its own
design and cannot guarantee stopping when Bluetooth or the computer is lost.
No production behavior or live service was changed by this inspection.
Verification: all 21 controller tests passed, covering confirmed Stop, ownership
loss, lease expiry, stale telemetry, orphan recovery and queued-motion cancellation.
