# macOS support: acceptance checklist

Date: October 28, 2026 (EDT).

Status: software acceptance complete in simulator mode on one Mac (Apple Silicon,
macOS 27, Python via uv, Node 24 in CI). **Physical acceptance has not started.**
Nothing here has connected to, scanned for, started or stopped a real treadmill.

Scope: the `mac-compat` work packages in [docs/mac](mac/README.md) (PRs #12–#18 and
this checklist). Linux behavior is unchanged; the Linux checklists remain
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
- [ ] Simulator walk via hotkeys: **not run**. This session could not post global
  key events or take screenshots. The hotkey actions call the same code the
  simulator test exercises; the key registration itself is unverified.
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
- [ ] `pitpat controls` / `pitpat start-pause` routing to an app in `~/Applications`:
  **not covered.** LaunchServices does not register apps under `/private/tmp`, so
  the throwaway install could not receive `open -b` or `pitpat://` URLs. Both
  worked from the build copy during the menu bar work (#17).

## Physical (owner only)

Run only with the belt clear and the physical stop control within reach. Record
date, time (America/New_York) and what happened for each item, including
failures. Do not check an item that was not physically observed.

- [ ] Install on the real home (`plan`, `apply --manifest`, the printed
  `launchctl bootstrap` and `open` steps); `pitpat controls` opens the popover.
  October 29, 2026, with the script launcher (before #20): apply, both bootstraps
  and `pitpat controls` worked; both agents ran and the menu bar app opened from
  `~/Applications`. Repeat with the Swift launcher.
- [ ] Bluetooth permission prompt names **PitPat Safety** on first Connect;
  allowing it lets discovery find the treadmill. October 29, 2026, script
  launcher: **failed.** Privacy & Security → Bluetooth listed only `python3.14`;
  the script `exec`s Python, so macOS credited Python. Fixed by the Swift
  launcher (#20); repeat after reinstalling.
- [ ] Connect and telemetry without Start: readings update; the belt does not move.
  October 29, 2026, script launcher: owner observed Connect and updating readings;
  Start was not pressed. Repeat with the Swift launcher.
- [ ] Start at minimum speed from the menu bar, then Stop from the menu bar;
  Stop is confirmed.
- [ ] Stop via ⌃⌥⌘. during a minimum-speed walk; Stop is confirmed.
- [ ] Application-crash stop on an empty belt: `kill -9` the bridge mid-walk; the
  safety process stops the belt. Record the time to stop.
- [ ] Application-freeze stop: `kill -STOP` the bridge mid-walk; the belt stops;
  after `kill -CONT` recovery is required and nothing restarts motion.
- [ ] Mac sleep during a walk (lid close or Apple menu → Sleep): **expected: not
  guaranteed.** Record what the belt did and what the app showed on wake. Do not
  claim support from one result.
- [ ] Rollback on the real home: Stop & Disconnect, `pitpat services-stop`,
  `launchctl bootout` both labels, `rollback --manifest`; compare against a
  listing taken before the install.
