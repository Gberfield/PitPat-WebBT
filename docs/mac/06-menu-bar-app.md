# 06 — Menu bar controller (replaces the Omarchy tray)

**Depends on:** 05. **Size:** large. **Touches real hardware:** no (simulator).

## Why

On Linux, `integration/omarchy/gabe.pitpat/` is a Quickshell plugin:
`Service.qml` (socket client + state), `Widget.qml` (UI), `Model.js` (pure view
model, shared with Node tests). It is a *native controller*: it connects to
`<runtime>/control.sock`, says `{"v":1,"op":"hello","kind":"tray"}`, can take
motion ownership, renews its lease every second, and exposes
start/pause/stop to Super+F10/F11. macOS needs the same thing in the menu bar.

## Decision (recommended; owner may override in the PR)

A small **SwiftUI `MenuBarExtra` app**, macOS 13+, no third-party packages,
built with `swift build` / `xcodebuild` from a Swift package in
`integration/macos/PitPatMenuBar/`. Reasons: native menu bar and global hotkeys
without extra permissions (Carbon `RegisterEventHotKey` needs no Accessibility
grant), no new Python dependencies, independent process from the bridge (so a
bridge freeze does not freeze the controls, same as the Linux tray).

Alternative considered: Python `rumps` + PyObjC. Rejected: adds runtime deps to
the locked environment and global hotkeys need PyObjC Carbon bridging anyway.

## Protocol contract (port exactly from `Service.qml`)

Read `Service.qml` fully; it is ~150 lines. The Swift client must reproduce:

- Socket: `AF_UNIX` stream to `<runtime>/control.sock`. Runtime path:
  `PITPAT_RUNTIME_ROOT` env if set, else
  `~/Library/Application Support/PitPat/run`, plus `/pitpat`
  (same as `platform_paths.runtime_dir()` from plan 01).
- Newline-delimited JSON, each line ≤ 65,536 bytes, else disconnect.
- On connect: send `{"v":1,"op":"hello","kind":"tray"}`. Expect
  `{"event":"authorized","generation":N,"simulator":bool,"snapshot":{...}}`.
- Requests: `{"v":1,"id":"<serial>","op":<op>,"generation":<gen>,"args":{...}}`,
  ops and args exactly as in `bridge/messages.py:ALLOWED`. Max 8 pending.
- Responses with `id`: apply the same obsolete-generation rule as `receive()`
  (the `changes` list). Events without `id`: drop if `generation` older or
  `seq <= sequence`.
- Every 1 s while a view is open or releasing: if owner or recovery claimant,
  send `renew`; time out pending requests after 8 s (26 s for `connect`) with the
  message "Request timed out; motion unconfirmed. Use the physical stop control."
  and drop the socket.
- On socket loss while connected: show "Controller connection lost; belt state
  is unconfirmed. Use the physical stop control."
- Closing the popover with zero views: if owner, `release` then disconnect.
  **Match the Linux semantics in `unregisterView`.** Note the Linux README:
  "Closing a popup retains native control" — read `Widget.qml` to see how views
  are registered and mirror that, rather than guessing.
- Recovery flow (`acknowledgeRecovery`): `stop`, then on ok and same `fault_id`,
  `acknowledge_recovery` with `fault_id` and `stop_confirmation_id`.

## View model

Port `Model.js` to Swift **literally** (`view`, `targetUnits`, `duration`),
including MPH/miles conversions and `canStartPause` / `canTakeControl` rules.
Add `tests/fixtures/model-cases.json`: generate it from `Model.js` with a small
Node script (`node tests/gen-model-cases.cjs`) covering ~20 snapshots (stopped,
walking owner, observer, stale, fault, recovery, simulator, safety unavailable,
storage fault). Swift unit tests (`swift test`) assert identical output for each
case. This is the guard that the two ports agree.

## UI (mirror `Widget.qml`)

- Menu bar icon: walking figure SF Symbol (`figure.walk`), tinted when walking,
  warning symbol when a warning is active, "SIM" badge in simulator mode.
- Popover: state label, owner line, speed/distance/Calories/steps/duration,
  target MPH stepper (±0.1, uses `targetUnits`), Start/Pause, **Stop** (always
  visible, red, enabled whenever `canStop`), Stop & Disconnect, Take control,
  Find treadmill (discover → device list → connect), Recover Stop control,
  continuity choice (`resolve_session`), recovery acknowledgment, Open dashboard,
  Open history. Error and warning text verbatim from the bridge.
- Copy rules: keep the existing wording; never claim the belt stopped unless the
  snapshot says so.

## Hotkeys and URL scheme

- Global hotkeys via `RegisterEventHotKey`, defaults (Mac keyboards often map F
  keys to media): ⌃⌥⌘P = open controls, ⌃⌥⌘Space = Start/Pause, ⌃⌥⌘. = Stop.
  Stop hotkey runs the same path as `pitpat stop` (direct to `safety.sock`), not
  the control socket. Implement it in Swift (hello `kind:"helper"`, then
  `{"v":1,"id":"stop","op":"stop","authority":null,"args":{}}`, 8 s timeout,
  success only on `result.outcome == "stopped_confirmed"`), mirroring
  `bridge/desktop.py:safety_stop`. Show a notification on failure:
  "Stop unconfirmed. Use the physical stop control."
- URL scheme `pitpat://` (`CFBundleURLTypes`): `pitpat://start-pause`,
  `pitpat://controls`. Used by `pitpat start-pause` from plan 05.
- Bundle id `com.gberfield.pitpat.menubar`, `LSUIElement=true`.

## Build and layout

```
integration/macos/PitPatMenuBar/Package.swift
integration/macos/PitPatMenuBar/Sources/PitPatMenuBar/{App,Service,Socket,Model,Hotkeys,SafetyStop}.swift
integration/macos/PitPatMenuBar/Tests/PitPatMenuBarTests/ModelTests.swift
integration/macos/PitPatMenuBar/Info.plist
scripts/build-menubar.sh     # swift build -c release + assemble .app + ad-hoc codesign
```

Use `Network.framework` `NWConnection` with `NWEndpoint.unix(path:)` for the
socket, or a plain `FileHandle` over a `socket()`/`connect()` fd; either is fine,
keep it on one serial queue and publish state to the main actor.

## Tests / acceptance (simulator only)

1. `swift test` passes, including the model-fixture cases.
2. With simulator services (plan 05 acceptance setup): menu bar shows
   "SIMULATOR · Disconnected"; Find treadmill → `SIMULATOR — no physical
   treadmill`; connect; take control; Start → Walking; ⌃⌥⌘Space pauses;
   ⌃⌥⌘. stops with confirmation; kill the bridge (`kill -STOP`, then `-CONT`) and
   watch recovery controls reappear; acknowledge recovery.
3. Record a short screen capture or screenshots in the PR.

## Don't

- Don't talk to Bluetooth from Swift. The safety process is the sole BLE owner.
- Don't implement auto-start at login or auto-restart of services.
- Don't invent new protocol ops; if something is missing, stop and ask in the PR.
