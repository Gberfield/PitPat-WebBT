# T2: Browser walk record says 'stopping' while the belt decelerates (GitHub issue #44)

## Context

`treadmill.js` is the browser dashboard. In Web Bluetooth mode (no shared bridge recording)
it records walks itself, in `captureWalk(state, raw, mph)`, called from `handleNotification`.
The bridge's recorder (`bridge/recorder.py`, `Recorder.observe`) records the same telemetry
for bridge mode.

Treadmill telemetry `running_state` is 0 starting, 1 running, 2 paused, 3 stopped/stopping.
"Stopped" means state 3 **and** speed 0.

## The defect

When the treadmill reports state 3 with non-zero speed (decelerating), `handleNotification`
maps it to `trackingState = 0` so that recording continues until the belt has actually
stopped. That is intended and must stay. But `captureWalk` then sets
`walk.status = 'starting'` for those packets. The bridge recorder writes `'stopping'` for the
same telemetry. So browser records briefly show "starting" during a stop, and the two
recorders disagree.

## What to do

1. Keep the "keep tracking until state 3 and speed 0" behaviour exactly as it is: the
   session must not finish early, counters keep updating, and a session must not be
   created from a decelerating packet when none exists.
2. Record the status as `'stopping'` for state 3 with non-zero speed, matching
   `bridge/recorder.py`. Pick the smallest change. For example, pass the real state (or a
   flag) through to `captureWalk` instead of overloading 0, but don't change
   `updateRunningState` / `setStatus('Stopping')` behaviour in the UI.
3. Check that `walks.js` and the Notion export (`buildNotionExport`) handle a `'stopping'`
   status like the other in-progress statuses ('starting', 'running', 'paused'). Bridge
   records can already carry 'stopping'. Fix only if they don't.
4. Add a test in `tests/units.test.cjs` (it already loads `treadmill.js` with fakes) that
   feeds: a running packet → a state-3 packet with non-zero speed → a state-3 zero-speed
   packet. Assert that the stored walk's status is 'stopping' after the second packet, and
   'completed' after the third, with final counters from the third packet.

## Safety boundary

Never connect to or move a physical treadmill. Tests use fakes only.

## Checks (all must pass)

```bash
node --test --test-isolation=none
uv sync --locked && uv run --frozen python -m unittest discover -s tests -p 'test_*.py'
```

## Rules

- Don't commit, push or create branches. Leave the changes in the working tree.
- Don't edit `PLAN.md` or anything under `docs/handoffs/`.
- Match the surrounding code style.
- Report what you changed, why, and the test output.
