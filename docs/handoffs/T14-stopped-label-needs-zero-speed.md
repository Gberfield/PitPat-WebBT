# T14: Show "Stopped" only when the treadmill reports state 3 and zero speed

## Context

PitPat-WebBT controls a PitPat treadmill. Telemetry reports a running state
(0 Starting, 1 Running/Walking, 2 Paused, 3 Stopped) and a speed (`speed_raw`,
`current_speed`). The safety rule everywhere in the bridge is that the belt is
stopped only when the state is 3 **and** the speed is zero
(`bridge/protocol.py` `Telemetry.stopped`; `treadmill.js` Stop confirmation).

The status labels don't follow that rule. They map state 3 to "Stopped" whatever
the speed:

- `integration/omarchy/gabe.pitpat/Model.js` (Omarchy tray), source of
  `tests/fixtures/model-cases.json` via `tests/gen-model-cases.cjs`;
- `integration/macos/PitPatMenuBar/Sources/PitPatMenuBar/Model.swift` (macOS menu
  bar; a literal port that must match the fixtures), which a Siri status intent
  on an unmerged branch also uses;
- `treadmill.js` (browser dashboard): `setStatus('Stopped')` for state 3 and
  `statusArr` in the telemetry handler.

On November 11, 2026 the owner's treadmill reported state 3 with speed 1.0 mph
for minutes while the belt was moving, and the menu bar and status said
"Stopped". The bridge copy rule is: never claim the belt stopped unless the
reports say so.

## What to do

1. In all three places, state 3 with a speed other than exactly zero must not be
   labelled "Stopped". Use "Stopping" in the tray/menu bar models and the
   browser status. Keep state 3 with zero speed as "Stopped". Don't change the
   other states' labels.
2. Don't change any control rule: `canStartPause`, `canAdjust`, `canStop`,
   `canTakeControl` (already requires state 3 and speed 0), Start/Pause text,
   browser `enableControls`, Stop confirmation, recording, or anything in
   `bridge/`.
3. Add a fixture case `stopped-state-moving` (state 3, speed_raw 1000, owner) to
   `tests/gen-model-cases.cjs`, regenerate `tests/fixtures/model-cases.json` with
   `node tests/gen-model-cases.cjs`, and make sure the Swift `ModelTests`
   fixture comparison passes. (This task starts from `main`, where the Siri
   `Intents.swift` and `StatusDialogTests` don't exist yet; the Siri branch picks
   up the label change when it is merged.) Add a browser test in the existing node tests if the status
   path is testable there; otherwise say why not.

## Safety boundary

Labels only. Never connect to, arm or move a physical treadmill; use fixtures,
fakes and the simulator. Don't change the BLE protocol, Stop confirmation,
timeouts, recovery rules or any `bridge/` code.

## Checks (all must pass)

```bash
node --test --test-isolation=none
uv sync --locked && uv run --frozen python -m unittest discover -s tests -p 'test_*.py'
(cd integration/macos/PitPatMenuBar && swift test)
scripts/build-menubar.sh
```

Swift, uv and socket checks may fail inside the Codex sandbox; report which ones
and the error, and Claude runs them outside it.

## Rules

- Don't commit, push or create branches. Leave changes in the working tree.
- Don't edit `PLAN.md` or anything under `docs/handoffs/`.
- Match the surrounding compact style.
- Report what you changed, every label change, and the check output.
