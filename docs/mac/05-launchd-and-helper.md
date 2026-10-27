# 05 — launchd services and the `pitpat` desktop helper

**Depends on:** 01, 02 (and 04 for the safety app bundle). **Size:** medium.
**Touches real hardware:** no.

## Why

On Linux, two systemd *user* units run on demand
(`integration/systemd/pitpat-safety.service`, `pitpat-bridge.service`) with
`Restart=no`, no `[Install]` section (never at login), `UMask=0077`, and stop
timeouts of 10 s / 35 s. `bridge/desktop.py` starts them with `systemctl --user`
and talks to the tray with `omarchy-shell`. macOS needs launchd equivalents with
the **same policy**.

## launchd mapping

| systemd | launchd key |
|---|---|
| `Restart=no` | omit `KeepAlive` (default false) |
| no `[Install]` (not at login) | `RunAtLoad` = `false` |
| `UMask=0077` | `Umask` = `63` (integer, = 0o077) |
| `TimeoutStopSec=35` / `10` | `ExitTimeOut` = `35` / `10` |
| `WorkingDirectory=` | `WorkingDirectory` |
| `ExecStart=` | `ProgramArguments` array |
| `Wants=/After=pitpat-safety` | none in launchd; the helper starts safety first, then the bridge (the bridge already retries the safety socket for 3 s in `SafetyClient`) |
| journal | `StandardOutPath` / `StandardErrorPath` = `~/Library/Logs/PitPat/{safety,bridge}.log` |

Labels: `com.gberfield.pitpat.safety`, `com.gberfield.pitpat.bridge`.

Note: a plist in `~/Library/LaunchAgents/` is loaded at every login, but with
`RunAtLoad=false` and no `KeepAlive` it **does not start**; it only becomes
startable via `launchctl kickstart`. That matches "installed but not enabled".

## Steps

1. Templates in `integration/launchd/`:

   `com.gberfield.pitpat.safety.plist`
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0"><dict>
     <key>Label</key><string>com.gberfield.pitpat.safety</string>
     <key>ProgramArguments</key><array>
       <string>@SAFETY_APP_EXECUTABLE@</string>
     </array>
     <key>WorkingDirectory</key><string>@REPO@</string>
     <key>RunAtLoad</key><false/>
     <key>Umask</key><integer>63</integer>
     <key>ExitTimeOut</key><integer>10</integer>
     <key>ProcessType</key><string>Interactive</string>
     <key>StandardOutPath</key><string>@LOGS@/safety.log</string>
     <key>StandardErrorPath</key><string>@LOGS@/safety.log</string>
   </dict></plist>
   ```
   `@SAFETY_APP_EXECUTABLE@` = `.../PitPat Safety.app/Contents/MacOS/pitpat-safety`
   from plan 04 (so Bluetooth permission attaches to the bundle).

   `com.gberfield.pitpat.bridge.plist`: same shape, `ExitTimeOut` 35,
   `ProgramArguments` = `[@PYTHON@, -u, -m, bridge, --port, 8766]`.

   `ProcessType=Interactive` prevents App Nap / timer coalescing from delaying
   health challenges (250 ms interval, 2 s timeout). Keep it on both.

   Generate with `plistlib` in the installer (plan 07) rather than string
   substitution if that is simpler; either way, the committed templates must
   round-trip through `plutil -lint`.

2. `bridge/desktop.py`: split host actions by platform.

   ```python
   from .platform_paths import DARWIN, runtime_dir, open_url_command
   UID=os.getuid()
   def start_services():
       if DARWIN:
           for label in ('com.gberfield.pitpat.safety','com.gberfield.pitpat.bridge'):
               run(['launchctl','kickstart',f'gui/{UID}/{label}'])
       else:run(['systemctl','--user','start','pitpat-bridge.service'])
   ```

   `launchctl kickstart` without `-k` does nothing if already running — same as
   `systemctl start`. Operations on macOS:
   - `controls` → `start_services()`, then `open -b com.gberfield.pitpat.menubar`
     (plan 06's app; it opens its popover on launch or on reopen).
   - `start-pause` → `open -g 'pitpat://start-pause'` (URL handled by the menu
     bar app, plan 06). Reason: Start/Pause must come from the motion owner that
     holds the lease, exactly like the Linux tray IPC.
   - `stop` → unchanged: one-shot authenticated Stop straight to `safety.sock`.
     This is the important one; it must not depend on the menu bar app.
   - `dashboard` / `history` → `open_url_command(...)`.
   - New `services-stop` (both OSes): stop bridge first, then safety
     (`launchctl kill SIGTERM gui/$UID/<label>` / `systemctl --user stop`).
     Print a reminder that this does not stop the belt; it is for after Stop &
     Disconnect.
   Linux branches must keep issuing exactly the same commands as today.

3. `integration/bin/pitpat` works as is on macOS (POSIX sh). No change.

## Tests

`tests/test_bridge_desktop.py`: patch `bridge.desktop.run` and `DARWIN`; assert
the exact argv lists for each operation on each platform. Add a plist test that
loads both templates with `plistlib`, checks `RunAtLoad is False`, no `KeepAlive`,
`Umask == 63`, `ExitTimeOut` values, and labels. Run `plutil -lint` in that test
only when `shutil.which('plutil')`.

## Acceptance

- Simulator run through launchd on macOS (implementer may do this; it never
  touches Bluetooth): temporarily point the plists at
  `-m bridge.safety_main --simulate` / `-m bridge --simulate --port 8767`, load with
  `launchctl bootstrap gui/$UID <plist>`, `pitpat controls`, open the simulator
  dashboard, start/stop a synthetic walk, then `launchctl bootout` both. Record
  the commands and output in the PR.
- After `bootout`, nothing PitPat is left in `launchctl list | grep pitpat`.

## Don't

- Don't add `KeepAlive`, `RunAtLoad=true`, or a login item.
- Don't make the safety agent depend on the bridge agent or vice versa.
- Don't route `stop` through the menu bar app.
