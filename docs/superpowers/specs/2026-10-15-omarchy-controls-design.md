# Omarchy PitPat controls and shared walk recording

Date: October 15, 2026 (Eastern Time)

Status: written specification and implementation plan approved by Gabe; implementation underway.

Notion task: https://www.notion.so/3faa4f6701628100b668cb646791755e

## Purpose and accepted behavior

Start a walk with a few deliberate clicks or keys, see current treadmill/session
measurements, and control the BA09-B from the Omarchy bar. Reuse the accepted
Firefox bridge, validated protocol, American units and Notion export format.
Every new physical walk has one canonical record regardless of which interface
controls or displays it. Existing browser history and its backups survive.

Gabe approved a native bar icon/popup, explicit Firefox/tray ownership, the
proposed shortcuts below, and moving new walk recording into the bridge. A
Firefox-controlled walk still stops when its controlling tab closes. A
tray-controlled walk continues with Firefox closed, because the tray remains its
controller. Losing the tray controller requests Stop. Service startup, opening
the popup/dashboard, reconnecting or taking control never starts the belt.

The native component is a Quickshell bar widget beside the existing tray, not a
replacement for `gabe.tray`. No desktop, shell or browser restart/shutdown is part
of installation. Work stays in this chat, without additional agents/model calls.

## Architecture and alternatives

**Selected: user-owned Quickshell widget plus the existing Python bridge.** This
matches the installed Omarchy shell and uses local popup/keyboard conventions.
The bridge remains the sole BLE writer and becomes the recorder of new walks.
A private local IPC channel serves native status/control without weakening the
browser's Host, Origin or token checks.

A standalone StatusNotifier application would work with `gabe.tray`, but adds a
separate GUI process/toolkit and lifecycle. A dashboard-only launcher/keybinding
is smaller, but cannot provide background tray control or reliable tray-only
recording. Neither is selected for this task.

Installed evidence: `quickshell` is present; `shell.json` uses `gabe.tray`; its
manifest declares a user-owned bar widget and its QML uses Quickshell.Io and the
native popup conventions. Read those installed interfaces again when planning
implementation; do not change packaged files under `/usr/share/omarchy/`.

## UI and keyboard actions

Add a single `gabe.pitpat` bar widget near the existing tray. Its icon/tooltip
distinguishes service unavailable, disconnected, connecting, connected,
starting, walking, paused, stopping and motion unknown. Simulator mode must be
prominent and must use a separate recorder/socket from real mode.

The popup shows:

- The current controller: Firefox, tray, or none, and whether this view is read-only.
- Speed and target in MPH, distance in miles, Calories as Cal, steps and duration.
- Open dashboard/history, bounded Connect/device selection, Take control,
  Start/Pause, Stop, Stop & Disconnect, and +/-0.1 MPH controls.
- Persistent failed/unconfirmed Stop and disconnected-motion warnings.
- A deliberate Stop & Release action to end native control without hiding a
  moving treadmill behind a closed menu. If confirmation fails, retain the
  connection/recovery affordance rather than pretending release succeeded.

Closing only the popup does not release tray control. Removing/unloading the
widget, quitting the controller or losing its IPC connection invokes the
owner-loss Stop path. A shell reload may therefore stop a tray-controlled walk;
document this conservative behavior. Never restart the shell to activate it.

Proposed bindings, approved in the conversational design:

| Shortcut | Action |
| --- | --- |
| Super+F9 | Open/focus PitPat controls; start the service on demand if needed |
| Super+F10 | Start/Pause only when this native controller owns a healthy connection |
| Super+F11 | Request Stop, including while starting |

Current binding discovery found these unused; recheck both user and live/default
bindings immediately before installation. Do not silently override a newly
conflicting shortcut. Keep Super+Shift+F12, the Codex desktop emergency stop,
unchanged. Start is a deliberate press, not a repeated key-down action; disable
motion controls without a known current state. Start from the minimum target on
a newly established control session; never inherit an old client's pending speed.

Use the same MPH conversion, nearest 0.1 kph quantization and 1000–6000 protocol
bounds as the dashboard. Show the actual rounded target. Stop is always available
to an authenticated local user when BLE is available, including during countdown.

## Controller ownership and observation

Extend the service to distinguish observers from the one motion controller.
Both native IPC and browser clients can observe the same validated telemetry,
owner state and session ID. Observers do not renew the owner's lease, write
heartbeats or make local copies of the live recording.

Connecting requires explicit device selection. If already connected, Take
control is an explicit command, allowed only with a fresh stopped/zero-speed
report, no Stop operation in progress and no unresolved safety fault. Transfer
atomically invalidates old queued motion, assigns the new owner, and starts its
lease; the previous owner becomes a visibly read-only observer. Reject transfer
while starting, walking or paused, and whenever motion or stopped state is
otherwise unconfirmed.
There is no automatic takeover, reconnect, Start replay or control transfer when
an observer opens/closes.

Only the owner may Start, Pause or adjust speed. Authenticated Stop is the
explicit safety exception: a local user can request it from either interface
without first taking ownership. All such commands still use the one serialized
BLE writer. Stop & Disconnect is a deliberate Stop followed by disconnection
only after confirmation; it clears ownership for every view.

The owner renews its lease every second; six seconds without renewal requests
Stop. The native lease connection must survive closing the popup but not widget
unload. Use one native control connection per shell runtime even with multiple
monitors. Native observers and extra browser tabs cannot keep a missing owner
alive. Preserve generation and request-ID guards across both transports.

The accepted five-second Stop write-plus-fresh-report deadline, five-second
valid-telemetry timeout and orphan recovery rules remain binding. A failed Stop
keeps BLE open where possible and blocks motion. Taking ordinary control cannot
bypass explicit recovery. Real BLE loss, sleep, bridge crashes and power loss
still cannot guarantee physical stopping; preserve those limits in both UIs.

## Native IPC authorization

Add a local Unix-domain socket under the service user's XDG runtime directory,
inside a dedicated mode-0700 directory, with the socket mode 0600. Verify peer UID
against the service UID. Do not follow attacker-supplied paths/symlinks, overwrite
another listener, expose a new LAN port, or make a permissive native endpoint on
the existing HTTP server.

Use bounded versioned JSON messages, semantic allowlisted operations, current
connection generations and unique request IDs. Reject arbitrary bytes/UUIDs,
malformed types, excessive messages and invalid speed targets before any writes.
Bound per-client queues; a slow observer cannot delay BLE heartbeats or Stop.
The widget and shortcut helper share this route. A one-shot shortcut does not
become a short-lived motion owner: it invokes the existing live native controller
or reports that ownership/connection must be established first.

Keep the HTTP/WebSocket exact Host/Origin checks, same-origin bootstrap and
in-memory tokens intact. Native access authenticates the local user, not arbitrary
websites, and does not need browser cookies, Notion credentials or saved secrets.

## One durable record for each new walk

Use a private SQLite store under the user's XDG state directory. Keep its
directory private and database/WAL files inaccessible to other users. The bridge
records validated telemetry independently of whether a browser is open. It emits
the canonical active session ID to all views; the browser must disable its local
live recorder when using this new bridge recording capability. The original
direct Chromium route retains its existing local recorder.

Preserve the existing schema-2 JSON-compatible fields and unknown provenance
fields. Store stable UUIDs, source telemetry, timestamps, partial/complete
coverage, steps, distance, Calories, duration, sampled average/maximum speed and
the compact speed trace. Keep dates/times displayed in America/New_York and retain
precise source instants in machine data. Do not invent active duration, heart rate,
GPS or active-versus-total energy.

Begin a counted record only after observed running, not merely a successful
Start write or a countdown. Where observed, retain the pre-start stopped counter
baseline so a later walk does not count cumulative totals from a previous walk.
If the start/baseline is not observed, label coverage partial instead of guessing.
Pause/resume keeps the same record. Preserve last nonzero totals on counter reset;
stop completion requires stopped state plus zero speed. Source gaps and service
restarts retain interrupted evidence and require an explicit tracking continuity
choice without starting motion. Persist checkpoints transactionally; a storage
failure blocks further motion and requests Stop without preventing the safety
path from operating. Never claim a successfully saved walk after a failed commit.

Existing browser history stays in place with its exact backup. The bridge history
and local legacy history appear as a combined, ID-deduplicated dashboard view;
conflicting IDs/measurements are surfaced, not overwritten or summed. Loading the
dashboard must not bulk-upload or delete legacy records. If a user imports old
JSON into the shared store, reuse stable-ID merge/conflict checks and require a
successful durable write before reflecting success. No silent history migration.

Prepare for Notion uses the existing `walks.js` mapping on that combined view.
Tray-only walks therefore appear in History and export with the same source ID
as the service record. Keep assistant-assisted Notion import and its existing
deduplication boundary; no automatic uploads, API token storage or historical
Apple Health reconciliation changes are included.

## Lifecycle and reversible installation

Default to service startup on demand, with no login startup enabled. Installation
may add a user launcher and manually startable service definition, but enabling
login startup requires a separate explicit choice. The bar icon can show an
unavailable service until the user opens/connects. Starting a service does not
scan, connect, take control or start motion. Reuse the existing loopback dashboard
at port 8766 so the accepted user URL and its browser history remain available.

Stage plugin, launcher, helper and user-service files in the repository. Before
activation, save exact backups of only affected user files and record their
hashes. Add the PitPat widget and bindings without editing `gabe.tray`, unrelated
plugins, defaults or other shortcuts. Follow the Omarchy skill; validate Hyprland
changes with reload/configerrors and use supported hot reload for shell config.
No desktop or shell shutdown/restart is authorized by this specification.

Do not replace the active bridge while a walk is underway. Activate only with the
belt stopped/disconnected and current records resolved/exported. Stop the old
transient instance before starting the upgraded service on the same port; never
run competing bridge instances. New database initialization must succeed before
new motion can be enabled. Preserve the existing accepted source for rollback.

Rollback restores the exact prior user configuration and removes only new
integration files after the belt is stopped/disconnected. Preserve the shared
database and exported JSON. Export new server walks before returning to the old
browser-only version, which cannot otherwise display the shared store. Do not
delete health data, restore whole desktop profiles, or interrupt other chats.

## Verification and acceptance

Retain all accepted Firefox protocol/controller/security/export tests. Add tests
for native UID/socket permissions and malformed requests, observer isolation,
ownership transfer with queue cancellation, owner-specific lease loss, global
Stop priority, and all recorded safety deadlines.

Test recording with the browser absent, multiple observers, pause/resume,
successive walks with cumulative counters, counter resets, missing baselines,
interrupted reconnect/restart, failed SQLite commits, stable IDs, legacy-view
conflicts and identical Notion exports for the same source walk. Prove tray and
browser create one record together, rather than testing only separate clients.

Use explicit simulator mode for popup/keyboard flows and for tray-controller loss.
Validate target Quickshell APIs from the installed runtime; do not assume generic
Qt code works inside this shell. Verify the launcher, current bindings, popup,
live state and Stop accessibility in the actual Omarchy session through a
separately agreed human/visible handoff or user-performed checks. Hidden-desktop
tests alone do not prove the host bar installation.

User-supervised physical checks must verify tray connect/Start/speed/Pause/Stop,
Stop during startup, confirmed disconnect, ownership transfer while stopped,
Firefox-tab closure in each ownership mode, and native-owner exit stopping.
Keep the physical stop available. Finally, verify one resulting real walk in
History and through the Notion export/deduplication path with the user's approval.
Do not mark task 5 complete until these outcomes are observed and recorded.

## Review boundary

This document specifies the approved conversational behavior. No product code,
desktop configuration, running service, history or controller ownership changes
are authorized by writing it. After written-spec approval, create and review the
implementation plan; execute it in the current chat without additional agents.
