# macOS compatibility: plan index

Branch: `mac-compat`, based on `codex/dedicated-safety` @ `93f84b8`.
Written 2026-10-27 (America/New_York) from a real run of the test suite on
macOS (Apple Silicon, Python 3.14 via uv, Node 26).

## Goal

Run the full PitPat stack on a Mac with the same safety behavior as on Linux:

1. the independent safety process (`bridge.safety_main`), the sole BLE owner;
2. the application bridge (`bridge`), serving the Firefox/Chromium/Safari dashboard
   on `http://127.0.0.1:8766/`;
3. a native menu bar controller that replaces the Omarchy Quickshell tray;
4. on-demand services (launchd), installer with rollback, and docs.

The static `main` dashboard already works on macOS in Chrome/Edge (Web Bluetooth
is built in there). Safari and Firefox on macOS do not provide Web Bluetooth;
they need the bridge.

## What actually breaks on macOS today (measured)

`node --test --test-isolation=none`: **90/90 pass.**

Python, `uv run --frozen python -m unittest tests.<module>`:

| Module | Result on macOS | Cause |
|---|---|---|
| test_bridge_native | 5 errors | `/var` symlink in temp path; then `socket.SO_PEERCRED` missing |
| test_bridge_recorder | 26 errors | `/var` symlink in temp path |
| test_bridge_server | 1 error | `/var` symlink in temp path |
| test_bridge_store | 6 errors | `/var` symlink in temp path |
| test_omarchy_install | 4 errors | `/var` symlink; then `systemd-analyze` missing |
| test_safety_client | 2 errors | symlink; then `time.CLOCK_BOOTTIME` missing |
| test_safety_facade | 5 errors | symlink; then `CLOCK_BOOTTIME` |
| test_safety_ipc | 2 errors | symlink; then `CLOCK_BOOTTIME`, `SO_PEERCRED` |
| test_safety_native_frames | 1 error | symlink; then `CLOCK_BOOTTIME` |
| test_safety_processes | 7 failures | `CLOCK_BOOTTIME` kills the child processes |
| test_safety_units | 1 error | `/var` symlink in installer `checked()` |
| controller, desktop, protocol, safety_core, safety_health, safety_messages | OK | — |

Root causes, all verified on this Mac:

- **`/var`, `/tmp`, `/etc` are root-owned symlinks into `/private`.** `tempfile`
  dirs live under `/var/folders/...`, so `store.private_directory()` and the
  installer's `checked()` refuse every temp path.
- **`socket.SO_PEERCRED` does not exist.** macOS uses
  `getsockopt(SOL_LOCAL=0, LOCAL_PEERCRED)` returning a 76-byte `struct xucred`;
  `struct.unpack('IIh16I', raw)[1]` is the peer uid (verified: returns 501).
- **`time.CLOCK_BOOTTIME` does not exist.** On macOS `CLOCK_MONOTONIC` keeps
  counting through sleep (verified: it was ~124,000 s ahead of
  `time.monotonic()` after sleeps), so it is the equivalent.
- **Linux-only host integration:** `XDG_RUNTIME_DIR` / `/run/user/<uid>`,
  `xdg-open`, `systemctl --user`, `omarchy-shell`, Quickshell QML, Hyprland keys.
- **Unix socket path limit is 104 bytes** on macOS (108 on Linux). Long runtime
  paths fail with an unclear `OSError`.

## Work packages

Do them in order unless marked parallel. Each file is self-contained: scope,
exact files, steps, tests, acceptance criteria and things not to do.

| # | Plan | Issue | Depends on | Size |
|---|---|---|---|---|
| 01 | [Platform shim: clock, peer credentials, paths, opener](01-platform-shim.md) | #4 | — | S |
| 02 | [Private-path checks vs. macOS system symlinks; socket path length](02-path-safety.md) | #5 | 01 | S |
| 03 | [Portable test suite + GitHub Actions (Linux and macOS)](03-tests-and-ci.md) | #6 | 01, 02 | S |
| 04 | [Bleak/CoreBluetooth backend and Bluetooth permission](04-bluetooth-macos.md) | #7 | 01 | M |
| 05 | [launchd services and the `pitpat` desktop helper](05-launchd-and-helper.md) | #8 | 01, 02 | M |
| 06 | [Menu bar controller (replaces the Omarchy tray)](06-menu-bar-app.md) | #9 | 05 | L |
| 07 | [macOS installer with plan/apply/rollback](07-installer.md) | #10 | 05, 06 | M |
| 08 | [Docs and acceptance checklist](08-docs-and-acceptance.md) | #11 | all | S |

01–03 make the existing software pass on a Mac with the simulator. 04 is the
first step that touches real Bluetooth. 05–07 replace the Linux desktop
integration. 08 closes out.

## Ground rules for every package

- **Safety first.** The bridge can move a treadmill belt. Never connect to, start
  or stop a real treadmill. Use `--simulate` for everything. Physical acceptance
  is done only by the repository owner, after they say so in chat.
- **Do not change safety semantics**: lease timeouts, telemetry timeouts, Stop
  confirmation, recovery latching, single BLE owner, `Restart=no`/not at login.
  The Mac port must behave the same as Linux, not "better".
- **Do not change the BLE protocol** (`protocol.py`, `protocol.js`, packet bytes).
- **Linux must keep working.** Every platform change is a branch on
  `sys.platform`, with Linux behavior byte-for-byte unchanged. Run the full suite
  and keep the Linux CI job green (plan 03).
- **Match the code style.** The bridge is dense, terse Python with few comments;
  keep new code in that style. No new runtime Python dependencies without the
  owner's approval (current: `aiohttp`, `bleak`).
- One package = one commit (or a few) on `mac-compat` = one PR against
  `mac-compat`. Do not push to `main` or `codex/dedicated-safety`.
- After each package, run:

  ```sh
  node --test --test-isolation=none
  uv run --frozen python -m unittest discover -s tests -p 'test_*.py'
  uv lock --check
  git diff --check
  ```

  and paste the summary lines into the PR description.
