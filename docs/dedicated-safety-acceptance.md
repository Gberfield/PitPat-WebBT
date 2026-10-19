# Dedicated safety process: implementation and acceptance

Date: October 15, 2026 (EDT).

Status: activated October 15, 2026 at 7:46 PM EDT from the retained
`codex/dedicated-safety` worktree after explicit stopped/disconnected and
walk-preservation confirmation. Both services verified active/running, the
dashboard returned HTTP 200, and safety reported disconnected, unarmed, no
owner/grant, no fault, and a healthy application. Physical acceptance is partial; see the dated physical results below. The original physical crash/freeze/link-loss failures remain evidence.

The old bridge exceeded its 35-second shutdown timeout and systemd terminated
it before replacement. Its PID was verified gone before the database backup.
The private closed-database backup passed `PRAGMA integrity_check`. Exact hashes,
service identities and readback are retained in the private activation receipt.
No Bluetooth scan, connection or Start was issued; no shell/desktop restart occurred.
Installed QML files match the manifest, but loading them in the running shell
has not been verified; cached QML may require a separately approved refresh.

## Source and reviewed installation

Reviewed source checkout:
`/home/gabe/Projects/PitPat-WebBT/.superpowers/worktrees/dedicated-safety`.
Do not delete or move this checkout while an installed manifest points to it.
The existing accepted checkout remains `/home/gabe/Projects/PitPat-WebBT`.
No commits were made because a real Git author identity is not configured.

[Specification](superpowers/specs/2026-10-15-dedicated-safety-process-design.md)
and [implementation plan](superpowers/plans/2026-10-15-dedicated-safety-process.md)
are the governing design and task boundaries. Private source hashes, preimages,
progress, test receipts and the installation manifest are under this task's
ignored `.superpowers/sdd/2026-10-15-dedicated-safety-process/` directories.

The staged installer manifest changes only:

- `~/.config/systemd/user/pitpat-bridge.service` to use the reviewed application
  checkout and request the independent safety dependency on demand.
- `~/.config/systemd/user/pitpat-safety.service` for the independent BLE owner.
- `~/.local/bin/pitpat` to use the reviewed helper; Stop targets safety.sock.
- The existing plugin's `Service.qml`, `Widget.qml`, `Model.js` for recovery.

The other manifest targets are unchanged. No login enablement, automatic service
restart, packaged Omarchy edit or desktop shutdown is part of installation.
QML may remain cached in the running shell; any necessary shell restart requires
separate explicit approval, with the bar/panels interruption explained and other
application/profile state retained. The earlier one-time shell restart approval
was already used and does not authorize another.

## Software verification

The complete Python and JavaScript suites, actual offscreen Quickshell check,
offline lock validation and syntax/whitespace checks are run from the reviewed
checkout. Final results: **115 Python tests and 90 JavaScript tests passed**. The actual
offscreen Quickshell check passed recovery acknowledgment without Start, shared
view ownership and last-view release. Offline lock validation, compilation and
whitespace checks passed. Private receipts retain exact commands and output;
counts were not inferred from older acceptance documents.

The process fixture hosts the synthetic GATT plant outside both child processes.
Therefore killing the BLE-owning process does not erase evidence of continued
motion. It never uses an installed service, real Bluetooth adapter or desktop.

| Tested synthetic case | Result |
| --- | --- |
| Application SIGKILL | Safety process survives and sends confirmed Stop to the persistent plant |
| Application SIGSTOP | Safety deadline stops the plant; resumption does not restart it |
| Explicit recovery after application resumption | New Stop, record resolution and acknowledgment required; Start remains a separate request |
| Direct emergency helper while application frozen | Helper reaches safety.sock and confirms Stop independently |
| Safety-process SIGKILL | Plant keeps moving; explicitly an uncovered failure |
| Safety-process SIGSTOP | Plant keeps moving; application reports unavailable/blocks motion |
| Slow application output/control queue saturation | Fault trips; direct helper Stop remains usable |
| Duplicate/stale motion authority | Rejected, without replaying writes |
| Uncertain timed-out motion write | Stop remains unconfirmed, including streamed events; explicit new physical link needed after safely stopping/power-cycling |
| Fault record reconciliation | Same session and original measurements preserved; evidence does not create a second counted workout |
| Missing safety process during startup | Application refuses before touching the walk database |
| Installer and rollback | Disposable-home tests retain version-1 rollback, enforce version-2 targets and refuse drift |

Exact fake-clock expiry tests use two seconds plus at most 50 ms evaluation
cadence. Real-process synthetic tests allow 0.5 seconds scheduling tolerance.
Neither measures physical belt deceleration or promises a hard real-time bound.
A parent Stop implementation remains as the extracted `control_core.py` kernel
with its existing regression tests; the production application facade has no
BLE writer. New end-to-end tests exercise the actual guarded entry point.

A bounded BERF preflight returned `unknown_state`; it did not execute a check or
establish correctness. Ordinary explicit checks supplied the verification.
Whole-change review stayed in this chat, per the no-additional-agents constraint;
this is self-review, not an independent review. Sandbox-restricted socket tests
were not accepted as results; successful socket/process checks used the normal
narrow execution approval route with temporary resources only.

## Deliberate implementation rulings

- The private `owner_lost` operation distinguishes an unexpectedly vanished client
  from deliberate Stop & Release. It latches the fault even while bridge health
  remains good.
- Early renewals are ignored without credit rather than closing a healthy client
  over subsecond timer jitter. Replayed renewal sequences are rejected.
- Request IDs and grants prevent replay. Health/renewal traffic does not consume
  the 1024-motion-command budget.
- Safety evidence is paged to fit 16 KiB framing; the 256-sample ring is bounded.
- Recording is constructed only after safety authentication, in a worker thread,
  so missing safety or legacy coexistence cannot corrupt an active walk record.
- An ambiguous motion-write timeout is stricter than normal Stop timeout: keep
  motion latched, use the physical stop, then power-cycle the stopped treadmill
  and explicitly reconnect. Cancellation is not proof the device command vanished.

## Activation procedure: performed after live approval and readiness

Before any service replacement, get fresh confirmation that the belt is stopped,
Bluetooth is disconnected, nobody is on the belt, and the current walk has been
resolved/preserved. Recheck the source hashes and every manifest preimage;
changed bytes hold activation for review. Do not infer present readiness from
old physical-test messages.

After that authorization, stop only the old PitPat application service and verify
its exact identity exited. Back up the closed SQLite database and any remaining
sidecars to a private directory (0700, files 0600), record hashes and run
`PRAGMA integrity_check` against the copied database. Preserve browser history.
Then apply the reviewed manifest and reload user systemd. Commands below are
procedural documentation, not an instruction to execute before approval:

```bash
.venv/bin/python scripts/install-omarchy.py --apply .superpowers/sdd/2026-10-15-dedicated-safety-process/install-plan.json
systemctl --user daemon-reload
systemctl --user start pitpat-safety.service
systemctl --user start pitpat-bridge.service
```

Run these from the reviewed checkout with its `.venv/bin/python` for the installer.
Verify each MainPID/cmdline/cwd, active/running states, HTTP200 at
`http://127.0.0.1:8766/`, two private socket paths and separate lock identities.
Startup must show no BLE connection, no owner/grant, and no motion. No login
startup, automatic restart, scan, connection or Start is implied by startup.
Resolve any cached QML activation through its own approved shell lifecycle.

## Physical results through October 19, 2026

These are supervised BA09-B observations of the installed dedicated safety
process, distinct from the earlier single-process failures and synthetic tests.

- October 15: application-only SIGKILL. Gabe reported the belt stopped by itself;
  the surviving safety process recorded Application connection lost and
  `stop_outcome=stopped_confirmed`.
- October 19: application-only SIGSTOP, initiated through the tray workflow at
  the lowest target. Gabe reported the belt stopped by itself; safety recorded
  Application health expired and `stop_outcome=stopped_confirmed`, with no
  uncertain writer. Only the identity-checked application was resumed.
- Gabe confirmed the belt stayed stopped after resumption. The tray initially
  displayed Safety unavailable/timeouts: the expired application IPC connection
  had closed, leaving its cached state stale. This was not safety-process death.
- Manual recovery succeeded via Find treadmill (reopens safety IPC), Claim
  recovery control, record resolution when offered, and Confirm Stop and
  acknowledge recovery. Gabe confirmed Stopped, Start enabled, and no automatic
  motion. Final independent readback showed a healthy application, ready
  authorization, no fault, tray ownership and stopped_confirmed.

Physical deceleration times were not measured. Private test receipts preserve
process identities, signals, exact fault/confirmation readback and user reports.
No safety test was uploaded as counted exercise. No code or shell changes were
needed for recovery. The current explicit reconnect path works, but discovering
it through Find treadmill is a usability gap; automatic recovery is not claimed.

These observations establish application-crash/freeze stopping and the tested
tray recovery only. They do not establish protection from safety-process
crash/freeze, Bluetooth/BlueZ loss, host sleep/power loss, or every remaining
acceptance item. Existing negative evidence and deferred tests remain intact.

## Separately armed physical acceptance

Each test needs fresh readiness and action-specific arming. Gabe stands beside an
empty belt, area clear, independent physical stop/power control ready. Gabe starts
only the minimum target. No agent starts the physical belt.

1. Verify normal Connect/Start/Pause/Stop, Stop during countdown and Stop & Disconnect.
2. Verify F11 helper Stop while the application is frozen, with safety running.
3. Kill only the identified application process. Record safety process survival,
   detection/write/confirmation times and Gabe's belt observation separately.
4. Freeze only the identified application process. Observe for at most five
   seconds after fault indication; physically stop immediately if needed.
5. Resume/restart application only after stopped confirmation. Verify no automatic
   motion. Claim recovery, resolve the interrupted record, confirm Stop and
   acknowledge recovery; confirm a separate Start is necessary in web and tray.
6. Verify tab/owner loss, ownership transfer while stopped, popup-close behavior,
   one canonical saved walk and deterministic export. Do not upload safety tests
   as counted exercise.

Any safety-process fault test needs its own explicit arming and physical fallback.
Do not describe it as protected by another watchdog. Bluetooth loss, host sleep,
BlueZ failure and power loss remain uncovered/unverified; actual sleep remains
deferred. The previous physical failures are not overwritten by simulator passes.

## Rollback procedure: stopped/disconnected belt required

Preserve failure evidence. After fresh physical-stop/disconnect confirmation,
stop the reviewed application and safety units and verify both exited. Apply the
same manifest's rollback from the reviewed checkout, then daemon-reload and start
only the restored legacy bridge. The old source checkout was preserved, so its
restored unit/wrapper still point to the accepted legacy implementation.

```bash
.venv/bin/python scripts/install-omarchy.py --rollback .superpowers/sdd/2026-10-15-dedicated-safety-process/install-plan.json
systemctl --user daemon-reload
systemctl --user start pitpat-bridge.service
```

Never run legacy and safety BLE owners together. Restore cached QML only through
an approved shell lifecycle. Verify dashboard HTTP200, no BLE connection/owner,
no automatic Start and intact records. Restore original source/configuration only
from the matching preimage; never overwrite drift or delete evidence. Restoring
legacy also restores its documented application-crash/freeze limitations.

## Manufacturer safeguard inquiry

The [unsent support inquiry](superpowers/specs/2026-10-15-dedicated-safety-process-design.md#12-treadmill-bluetooth-loss-safeguard-investigation)
requests BA09-B model/firmware-specific Bluetooth-disconnect and heartbeat-timeout
behavior. No setting or command is verified, no firmware was changed and no
message was sent. Exact stopped-device label/firmware evidence and a manufacturer
response/original manual are still needed. Keep serial numbers private.

## Automatic tray recovery follow-up — October 19, 2026

A bounded application reconnect now restores only private safety IPC observation
and health after it becomes unavailable. The existing application ticker schedules
one reconnect task; failed attempts are spaced by at least one second after each
bounded attempt. Concurrent explicit and automatic opens share one handshake.
Shutdown cancels the pending reconnect before closing the client. Reconnection
publishes the authoritative fault snapshot to tray/browser subscribers and fetches
bounded safety evidence for the interrupted record.

This supersedes the manual Find treadmill requirement for this software revision,
but not the historical physical result above. There is no automatic BLE scan,
Bluetooth connection, owner acquisition, fault acknowledgment, record resolution,
service restart or Start. Explicit recovery remains required.

Verification: the new persistent-plant freeze/resume test first failed against
unchanged production code, then passed without a discover/connect action. It
checks automatic recovery visibility, retained interrupted record, no motion
owner, latched fault and rejected Start. Full results: 118 Python tests and
90 JavaScript tests passed; offscreen Quickshell recovery/ownership passed;
compilation and diff checks passed. The shutdown test's first fixture stalled;
its unavailable-socket setup was corrected and the full suite then passed.
The BERF bounded preflight returned unknown_state and supplied no correctness
claim. Private preimages, patch, exact source hashes and logs are retained under
`.superpowers/sdd/2026-10-19-tray-recovery/` in the maintained worktree.

Activated October 19, 2026 after fresh user confirmation of a stopped,
disconnected belt and preserved record. Only the application service restarted;
the safety process retained its identity and no shell restart occurred. Startup
readback: healthy application, disconnected/unarmed, no owner/grant/fault,
no storage fault and HTTP 200. The prior application exceeded its 35-second
shutdown timeout and systemd terminated it before replacement; graceful-shutdown
cleanup remains a separate known issue. The revised automatic recovery path
has not yet been physically retested.

## Full-evidence tray frame fix — October 19, 2026

Physical retest of the automatic IPC reconnect produced an automatic stop and
independent stopped_confirmed result. After identity-checked resumption, Gabe
confirmed Claim recovery control appeared without Find treadmill and the belt
stayed stopped. This supersedes the earlier untested status for automatic IPC
reconnection, but did not complete the whole recovery interaction.

The subsequent tray flicker had a distinct observed cause: a live walk event
included the full safety evidence in both data and snapshot, reaching 87,110
characters. Service snapshots remained healthy; Quickshell rejected the frame
over its existing 65,536-character bound and repeatedly reconnected. Ordinary
live session summaries now exclude bulk safetyEvidence, just as they already
exclude sourceTelemetry and speedSamples. Canonical SQLite/export provenance is
preserved. A regression with 256 full-size protocol packets first reproduced
the oversized frame, then verified small live messages and intact stored samples.

All 119 Python tests and the actual offscreen Quickshell recovery/ownership
check passed; compilation and whitespace checks passed. The previous 90-test
JavaScript pass was reused with unchanged JS/CJS hashes. The bounded BERF
preflight returned unknown_state and supplied no correctness claim.

After explicit stopped-belt activation approval, authenticated Stop & Disconnect
was confirmed, a consistent private database backup passed integrity_check, and
only the application restarted. Safety retained its PID; no shell restart or
motion command occurred. Live application handshake measured 1,885 characters;
three passive tray status samples were authorized/connected with no error.
Bluetooth remains disconnected and the fault stays latched. Gabe subsequently confirmed the blinking was gone, the tray returned to
Stopped with Start enabled after explicit recovery, and the belt remained
stopped throughout. Final observation-only readback confirmed healthy
application/safety IPC, ready authorization, tray ownership and no fault or
storage fault. This completes the tested automatic IPC recovery visibility and
explicit tray recovery; the frame fix was verified on the preserved recovery
state without a further moving-belt freeze. Physical stop latency and unrelated
failure-domain limitations remain unchanged.
