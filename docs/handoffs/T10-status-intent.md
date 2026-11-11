# T10: Finish the read-only PitPat Status intent

## Context

PitPat-WebBT controls a PitPat treadmill. On macOS the menu bar app
(`integration/macos/PitPatMenuBar`) is the native controller. Its `Service`
(`Sources/PitPatMenuBar/Service.swift`) holds the socket to the local bridge and
publishes `snapshot` and `authorized`; `Model.view(snapshot, isOwner)`
(`Model.swift`) produces the labels the popover shows (`state`, `label`, `owner`,
`speed`, `distance`, `calories`, `steps`, `duration`).

T9 (already on this branch) added `Sources/PitPatMenuBar/Intents.swift` with a
read-only `PitPatStatusIntent`, its `AppShortcutsProvider` phrases, the pure
function `statusDialog(authorized:model:)`, and tests in
`Tests/PitPatMenuBarTests/StatusDialogTests.swift`. The app is now built with
`PitPat.xcodeproj` through `scripts/build-menubar.sh`. Design and owner decisions:
`docs/siri-integration.md`; T9 findings: `docs/siri-intents-spike.md`.

The owner decided (D2, revised) that Siri opening PitPat counts as opening it. So
when PitPat is closed, Siri launches the menu bar app, which starts the services
(`ServiceStart.run`) and connects its socket on a one-second retry tick. The
intent's `perform()` can therefore run before `Service.authorized` is true, and
today it would wrongly answer "PitPat isn't connected to its services."

## What to do

1. **Wait briefly for the bridge on launch.** In `perform()`, if the service is
   not authorized, wait for `authorized` to become true for up to 5 seconds
   (observe the published value or poll on the main actor; no busy loop, no new
   requests), then build the reply. Put the wait in a small helper that takes the
   timeout and a clock or sleep function, so tests can run it without real time.
   If it is still not authorized, reply "PitPat couldn't reach its services. Open
   PitPat from the menu bar to check." Don't change `ServiceStart`, the socket
   retry tick or the launch path.
2. **Better replies.** Extend `statusDialog` so the spoken text fits the state,
   using only `Model.view` fields and the snapshot fields the popover already
   reads. Keep the bridge's wording; never say the belt stopped unless the model
   state says so. At least:
   - no treadmill connected (`disconnected`, `simulator-disconnected`, `empty`,
     `unavailable` fixtures): "PitPat is open but no treadmill is connected."
     (prefix with the simulator label when the model's label has it);
   - connecting: "PitPat is connecting to the treadmill.";
   - walking, paused, starting, stopped with metrics: `<label>. <speed>,
     <distance>, <duration>, <steps> steps.`;
   - stale: say the reading is stale, using the model's label;
   - fault or a non-empty service `warning`: append the warning text verbatim
     and "Use the physical stop control if needed."
   The exact wording of the other cases is your call; keep it short and spoken.
3. **Tests.** Update `StatusDialogTests` to cover every case in
   `tests/fixtures/model-cases.json` (assert the category of reply per fixture
   name, plus exact text for at least walking, disconnected, stale and fault),
   the not-authorized-after-wait case, and the wait helper (becomes authorized
   in time; times out).

## Safety boundary

Read-only: the intent must not send any request, take control, connect, or start
or stop services. If finishing it seems to need a new request or protocol op,
stop and report. Never connect to, arm or move a physical treadmill. Use fakes
only. Don't change the BLE protocol, safety timeouts, Stop handling, recovery
rules, `ServiceStart` or the quit path.

## Checks (all must pass)

```bash
node --test --test-isolation=none
uv sync --locked && uv run --frozen python -m unittest discover -s tests -p 'test_*.py'
(cd integration/macos/PitPatMenuBar && swift test)
scripts/build-menubar.sh
```

Swift builds, `xcodebuild`, uv and socket tests may fail inside the Codex sandbox
(module cache, uv cache, sockets). Report exactly which ones and the error; Claude
runs them outside it. Don't change global config to work around the sandbox.

## Rules

- Don't commit, push or create branches. Leave the changes in the working tree.
- Don't edit `PLAN.md` or anything under `docs/handoffs/`.
- Don't install into `~/Applications` or start the real services.
- Match the surrounding compact Swift style.
- Report what you changed, the reply text for each fixture category, and the
  check output.
