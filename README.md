# PitPat Treadmill Web Dashboard

A web-based dashboard to control and monitor a PitPat treadmill via Bluetooth. This tool provides real-time data visualization and treadmill control.

## Prerequisites

- Firefox or Chromium with the local bridge described below; or Chromium with
  Web Bluetooth for the original direct connection route.

## Firefox and the local Bluetooth bridge

From this checkout, prepare the isolated Python environment and run the bridge:

```sh
uv sync --locked
uv run --frozen python -m bridge.safety_main
```

Leave the safety process running. In a second terminal:

```sh
uv run --frozen python -m bridge --port 8766
```

Open [the bridge dashboard](http://127.0.0.1:8766/) in Firefox. Click **Connect**,
then select the treadmill from the local device list. Connecting never starts the
belt. The bridge needs the existing BlueZ service and permission to use the local
Bluetooth adapter. The project environment contains aiohttp and Bleak; it does
not replace system Python packages. No browser extension is needed.

If the existing static server is still using port 8765, leave it running while
testing the bridge separately:

```sh
uv run --frozen python -m bridge --port 8766
```

Use [the separate bridge dashboard](http://127.0.0.1:8766/). Before connecting it,
stop and disconnect the direct Chromium connection. Use one connection route at
a time. The bridge permits one controller; a second client reports busy rather
than taking over. Do not reload a live walk to change servers or transports.

To test without hardware, start the explicitly labelled simulator:

```sh
uv run --frozen python -m bridge.safety_main --simulate
```

In a second terminal:

```sh
uv run --frozen python -m bridge --simulate --port 8767
```

The [simulator dashboard](http://127.0.0.1:8767/) never touches Bluetooth. It uses
its own browser origin/history, so its synthetic walks do not enter the normal
dashboard's storage. Do not import simulator exports as real exercise.

The backend requests Stop if its controlling browser closes or fails to renew a
six-second lease. It also blocks motion and requests Stop after five seconds
without valid telemetry. Background throttling can therefore stop a walk. An
unconfirmed Stop keeps BLE open when available; **Recover Stop control** lets a
new client explicitly recover that orphaned connection. Motion remains blocked
until fresh telemetry reports stopped and zero speed. Intentional disconnect
still requires a successful Stop write and a fresh stopped/zero-speed report.

This is best-effort browser-loss stopping while the bridge and BLE link remain
alive. The separate safety process attempts Stop on application-bridge crash or freeze
while its own process and BLE remain usable. Radio loss, computer sleep/power loss
and failure of the safety process cannot guarantee Stop delivery. This is not a
hardware safety interlock. Supervised application-crash/freeze stopping and tray recovery have passed; these
results do not cover failure of the safety process or transport. See
[dedicated safety acceptance](docs/dedicated-safety-acceptance.md).

Firefox and Chromium have separate localStorage. Export history from Chromium
and import that JSON in Firefox to retain existing session IDs. Reimports merge
through the current ID/conflict checks; do not clear either browser's history.
The bridge does not store Notion credentials or upload anything to Notion.

Only `127.0.0.1` is supported; use that exact address rather than `localhost`.
The API checks the exact Host/Origin and a short-lived in-memory token. If the
service restarts, reload its page to obtain a new token. **Connection unavailable**
means start/check the bridge; **No treadmill found** means check power, adapter
and the other Bluetooth connection; **Controller busy** means stop/disconnect
the owner first. Errors appear in the dashboard; no DevTools setup is required.

Stop/disconnect the treadmill before terminating the foreground bridge with
Ctrl+C. Graceful shutdown attempts Stop, but an unconfirmed result still requires
the physical stop control. To roll back, stop the bridge and use the static
Chromium route below. The foreground commands do not install desktop integration. Optional Omarchy
integration is described below; neither service is enabled at login.

Run the software checks (Python socket tests use ephemeral loopback ports):

```sh
node --test --test-isolation=none
uv run --frozen python -m unittest discover -s tests -p 'test_*.py' -v
uv lock --check
git diff --check
```

See [acceptance evidence](docs/firefox-bridge-acceptance.md) and the
[Firefox simulator checklist](tests/firefox-simulator-checklist.md). Software
simulation does not establish physical BA09-B acceptance.


## macOS

Chrome and Edge on macOS include Web Bluetooth, so the static Chromium route below
works unchanged. Safari and Firefox on macOS do not; use the local bridge.

The foreground bridge uses the same commands as Linux:

```sh
uv sync --locked
uv run --frozen python -m bridge.safety_main
```

In a second terminal:

```sh
uv run --frozen python -m bridge --port 8766
```

The safety process is the only Bluetooth owner. On first connect, macOS asks
whether the terminal app running it may use Bluetooth. If it is denied, Connect
reports **Bluetooth permission denied** with the System Settings location. To test without hardware, use the same
`--simulate` commands and [simulator dashboard](http://127.0.0.1:8767/) as Linux.

macOS paths:

| Purpose | Path |
| --- | --- |
| IPC sockets | `~/Library/Application Support/PitPat/run/pitpat` (simulator: `pitpat-simulator`) |
| Walks and state | `~/Library/Application Support/PitPat/state` |
| Installed service logs | `~/Library/Logs/PitPat/` |

### Installed services and menu bar app

Build the menu bar app and the PitPat Safety launcher, then preview and apply the
per-user installation:

```sh
scripts/build-menubar.sh
uv run --frozen python scripts/install-macos.py plan
uv run --frozen python scripts/install-macos.py apply --manifest ~/.local/state/pitpat/install-macos.json
```

`plan` writes nothing. `apply` installs two launchd agents in
`~/Library/LaunchAgents`, `PitPat Safety.app` and `PitPat.app` in
`~/Applications`, and `~/.local/bin/pitpat`. It ad-hoc signs both apps and records
exact per-file backups in the manifest. It refuses drift and never uses sudo,
`/Library` or login items. It prints, but does not run, the next steps:

```sh
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.gberfield.pitpat.safety.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.gberfield.pitpat.bridge.plist
open ~/Applications/PitPat.app
```

Bootstrapping loads the agents without starting them. They start on demand only:
`pitpat controls` starts both and opens the menu bar app. Opening the app alone
does not start them. They have no automatic restart and are not started at login. With the installed safety process, macOS asks
for Bluetooth permission for **PitPat Safety** rather than for a terminal or Python:
the app's small launcher starts the safety process as its child, so macOS credits
the signed app. Each install re-signs the app, so macOS may ask again after one.

The PitPat menu bar item replaces the Omarchy tray popup with the same controls
and wording. Closing its popover retains control; **Quit PitPat menu bar**
releases it. Hotkeys:

| Keys | Action |
| --- | --- |
| ⌃⌥⌘P | Open the controls popover |
| ⌃⌥⌘Space | Start/Pause through the menu bar owner, like `pitpat start-pause` |
| ⌃⌥⌘. | Stop through the safety process, like `pitpat stop` |

Stop and `pitpat stop` go straight to the safety process, without the bridge or
the menu bar lease. If either reports Stop unconfirmed, use the physical stop
control. With no treadmill connected, Stop cannot be confirmed and reports so. `pitpat dashboard` and `pitpat history` open the dashboard.

The safety limits described above apply unchanged: Stop on application crash or
freeze depends on the safety process and the Bluetooth link staying alive; radio
loss, power loss and failure of the safety process cannot guarantee Stop; this is
not a hardware safety interlock. In addition, **macOS sleep, lid close and App Nap
are not verified**. Keep the physical stop control available.

To roll back, choose **Stop & Disconnect** first, then:

```sh
pitpat services-stop
launchctl bootout gui/$(id -u)/com.gberfield.pitpat.bridge
launchctl bootout gui/$(id -u)/com.gberfield.pitpat.safety
uv run --frozen python scripts/install-macos.py rollback --manifest ~/.local/state/pitpat/install-macos.json
```

`services-stop` does not stop the belt. Rollback refuses while either service is
running or loaded and restores the previous bytes of every installed file. It
keeps logs, walks and state. See [macOS operations](docs/macos-operations.md) for
updates and troubleshooting, the [macOS acceptance checklist](docs/macos-acceptance.md)
for results, and the [documentation index](docs/README.md) for everything else.

## Upstream demo

The [original upstream demo](https://keirany.github.io/PitPat-WebBT/) is hosted by keirany. It is the static
Web Bluetooth dashboard only, separate from this fork's bridge, safety process and
desktop integrations.

## American units

The local dashboard displays speed in MPH, distance in miles, and exercise Calories as
`Cal` (one food/exercise Calorie equals one kcal; numeric energy values stay the same).
Metric and imperial device notifications are both supported. Raw telemetry keeps its
original values and units.

The speed slider accepts 0.62–3.73 MPH. Commands still use the existing metric
protocol and its 1–6 kph limits. Targets round to the nearest 0.1 kph, then clamp
to those limits; the displayed target updates to the resulting MPH. The ±0.1 MPH
buttons use the same conversion and rounding. For example, selecting 2.00 MPH
requests 3.2 kph and displays approximately 1.99 MPH. Physical treadmill behavior
still requires user verification.

Existing history migrates to schema version 2 on page load. Each converted record
keeps `originalMeasurements`; records with unknown speed units keep their original
speed rather than guessing. JSON exports remain arrays and include this metadata.
Before the first history rewrite, the exact original JSON is saved in browser
localStorage as `treadmill_sessions_backup_v1`; subsequent writes never overwrite
that backup. If the backup cannot be saved, the original history is not replaced.
New sessions also retain the latest notification in `sourceTelemetry`; this is
not a full telemetry time series.

To roll back, stop and disconnect the treadmill, export any new sessions, and close
other dashboard tabs. With the app closed, restore the previous source files. On
the next visit, use browser DevTools → Application → Local Storage for this origin
to copy the backup value into `treadmill_sessions` before using history. This
restores only the pre-migration snapshot, so retain the newer export separately.

## Local run and checks

Serve the project with `python3 -m http.server 8765 --bind 127.0.0.1` and visit
[the local dashboard](http://127.0.0.1:8765/) in a Web Bluetooth-capable browser.
On Chromium for Linux, Web Bluetooth may require enabling Experimental Web Platform
features in `chrome://flags/#enable-experimental-web-platform-features` and relaunching.

Run the dependency-free unit and dashboard integration checks with:

```sh
node --test --test-isolation=none
node --check treadmill.js
```

Tests use synthetic Bluetooth notifications and isolated in-memory browser storage;
they do not send commands to hardware.

## Walking records and Notion

History → **Prepare for Notion** previews finished/interrupted walks. Choose
**Download Notion export**, then provide the file in chat for assistant-assisted
import into your existing Exercise Log. This browser button only downloads a file.
See [NOTION_IMPORT.md](NOTION_IMPORT.md) for the mapping, deduplication, and verified
import procedure. No Notion token is stored in the browser.

New walking records retain distance, device duration, steps, Calories, sampled
average/maximum speed, timestamps, a compact speed trace, and their stable ID.
Pause/resume stays in one record. Counter resets preserve the last nonzero totals.
Disconnects and reloads require a tracking-continuity choice before recording
continues. That choice does not control treadmill motion. Old records receive
persistent IDs and retain any unknown fields; distance can be recovered from
previously saved raw telemetry where its unit is known.

History import now merges new records. Reimporting the same IDs does not duplicate
them, and conflicting records block the import rather than overwriting history.
Use one dashboard tab for tracking; simultaneous writers are not coordinated.

## Stop and disconnect behavior (BA09-B)

**Stop & Disconnect** now sends Stop through the serialized GATT writer, cancels
queued motion, and waits up to five seconds for both the write and a fresh valid
notification reporting stopped state and zero speed. Only then does the app close
Bluetooth. A failed write, missing confirmation or lost link produces a persistent
physical-stop warning; the app keeps Bluetooth open when it can. Stop also sends
immediately and stays available while starting. It does not wait for the next
notification to send its command.

The BA09-B continued moving after a disconnect reported by the user. **Automatic
physical stopping after unexpected Bluetooth loss, tab/browser closure, computer
sleep or an app crash is not verified and is not guaranteed by this web app.**
After a true link loss, the browser cannot deliver a Stop command. A verified
device-side communication watchdog or an independent stop mechanism is required
for that guarantee. Keep the treadmill's physical stop control available. The
app reports connection loss as an interruption, clears pending motion, and does
not claim that the belt stopped.

Stop confirmation validates the telemetry frame (observed BA09-B header, length,
XOR checksum and terminator) as well as stopped state and zero speed. This is
device-reported state, not an independent measurement of belt motion. Validation
here uses synthetic Bluetooth tests; real stop/disconnect behavior still requires
user acceptance. Do not reload the dashboard while relying on it to stop the belt.

The observed formats include 53-byte idle reports beginning with `0x66` and
reports beginning with `0x67`. Both use the same basic speed/state fields. Valid
idle reports receive the normal heartbeat reply; rejecting them would block the
controls and prevent stop confirmation. Invalid reports keep motion blocked and
leave the last displayed readings explicitly marked stale.

### Omarchy controls and shared recording

The `gabe.pitpat` Quickshell plugin adds a native popup beside the system tray.
Super+F9 opens controls, Super+F10 requests Start/Pause through the tray owner,
and Super+F11 requests Stop. Connect and choose devices explicitly. Startup,
reconnection and taking ownership never start the belt.

New bridge walks are recorded once in private SQLite storage, including when
Firefox is closed. Firefox can observe a tray-controlled walk; only the motion
owner renews its lease. Closing the controlling browser or losing the last
native controller requests Stop. Closing a popup retains native control.

The original direct Chromium recorder remains available when no bridge endpoint
exists. Browser history stays local and is combined with shared records for
History and Prepare for Notion; there is no silent upload or migration. Conflicts
need explicit review. A failed save blocks motion and requests Stop independently
of disk I/O. Actual Bluetooth loss cannot guarantee a physical stop.

Installation templates live in `integration/`; `scripts/install-omarchy.py`
stages exact per-file backups, detects drift and supports rollback. It installs
a manually startable user service without enabling login startup. See
[verification, physical checks and rollback](docs/omarchy-controls-acceptance.md).

### Recovery with the dedicated safety process

A fault stays latched after the belt reports zero. Claim recovery control, resolve
the interrupted record, then choose **Confirm Stop and acknowledge recovery**.
A separate Start is required; startup and reconnect never start motion.
Super+F11 sends Stop directly to the safety process even if the application is
unavailable. If it reports Stop unconfirmed, use the physical stop control.
A timed-out motion write remains ambiguous; physically stop and power-cycle the
treadmill before reconnecting rather than treating cancellation as device Stop.
The two services start on demand, have no automatic restart and are not enabled
at login. The two-service installation and application crash/freeze stopping have been
physically checked on the BA09-B. After a freeze, application-to-safety IPC
reconnects automatically so recovery controls reappear without discovery.
Bulk safety evidence stays in saved walks/exports rather than live UI messages.
The explicit recovery sequence and separate Start remain required. See
[current acceptance and remaining limits](docs/dedicated-safety-acceptance.md)
and the [closeout handoff](docs/closeout-handoff.md).

## License

See [LICENSE](LICENSE).
