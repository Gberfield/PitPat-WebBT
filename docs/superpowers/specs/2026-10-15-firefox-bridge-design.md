# Firefox support through a local Bluetooth bridge

Date: October 15, 2026 (Eastern Time)

Status: implemented and accepted by Gabe after Firefox simulator and physical control/tab-closure checks; see ../../firefox-bridge-acceptance.md for the limits of verified behavior.

Notion task: https://www.notion.so/3faa4f67016281fe93fde78cb0be563f

## Outcome and scope

Use the existing PitPat dashboard in Firefox on Gabe's Omarchy computer to control
the DeerRun PitPat BA09-B and record walks. Preserve MPH, miles, exercise Calories,
history, stable session identities, and the existing Notion export workflow.
Connecting, reloading, reconnecting, or restarting the service must never start
the belt automatically. Stop remains available during starting/countdown.

This change supplies the local service that a later Omarchy tray client can use.
It does not install a tray, edit desktop configuration, change Notion import
rules, upload health data, or promise a device-side communications watchdog.
Implementation stays in this chat, with no additional agents or model calls.

## Alternatives and decision

1. **Dedicated Python bridge using Bleak and BlueZ — selected.** A small local
   service owns BLE, command ordering and stop confirmation. Firefox communicates
   with that service through an authenticated loopback WebSocket. This supports
   future tray control and lets the service request Stop when a browser vanishes.
   It introduces Python dependencies and a second process to run and maintain.
2. **WebBT extension and native companion.** Potentially reuses the current Web
   Bluetooth calls with fewer application changes. Its Linux support is described
   as experimental, it still needs native software, and application-specific
   ownership and browser-loss stopping would remain outside our direct control.
3. **Continue using Chromium.** Keeps the working direct connection and adds no
   native service, but does not meet the Firefox or future tray requirements.

The machine has BlueZ 5.86 and an active Bluetooth service. Bleak and aiohttp are
not installed in the inspected Python environment. Use an isolated project
environment with locked dependencies; do not replace system Python packages.

## Components and boundaries

- A Python service uses aiohttp for static files and WebSockets, and Bleak for
  device discovery, connection, notifications and characteristic writes. It binds
  only to `127.0.0.1`; the normal URL remains `http://127.0.0.1:8765/`.
- A bridge controller owns the single treadmill connection, a serialized write
  queue, connection generations, telemetry validation, command bounds and an
  expiring controller lease. It accepts semantic commands, never arbitrary GATT
  addresses, UUIDs or byte payloads from a browser.
- A browser transport adapter presents connection events, raw telemetry and
  command results to the dashboard. Existing display parsing, units, session
  continuity, storage and exports continue to operate on the same measurements.
- Extract browser protocol helpers only where needed to isolate transport from
  the existing UI. The bridge independently validates the framing and safety
  fields it relies on. Shared synthetic fixtures verify both implementations
  against the same bytes and units.
- A simulator implements the BLE boundary without touching an adapter. Simulator
  mode must be explicitly selected at service startup and conspicuously labelled
  in the dashboard; it must never silently replace a failed real connection.

The Chromium direct Web Bluetooth path remains available on the static server.
When served by the bridge, both Firefox and Chromium use the bridge by default.
There is no automatic fallback to direct BLE after a bridge error, and no
automatic switching between transports while connected. The service cannot
coordinate a separately opened Chromium direct connection; document using only
one connection route at a time and report device-busy failures clearly.

## Browser flow and API contract

1. The page obtains bridge capabilities and an in-memory authorization token
   through a same-origin bootstrap endpoint. This does not scan, connect or move
   the treadmill. A static deployment without bridge capabilities uses the direct
   transport if Web Bluetooth exists, otherwise gives an actionable unsupported
   browser message.
2. Connect opens an authorized WebSocket and requests a bounded discovery scan
   for the existing service UUID. Display matching devices for explicit selection;
   never connect to an arbitrary nearby device automatically. Do not log device
   identifiers by default or persist them in public fixtures.
3. Selecting a device claims the controller lease and connects/subscribes. A
   second client gets an explicit busy response and cannot supersede the owner.
   Fresh validated telemetry is required before motion is enabled.
4. Versioned JSON messages carry request IDs and allowlisted operations:
   discover, connect, start, pause, set_speed, stop, stop_disconnect and release.
   Speed is an integer metric protocol value, 1000–6000 inclusive in increments
   of 100. The existing MPH UI rounds and converts before sending it. The service
   rejects malformed types, unknown operations and out-of-range values.
5. Events carry connection generation, event sequence, raw telemetry bytes in
   hex, explicit motion/connection state, safety outcomes and bounded error text.
   A write acknowledgement is distinct from a confirmed physical-state report.
   Old-generation responses and events cannot affect a replacement connection.
6. Browser heartbeats renew the lease every second. A monotonic six-second lease
   expiry, WebSocket closure or explicit release cancels queued motion and requests
   Stop. No automatic takeover or replay of a prior start/speed request occurs.

The bridge owns heartbeat replies to valid device notifications and all BLE
write serialization. The browser must not also reply to notifications when using
the bridge. Pending motion is invalidated by Stop, lease loss or link replacement.
Never replay failed commands automatically; use request IDs to reject duplicate
motion submissions within the active connection.

## Stop and failure semantics

Both transports require a successful Stop write and a fresh valid report of
stopped state **and zero speed**, received after that write begins. The bridge
uses the existing five-second deadline for the whole operation, including writes
that never resolve. Stop preempts queued motion and blocks new motion until the
operation resolves. A repeated Stop joins the current stop operation.

Stop & Disconnect closes BLE only after confirmation. If Stop fails or times out,
retain the connection when available, block motion, and display the persistent
physical-stop warning. A valid fresh stopped report can restore a known stopped
state; it must not retroactively label an earlier failed operation successful.

On browser loss the service attempts Stop independently of browser JavaScript.
If unconfirmed, retain BLE in an orphaned, motion-blocked state. A newly authorized
client may explicitly claim recovery control to request Stop; motion stays blocked
until fresh telemetry confirms stopped/zero speed. No new owner inherits pending
motion. A confirmed stop permits releasing the old lease and connection.

Invalid telemetry immediately blocks motion. Five seconds without valid telemetry
while connected also blocks motion and requests Stop; it cannot confirm Stop from
cached readings. Lost BLE, adapter failure and device-not-found states are distinct
from browser disconnection. On real BLE loss, clear the queue and mark motion
unknown. A reconnect requires explicit user action and fresh state.

Graceful service termination attempts the same bounded Stop while BLE is usable
and reports an unconfirmed result truthfully. Service crashes, event-loop stalls,
computer sleep, power loss and actual radio loss cannot guarantee Stop delivery.
Browser background throttling may expire the lease and stop a walk; choose this
conservative behavior over allowing unattended control. Do not claim that the
bridge is a hardware safety interlock. Keep the physical stop control available.

## Local authorization

- Bind only loopback and require the exact configured Host, including port, on
  static and API requests to resist DNS rebinding. Reject alternate hostnames.
- WebSocket upgrades require the exact dashboard Origin and a random per-process
  token in the first message before any operation is accepted. Reject missing,
  null or foreign origins; never place the token in URLs, logs or localStorage.
- The bootstrap response is same-origin, non-cacheable and has no control side
  effects. Do not enable CORS. Reject cross-site fetch metadata where supplied.
  Same-origin policy protects bootstrap contents from unrelated websites.
- Serve only intended dashboard assets, not the repository, private files, health
  exports or dependency environment. Disable framing, use a restrictive content
  security policy, bound message sizes and scan duration, and validate all inputs.
- An authorized WebSocket has only one controller lease. Authentication alone
  does not authorize a second client to start motion or replace its owner.

This protects against unrelated websites, not malicious local software or a
compromised dashboard origin. Future tray access needs its own deliberate local
authorization route; do not weaken browser-origin checks to anticipate it.

## History, interface and external assets

Walk history remains in the current browser's localStorage. Firefox does not
inherit Chromium storage: export/import is the supported transfer path. Preserve
stable IDs, backups and existing merge/conflict checks; do not silently merge or
overwrite histories. Bridge lifetime is not a new source of counted workouts.
After browser loss, the next visit uses the existing interrupted-session continuity
choice. Do not fabricate telemetry or a fully observed closing segment.

The dashboard identifies the selected transport, simulator status and connection
state. Show unsupported browser, bridge unavailable, controller busy and adapter
errors in the page, without requiring DevTools. Remove external MDL/font network
dependencies for core operation, replacing required tabs, controls, toast and
loading behavior with local HTML/CSS/JavaScript. Keep layout work limited to a
clear working dashboard and visible safety status.

## Verification and acceptance

Automated checks must cover:

- Existing units, session continuity, history preservation and Notion export.
- Both observed BA09-B telemetry formats, checksum/length errors, stale telemetry,
  metric/imperial measurements and parity of browser/bridge safety fields.
- Start/countdown, speed bounds, second-client rejection, duplicate motion
  requests, serialized writes and cancellation across connection generations.
- Fresh Stop confirmation versus stale or nonzero-speed reports, failed/hung
  writes, timeout, browser-loss Stop, lease expiry and recovery ownership.
- Host/Origin/token rejection, oversized/malformed messages and static-file
  exposure restrictions. Rejected requests must produce no BLE writes.
- End-to-end simulator flows over the actual HTTP/WebSocket boundary, including
  Firefox connect, telemetry, commands, reload, Stop & Disconnect and loss errors.

Hardware acceptance is separately user supervised: connect to the BA09-B, verify
live readings and a low-speed command, Stop during starting, Stop & Disconnect,
and browser-loss stopping while BLE remains available. Arrange each physical test
with the user present and the physical stop control ready. Automated tests never
scan or command the real treadmill. Do not mark task 4 complete until Firefox and
physical acceptance have actual evidence; mark untested scenarios explicitly.

## Delivery and rollback

Deliver reproducible environment setup, a foreground launch command, simulator
mode, diagnostics and the test commands. Do not replace the running static server
or change its port until the bridge is validated and the user can safely switch
with the belt stopped. Do not add automatic service startup in this task.

Rollback: stop/disconnect the belt, stop the bridge, and run the existing static
server in Chromium. Keep browser history and exports untouched. The bridge does
not write Notion, install system packages, or alter desktop bindings.

## References

- Existing dashboard code, README, and synthetic tests in this repository.
- Mozilla Web Bluetooth implementation tracking:
  https://bugzilla.mozilla.org/show_bug.cgi?id=674737
- Bleak Linux backend (BlueZ over D-Bus):
  https://bleak.readthedocs.io/en/stable/backends/linux.html
- WebBT alternative, native companion and experimental Linux status:
  https://addons.mozilla.org/en-US/firefox/addon/webbt/
