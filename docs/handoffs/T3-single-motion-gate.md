# T3: One motion-gate rule in the stop kernel and SafetyCore (GitHub issue #34)

## Context

`bridge/control_core.py` `Controller` is the stop kernel: it owns the Bluetooth link,
heartbeat and telemetry-confirmed Stop. `bridge/safety_core.py` `SafetyCore` extends it and is
the production safety process. The flag `blocked` gates motion writes. In particular
`write()` cancels queued motion when `self.blocked` is set.

## The problem

`Controller.packet()` (control_core.py, the "if not stopping" block near the end) computes
`blocked` with the kernel's rule (`storage_fault`, `report.stopped`, `initial_report`,
`recovery`). It then emits `emit('state', ..., blocked=self.blocked)`. `SafetyCore.packet()`
calls `super().packet()` and immediately overwrites `blocked` with
`bool(self.fault_id) or not bool(self.grant_id)`. Two layers write the same safety flag under
different rules, and the emitted `state` event carries a value the safety process doesn't
use. `SafetyCore.stop()` and `grant()` also set `blocked` directly.

This is not a known live bug: the overwrite is synchronous and the application ignores
`data.blocked` from safety. It is a drift risk in safety-critical code.

## What to do

1. Introduce one overridable rule for "is motion blocked after this telemetry", for example a
   method `_motion_blocked_after_report(report)` on the kernel that `SafetyCore` overrides.
   `packet()` should assign `blocked` from it **before** emitting the `state` event, so the
   emitted value and the stored value always agree.
2. `SafetyCore.packet()` must no longer overwrite `blocked` after `super().packet()`.
3. Preserve behaviour exactly: for the kernel alone and for `SafetyCore`, every existing test
   must pass unchanged, and `blocked` must have the same value after every packet as it does
   today. Keep `recovery` handling in the kernel as it is. Don't change `stop()`,
   `perform_stop()`, `lost()`, `trip()`, `grant()`, `write()`, the heartbeat, or the
   stop-confirmation logic, beyond what step 1 strictly needs.
4. Add tests for the agreement: after a packet, the `blocked` carried by the `state` event
   equals the stored `blocked`, for both the kernel (`tests/test_bridge_controller.py`) and
   `SafetyCore` (`tests/test_safety_core.py`). Cover these cases: fault latched, no grant,
   grant with a stopped report, and a moving report while stopping.
5. Don't touch `link_state` in this task.

## Safety boundary

This is safety-critical code. Never connect to, arm or move a physical treadmill. Tests use
`SimulatorBackend` and fakes only. If keeping behaviour identical turns out to be impossible,
stop and report instead of changing behaviour.

## Checks (all must pass)

```bash
node --test --test-isolation=none
uv sync --locked && uv run --frozen python -m unittest discover -s tests -p 'test_*.py'
```

## Rules

- Don't commit, push or create branches. Leave the changes in the working tree.
- Don't edit `PLAN.md` or anything under `docs/handoffs/`.
- Match the surrounding code style (compact one-line style in safety_core.py).
- Report what you changed, why, and the test output.
