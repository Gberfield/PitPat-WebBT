# Omarchy controls verification

Implementation date: October 15, 2026 (EDT).

The accepted Firefox source is preserved in the ignored Omarchy plan workspace,
including the original uncommitted Python, browser and export code. No Git commit
was made: repository author identity is not configured.

Final automated checks: 89 JavaScript tests, 68 Python tests with ResourceWarning
errors enabled, installed Quickshell synthetic integration, offline lock validation
and syntax/diff checks pass.

## Software evidence

- SQLite transactional history, unknown-field retention, ID conflicts, private
  permissions, restart tracking, individual counter resets and successive walks.
- A deliberately stalled commit cannot delay Stop; a failed commit blocks motion
  and requests Stop without publishing saved completion.
- Browser/native observer roles, stopped explicit ownership transfer, old queued
  motion cancellation, owner-only leases and authenticated global Stop.
- Private native Unix socket, peer UID, exclusive service lock before database,
  strict framing and protected HTTP history/import.
- Shared browser history preserves raw legacy/current storage on page load;
  imports wait for durable acknowledgement; conflicting IDs block export.
- Disposable-home installation and exact rollback refuse file drift and retain
  walk databases. No login startup is enabled.
- Installed Quickshell service tested offscreen with a synthetic treadmill:
  two views share one owner, removing one retains it, removing the last Stops
  and disconnects. Offscreen cannot instantiate the Wayland popup backend.
- Hidden native Wayland popup loading, Find and explicit simulator connect
  verified; connection remained stopped. Visual clipping/disabled-text issues
  were corrected in the installed source. Host/physical acceptance was subsequently
  reported by Gabe, as recorded below.
- Late-backend QML integration reproduces the installed Quickshell socket retry
  behavior and verifies recovery, two views and last-view Stop & Release.

## Activation readback

The upgraded manual user unit is active and the dashboard returns HTTP200 with
shared recording/observer capabilities. Runtime directory700; socket/lock/database
600; no login startup (unit is static); Hyprland reports no configuration errors.
The host plugin reports one view, authenticated native socket, available service,
no BLE connection and no owner. No physical scan or motion was issued by the agent.

The original unit generator quoted WorkingDirectory incorrectly; the actual
systemd-parser regression now passes and the corrected unit is running. The
installed shell retained old keepLoaded QML through rescans. Failed versioned
entry experiments were rolled back. Gabe then explicitly approved one Omarchy
shell restart; it completed, retaining app/profile/other desktop state. That
one-time exception is used; no further restart is authorized.

## User acceptance

On October 15, 2026 (EDT), Gabe reported **“all passes perfectly”** in response
to the supplied host/physical/export checklist. Task 5 is accepted on that report.
This is user-reported acceptance; the agent did not independently observe every
physical or export step. No additional Exercise Log upload was performed in this
acceptance update. The separate radio-loss/sleep/crash/power-loss follow-up stays
open. The checks below are retained for future regression testing.

## Accepted regression checklist

Keep the physical stop available. Use the minimum starting target.

1. Super+F9 opens the PitPat popup. Choose Find treadmill and explicitly select
   the BA09-B. Connecting alone must not start it.
2. Start, +/-0.1 MPH, Pause, Resume, Super+F11 Stop, and Stop & Disconnect.
3. Super+F10 starts/pauses only when the tray owns a healthy connection. Test
   Stop during countdown. Confirm reconnect never starts motion automatically.
4. While stopped, Take control in Firefox, then transfer back to the tray.
   Each new owner must explicitly Start. An observer can Stop but cannot move.
5. Close Firefox while it owns motion: requests Stop. Close Firefox while it
   observes a tray-owned walk: the walk continues. Popup closure retains tray
   control. Stop & Release ends it; unloading the last native view requests Stop.
6. Make one tray-controlled walk with Firefox closed. Reopen History and verify
   one record with one stable ID, then Prepare for Notion. Review/import its JSON
   through the established assistant workflow. Repeat export must not create a
   second counted exercise.

Notion task 5 is Done on the user-reported acceptance above.
Real radio loss, sleep, process crash and power failure remain unverified physical
stop cases; their separate safety follow-up stays open.

## Operation and recovery

Dashboard remains http://127.0.0.1:8766/. New bridge walks are stored under
`$XDG_STATE_HOME/pitpat/walks.sqlite3` (default `~/.local/state/pitpat/`). The native
socket is `$XDG_RUNTIME_DIR/pitpat/control.sock`. Simulation uses separate paths.
Storage faults block motion but never prevent authenticated Stop. Resolve
interrupted tracking explicitly; the choice itself never starts the belt.

`pitpat controls` starts the manually startable service and opens the popup.
`pitpat start-pause` routes only through the existing native controller.
`pitpat stop` uses a one-shot authenticated helper and waits for stopped telemetry.
`pitpat dashboard` and `pitpat history` open the browser.

Installation is staged with `scripts/install-omarchy.py --plan PATH`. Apply only
the reviewed plan after the belt is stopped/disconnected and current records are
resolved/exported. The plan contains exact preimages/postimages and hashes; keep
it private. Backups are under `~/.local/state/pitpat/install-backups/`.

Rollback with `scripts/install-omarchy.py --rollback PATH` after stopping and
exporting new shared walks. It restores unchanged installed files only and
preserves the database. Service management is separate: safely stop the upgraded
service, restore accepted source from the retained snapshot, daemon-reload and
restore the prior transient service if necessary. Never run two real bridges.
Current private rollback sequence (after stopping/exporting shared records):
`status-plan.json`, `socket-repair-plan.json`, `unit-repair-plan.json`, then
`install-plan.json`, each under the retained Omarchy plan workspace. Apply
`--rollback` newest-first. Failed runtime-entry/name experiments are already
rolled back. The active unit must be safely stopped before its file is restored.
No desktop shutdown is authorized; the single shell-restart exception was used.

## Dedicated safety process follow-up

A separate implementation is staged, with synthetic verification documented in
[dedicated safety acceptance](dedicated-safety-acceptance.md). The application and
sole BLE-owning safety process have distinct failure tests. The older acceptance
and failed physical observations above are retained as historical evidence; they
do not establish physical acceptance of the new process split. No live change or
new physical test has been performed for that split.
