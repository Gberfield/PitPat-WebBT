# T11: "Stop PitPat" intent through the safety Stop path

## Context

PitPat-WebBT controls a PitPat treadmill. A separate safety process owns
Bluetooth and Stop and listens on `<runtime>/safety.sock`. On macOS the menu bar
app (`integration/macos/PitPatMenuBar`) has a Stop hotkey (⌃⌥⌘.) that calls
`AppDelegate.safetyStop()` in `App.swift`. That calls `SafetyStop.run(runtime:)`
(`SafetyStop.swift`): a one-shot helper connection (hello `kind:"helper"`, then
`op:"stop"`) that succeeds only on `result.outcome == "stopped_confirmed"` and
otherwise returns `SafetyStop.guidance` ("Stop unconfirmed. Use the physical stop
control.") plus the failure text. On failure the hotkey path sets
`service.warning`, posts a notification and opens the popover.

T9 and T10 (already on this branch) added App Intents to the menu bar app:
`Sources/PitPatMenuBar/Intents.swift` has `PitPatStatusIntent`, the
`AppShortcutsProvider` (`PitPatShortcuts`) and `AppDelegate.intentService`. The app
is built with `PitPat.xcodeproj` via `scripts/build-menubar.sh`. Design and owner
decisions: `docs/siri-integration.md` (D1–D4; D2 was revised after T9).

Owner decisions that bind this task:

- **D3:** the Siri Stop sends exactly what the Stop hotkey sends. No new Stop
  rule, no skipping Stop based on the menu bar's snapshot.
- **D2 (revised):** Siri opening PitPat counts as opening it. When PitPat is closed,
  Siri launches the app, which starts the services (`ServiceStart.run` in
  `applicationDidFinishLaunching`). A Stop to a freshly started safety process
  with no treadmill connected latches a fault. To avoid that, the Stop intent
  refuses when safety was not already running before this app launch, as long as
  this app session has never seen a treadmill connection. Best effort is
  accepted: if it misjudges, the worst case is that fault.

## What to do

1. **Probe at launch.** In `applicationDidFinishLaunching`, before
   `ServiceStart.run` is called (and also when `ServiceStart.shouldStart()` is
   false), record once whether `<runtime>/safety.sock` accepted a connection:
   `connectUnix` then close immediately, sending nothing (safety drops a client
   that sends no hello within 3 s; this is harmless). Store it as
   `safetyRunningAtLaunch`. Put the probe in a small function that takes the
   path, so it can be tested against a fake socket. Don't otherwise change the
   launch, service-start or quit paths.
2. **Track connections this session.** Add to `Service` a flag that becomes true
   the first time any accepted snapshot has `connected` or `connecting` true, and
   never resets while the app runs. Don't change any other `Service` behaviour.
3. **`PitPatStopIntent`** (title "Stop PitPat", `openAppWhenRun = false`), with
   phrases such as "Stop \(.applicationName)" and "Stop the treadmill in
   \(.applicationName)", added to `PitPatShortcuts`. `perform()` on the main
   actor:
   - If `!safetyRunningAtLaunch` and the session flag is false: reply "PitPat
     wasn't open, so no treadmill is connected. Nothing was stopped." and send
     nothing.
   - Otherwise run the same Stop as the hotkey: factor the hotkey's body into one
     function both call (same `SafetyStop.run`, same warning, notification and
     popover on failure), awaiting its result. Reply "Stopped." only when it
     returned nil (stopped_confirmed). Otherwise reply with the failure text
     exactly as the hotkey shows it.
   - No confirmation prompt, no waiting for the bridge, no use of the control
     socket, no take-control or connect.
4. **Tests** (Swift, fake `safety.sock` in a temp directory, simulator and fakes
   only): the probe is true for a listening socket and false for a missing path
   and a stale socket file with no listener; the session flag; the refusal rule
   (all four combinations of probe and flag); the Stop reply for
   `stopped_confirmed`, an `ok:false` reply, another outcome, a timeout and a
   missing socket, with the exact texts. Factor the decision and reply text into
   pure functions where that keeps the tests simple.

## Safety boundary

This is the Stop path. Never connect to, arm or move a physical treadmill; tests
use fake sockets only. Don't change `SafetyStop`'s protocol, timeouts or success
rule, the safety process, Stop confirmation, recovery rules, BLE code or the
on-demand service policy. If the refusal rule seems to need any of those, stop
and report. The intent must never claim the belt stopped unless safety returned
`stopped_confirmed`.

## Checks (all must pass)

```bash
node --test --test-isolation=none
uv sync --locked && uv run --frozen python -m unittest discover -s tests -p 'test_*.py'
(cd integration/macos/PitPatMenuBar && swift test)
scripts/build-menubar.sh
```

Swift builds, `xcodebuild`, uv and socket tests may fail inside the Codex sandbox.
Report exactly which ones and the error; Claude runs them outside it. Don't change
global config to work around the sandbox.

## Rules

- Don't commit, push or create branches. Leave the changes in the working tree.
- Don't edit `PLAN.md` or anything under `docs/handoffs/`.
- Don't install into `~/Applications` or start the real services.
- Match the surrounding compact Swift style.
- Report what you changed, the reply text for each case, and the check output.
