# macOS support: acceptance checklist

Date: October 28, 2026 (EDT); physical results October 29, 2026 (EDT).

Status: software acceptance complete in simulator mode on one Mac (Apple Silicon,
macOS 27, Python via uv, Node 24 in CI). Physical acceptance by the owner on the
same Mac passed every item except Mac sleep, which was not run because system
sleep is disabled on that Mac. The software items ran in simulator mode only; the
physical items were run by the owner, with the implementer sending the crash and
freeze signals at the owner's request.

Scope: the `mac-compat` work packages in [docs/mac](mac/README.md) (PRs #12–#19),
and the Swift safety launcher (#21). Linux behavior is unchanged; the Linux checklists remain
[dedicated safety acceptance](dedicated-safety-acceptance.md) and
[Omarchy controls acceptance](omarchy-controls-acceptance.md).

## Software (implementer)

Every item below ran with `--simulate` or disposable homes only.

- [x] Test suites per OS, from CI on the installer merge
  ([run 40769571705](https://github.com/Gberfield/PitPat-WebBT/actions/runs/40769571705)):
  - ubuntu-latest: Node 91/91; Python 152 tests OK (2 skipped: no `plutil`, and the
    macOS `/private` system-link test). The installer tests use a no-op signer there.
  - macos-latest: Node 91/91; Python 152 tests OK (1 skipped: `systemd-analyze`);
    Swift 8 tests, 1 skipped (the opt-in simulator walk), 0 failures.
  - The same counts locally on macOS.
- [x] Simulator walk via browser: the README's foreground `--simulate` commands,
  dashboard on port 8767. Connect → choose **SIMULATOR — no physical treadmill**
  → Start (0.62 MPH, Running) → Stop (0.00 MPH, Stopped) → **Stop & Disconnect**
  (bridge reports disconnected, no owner, no fault).
- [x] Simulator walk via the menu bar controller: the opt-in `SimulatorTests`
  drive the app's `Service` as `tray` against the installed launchd services:
  connect, walk, pause, walk, Stop & Disconnect, quit releases control. Passed
  (20.5 s). The installed `PitPat.app` launched and connected to `control.sock`.
- [x] Direct safety Stop (the ⌃⌥⌘. and `pitpat stop` path): `SafetyStop` against
  `safety.sock` returned confirmed Stop during a simulated walk. With no treadmill
  connected, `pitpat stop` reports **Stop unconfirmed** (exit 1) and the next
  connection starts in recovery, as on Linux.
- [x] Hotkeys: **not run in simulator mode** (this session could not post global
  key events). Covered on October 29, 2026 by the physical hotkey item below.
- [x] Recovery after `kill -STOP` of the bridge: with the menu bar walking, the
  bridge was frozen; the controller-lost warning and timeout error appeared; after
  `kill -CONT` it reconnected into recovery, claimed recovery, resolved the record
  and acknowledged it without Start.
- [x] Installer plan/apply/rollback (`scripts/install-macos.py`, throwaway home):
  `plan` wrote nothing; `apply` installed and ad-hoc signed both apps
  (`codesign --verify --deep --strict` passed); the literal `launchctl bootstrap`
  lines loaded both agents as **not running**; rollback refused while loaded and
  while running; after `pitpat services-stop` and `launchctl bootout`, rollback
  left `~/Library/LaunchAgents`, `~/Applications` and `~/.local/bin` byte-identical
  to the pre-install listing, and kept logs, walks and state.
- [x] `pitpat controls` / `pitpat start-pause` routing to an app in `~/Applications`:
  not covered by the throwaway install (LaunchServices does not register apps
  under `/private/tmp`). Covered on October 29, 2026 by the real-home install:
  `pitpat controls` started both agents and opened `~/Applications/PitPat.app`.

## Physical (owner only)

Run only with the belt clear and the physical stop control within reach. Record
date, time (America/New_York) and what happened for each item, including
failures. Do not check an item that was not physically observed.

- [x] Install on the real home (`plan`, `apply --manifest`, the printed
  `launchctl bootstrap` steps); `pitpat controls` opens the popover. First with the
  script launcher (before #20), then again after #21 with the Swift launcher: both
  apps passed `codesign --verify --deep --strict`, both agents loaded as not
  running, and `pitpat controls` started both and opened the menu bar app.
- [x] Bluetooth permission prompt names **PitPat Safety** on first Connect;
  allowing it lets discovery find the treadmill. Script launcher: **failed**;
  Privacy & Security → Bluetooth listed only `python3.14`, because the script
  `exec`s Python and macOS credited Python (#20). Swift launcher (#21): the
  prompt named **PitPat Safety**, and Connect found the treadmill.
- [x] Connect and telemetry without Start: readings updated; the belt did not
  move. Observed with both launchers.
- [x] Start at minimum speed from the menu bar, then Stop from the menu bar;
  Stop confirmed. The owner then walked a session controlled over Bluetooth.
- [x] Stop via ⌃⌥⌘. during a minimum-speed walk: Stop confirmed. ⌃⌥⌘Space
  started and paused the belt; ⌃⌥⌘P opened the popover.
- [x] Application-crash stop on an empty belt (1.0 mph, 0 steps): `kill -9` of the
  bridge at 3:33:35 PM; the safety process kept running and the belt stopped.
  Time to stop was not measured. The next Connect required confirming Stop and
  acknowledging recovery.
- [x] Application-freeze stop on an empty belt (1.0 mph, 0 steps): `kill -STOP`
  of the bridge at 3:44:55 PM. The safety process recorded `Application health
  expired` with outcome `stopped_confirmed`. After `kill -CONT` at 3:45:10 PM the
  bridge was connected, in recovery and blocked, at speed 0 with the walk marked
  interrupted; nothing restarted motion.
- [ ] Mac sleep during a walk (lid close or Apple menu → Sleep): **expected: not
  guaranteed.** **Not run:** system sleep is disabled on this Mac. Run once
  wherever sleep is enabled; do not claim support from one result. App Nap is also
  unverified.
- [x] Rollback on the real home: after Stop & Disconnect (bridge reported
  disconnected), `pitpat services-stop`, `launchctl bootout` both labels and
  `rollback --manifest` removed `~/Applications` and every PitPat file in
  `~/Library/LaunchAgents`, and kept logs, walks and state. Checked by listing,
  not against a byte listing taken before the install. The rolled-back manifest
  was kept as `install-macos.rolled-back-20261029.json`.
