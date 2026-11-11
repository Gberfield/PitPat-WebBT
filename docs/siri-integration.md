# Siri integration plan (proposed)

Drafted November 11, 2026. Nothing here is built yet. The tasks are proposed
rows T9–T13 in [PLAN.md](../PLAN.md). On November 11, 2026 the owner accepted
the recommendation in each of D1–D4 below; they are settled.

## Goal

Let the owner speak to PitPat through Siri on the Mac, and get the same
actions in Shortcuts and Spotlight: ask how the walk is going, stop the belt,
and possibly pause or start it, without touching the keyboard.

Siri is a convenience, never a safety control. Recognition can fail, be slow,
or be off. The physical stop control stays the only guaranteed Stop, and every
reply follows the existing copy rule: never claim the belt stopped unless
safety confirmed it.

## How it fits the current app

- **Where the intents live.** Siri on macOS runs App Intents. They go in the
  menu bar app (`integration/macos/PitPatMenuBar`), next to the hotkeys, using
  an `AppShortcutsProvider` so the phrases work with no setup in Shortcuts.
  The intents run inside the menu bar process and call the `Service` it already
  holds, so they reuse its socket, lease, view model and wording.
- **No new protocol.** Each intent maps onto a path that already exists:

  | Intent | Existing path | Motion? |
  | --- | --- | --- |
  | Status ("How's my walk?") | `Service.snapshot` + `Model.view` | No |
  | Stop ("Stop PitPat") | `SafetyStop.run`, the same path as ⌃⌥⌘. and `pitpat stop`, straight to `safety.sock` | Stop only |
  | Pause | `Service.startPause()` when it would send `pause`, through the menu bar owner's lease | Yes (safety treats Pause as motion) |
  | Start | `Service.startPause()` when it would send `start` | Yes |
  | Set speed | `Service.setTargetMph`, bounded by the existing 1000–6000 unit check | Yes |

  The motion intents never take control or connect a treadmill. If the menu bar
  is not the owner of a healthy connection, they refuse with the existing text
  ("Take control of a healthy, stopped connection first.").
- **Linux** has no Siri. The Omarchy tray is out of scope.

## What has to change to build it

1. **Build.** `scripts/build-menubar.sh` uses `swift build`, which does not run
   Xcode's `appintentsmetadataprocessor`. Without the generated
   `Contents/Resources/Metadata.appintents`, macOS doesn't register the intents.
   The build likely has to move to `xcodebuild` (on the package scheme or a
   small Xcode project) with the full Xcode (27.2 is installed). T9 checks this
   first, with one read-only intent.
2. **Installer.** `scripts/install-macos.py` copies only `Info.plist` and the
   executable into `~/Applications/PitPat.app`, and refuses unexpected files in
   the build. It needs to allow and copy the intents metadata, and the menu
   bar's tests need to cover that.
3. **Launch behaviour.** If Siri runs a PitPat intent while PitPat is closed,
   macOS launches the menu bar app, and opening it starts both services
   (on-demand policy, November 4). T9 records what actually happens. Owner
   decision D2 settles what it should do.

## Owner decisions (settled November 11, 2026: each recommendation accepted)

- **D1. Which motion commands may be voice-driven.** Recommendation: Status and
  Stop in the first release; Pause next, since it slows the belt; Start only
  with Siri's spoken confirmation step (`requestConfirmation`), or not at all;
  speed changes left out unless wanted. Each motion intent gets an adversarial
  review.
- **D2. Intents while PitPat is closed.** Recommendation: an intent never starts
  the services. If the app was launched for an intent, it answers "PitPat isn't
  open" and quits without starting anything. Otherwise saying "Stop PitPat"
  when nothing is running would start safety and then latch a fault (see D3).
  Whether this can be detected reliably is part of T9; if it can't, the
  fallback is that Siri launching PitPat counts as opening it.
  **Revised November 11, 2026, after T9:** T9 found no documented way to tell
  an intent launch from a normal open before services start, and the owner
  chose the fallback: Siri launching PitPat counts as opening it, so an intent
  may start the services. One guard is added: the Stop intent refuses with
  "PitPat isn't open" when the safety process wasn't already running before the
  app launched, so a voice Stop on a closed PitPat can't latch a fault. That
  check is best effort; if it misjudges, the worst case is the fault described
  in D3. A separate intents process (which would guarantee "never starts") was
  considered and not chosen.
  **Revised again November 11, 2026, after T11's adversarial review:** the
  launch-probe guard could refuse a needed Stop when the menu bar missed a
  browser Connect. The owner chose to ask safety itself: the Siri Stop skips
  sending only when safety's own hello snapshot reports `link_state`
  "disconnected" and `connected` false, and otherwise sends Stop exactly as the
  hotkey does. This narrows D3: with PitPat open but nothing connected, the
  voice Stop no longer latches a fault, while the hotkey and `pitpat stop`
  still always send Stop.
- **D3. Stop with nothing connected.** `pitpat stop` and the Stop hotkey latch a
  fault when no treadmill is connected (STATUS optional item 4, left unchanged
  on purpose). Recommendation: the Siri Stop sends exactly what the hotkey
  sends, with no new rule. Skipping Stop when the menu bar shows "Disconnected"
  would avoid the fault but trusts a possibly stale snapshot, so that's a
  recovery-rules change for the owner.
- **D4. Build tooling.** Moving from `swift build` to `xcodebuild` makes the full
  Xcode a build requirement for the menu bar app, not just the command line
  tools. Recommendation: accept it; the owner's Mac already has Xcode 27.2.

## Task outline

Each task follows the Codex handoff workflow. The T9 brief is in
[docs/handoffs/](handoffs/T9-siri-intents-spike.md); T10 brief is
[T10-status-intent.md](handoffs/T10-status-intent.md); T11–T13 briefs follow
in order. All automated work
uses the simulator services only.

- **T9. Spike: intents build and register (high).** Move the build to one that
  emits App Intents metadata; add one read-only `PitPatStatusIntent`; extend
  the installer allowlist; record whether Shortcuts lists it, whether Siri
  answers it, and what happens when it runs with PitPat closed. Codex review.
- **T10. Status intents (medium).** Spoken state, speed, distance, time and steps
  from `Model.view`, using the menu bar's existing labels, including Simulator,
  stale, fault and safety-unavailable cases. Swift tests over the
  `model-cases.json` fixtures. Codex review.
- **T11. Stop intent (high).** "Stop PitPat" runs `SafetyStop.run`. It replies
  "Stopped" only on `stopped_confirmed`, otherwise "Stop unconfirmed. Use the
  physical stop control." plus the failure text, and shows the same
  notification as the hotkey. Tests use a fake `safety.sock`. Codex review and
  adversarial review.
- **T12. Motion intents (xhigh, only what D1 allows).** Pause, and Start with
  confirmation, through the owner's `Service` path; refusal when not owner or
  `canStartPause` is false; no take-control or connect by voice. Codex review
  and adversarial review.
- **T13. Docs (low).** README (phrases and limits), macOS operations (enabling
  Siri, rebuilding with Xcode), a Siri section in macOS acceptance, STATUS.

## Acceptance

- Automated: both project checks and `swift test` pass; the intents are tested
  against fakes and simulator services.
- Owner, on the installed app: with simulator services, each phrase works from
  Siri and from Shortcuts. With the treadmill, only after the owner's go-ahead
  in chat: "Stop PitPat" mid-walk stops the belt, and the reply matches what
  safety reported. Results go in [macOS acceptance](macos-acceptance.md).
