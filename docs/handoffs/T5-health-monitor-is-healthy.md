# T5: Make the health check one call that includes expiry (GitHub issue #38)

## Context

PitPat-WebBT controls a PitPat treadmill. In production, Bluetooth is owned by a separate
safety process, `bridge/safety_core.py` `SafetyCore`. It watches the application process
with `bridge/safety_health.py` `HealthMonitor`: safety sends challenges, the application
answers, and an application that stops answering for `HEALTH_TIMEOUT` (2 s) is treated as
gone and trips a fault.

## The problem

`HealthMonitor.healthy` is set to True by the first accepted answer after `attach()`, and
only `attach()` / `detach()` reset it. It means "answered at least once since attach", not
"healthy now". Being healthy now also needs `not expired()`.

Every current caller pairs the two correctly (`bridge/safety_core.py`: `snapshot()`'s
`bridge_healthy`, the health tick that trips "Application health expired", the readiness
check before acquire/recover, and the writer's `before()` check). But the name invites a
future caller to check `healthy` alone and accept an application that has stopped answering.
This is safety-critical code, so the name should not be able to mislead.

## What to do

1. In `HealthMonitor`, rename the attribute `healthy` to a name that says what it means,
   for example `answered` (answered since attach). Add one method, for example
   `is_healthy()`, that returns `answered and not expired()`.
2. Change every caller in `bridge/` that checks `healthy` together with `expired()` to use
   `is_healthy()`, where the two together mean "healthy now". Where a caller needs the
   pieces separately (for example the tick that trips on expiry while connected), keep its
   logic exactly as it is and only follow the rename.
3. Behaviour must not change at all: same trips, same fault messages, same refusals, same
   timing. `snapshot()` keeps the wire field name `bridge_healthy` and its value. Don't
   change `HEALTH_TIMEOUT`, the challenge protocol, `accept_health`, or anything outside
   this health check.
4. Update tests that read `core.health.healthy` (`tests/test_safety_ipc.py`,
   `tests/test_safety_client.py`, and any others) to the new name.
5. Add focused unit tests for `HealthMonitor`: `is_healthy()` is False before any answer,
   True after an accepted answer, False once the clock passes `HEALTH_TIMEOUT` with no new
   answer (while `answered` stays True), and False after `detach()` and after a new
   `attach()`. Use a fake clock.
6. Search `docs/` for `healthy` as an attribute of the health monitor, and update any
   mention.

## Safety boundary

This is safety-critical code. Never connect to, arm or move a physical treadmill. Tests use
`SimulatorBackend` and fakes only. If keeping behaviour identical turns out to be
impossible, stop and report instead of changing behaviour.

## Checks (all must pass)

```bash
node --test --test-isolation=none
uv sync --locked && uv run --frozen python -m unittest discover -s tests -p 'test_*.py'
```

Socket-based tests may fail inside the Codex sandbox with PermissionError. Report which
ones, and Claude will run them outside it.

## Rules

- Don't commit, push or create branches. Leave the changes in the working tree.
- Don't edit `PLAN.md` or anything under `docs/handoffs/`.
- Match the surrounding code style (compact one-line style in safety_core.py and
  safety_health.py).
- Report what you changed, why, and the test output.
