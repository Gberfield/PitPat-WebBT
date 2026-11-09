# T1: Block motion as soon as an interrupt is queued (GitHub issue #41)

## Context

PitPat-WebBT controls a PitPat treadmill. In production, Bluetooth is owned by a separate
safety process (`bridge/safety_core.py`, `SafetyCore`). The application process
(`bridge/controller.py`, `Controller`, started from `bridge/__main__.py`) does IPC and walk
recording only. Walk recording runs through `bridge/recorder.py`: `RecordingWorker` queues work
(`offer`) and a worker task applies it to `Recorder`, which then calls the controller's
`recorded(row)` callback.

`tracking_review` blocks start / pause / set_speed until an interrupted walk record is
resolved (`bridge/controller.py`, the check before motion in `dispatch`).

## The defect

In `bridge/controller.py`, `tracking_review` is set only in `recorded()`, which runs after the
worker has actually written the interrupted row. `record('interrupt', ...)` only queues the
work. For an interrupt that doesn't also trip safety (for example
`'Safety telemetry gap; coverage partial'` in `received()`), a motion request dispatched
before the worker runs passes the `tracking_review` check.

The stop kernel `bridge/control_core.py` `Controller` (used directly only by tests, and as
the base of `SafetyCore`) latches `tracking_review = True` the moment it queues an interrupt
(`record()`). It clears the flag in `recorded()` only when the queue is empty. So the two
controllers use different rules for the same flag.

## What to do

1. In `bridge/controller.py`, latch `tracking_review = True` at the moment an `interrupt` or
   `safety_evidence` record is offered, before the worker runs.
2. Clear it only when the recorder reports a row that is not interrupted (or no row) **and**
   no interrupt / safety_evidence work is still queued. Count pending interrupt work
   explicitly; don't rely on total queue size alone if other work kinds are queued
   behind it.
3. Make `bridge/control_core.py` use the same rule, so both controllers agree. Prefer one
   small shared helper (for example on `RecordingWorker`) over two copies.
4. If `offer` fails (recording faulted or closed), motion must stay blocked. `storage_fault`
   already does that; keep it.
5. Add tests:
   - in `tests/test_safety_facade.py` (the production facade over a real `SafetyCore` with
     `SimulatorBackend`), or a focused unit test against `bridge.controller.Controller`
     with a fake safety client: a motion request issued after an interrupt is queued but
     before the worker has run is refused with the existing "Resolve interrupted tracking
     first" error;
   - motion is allowed again only after the record is resolved (`resolve_session`) and no
     interrupt work is pending;
   - the equivalent case for `bridge.control_core.Controller` still passes.

Don't change any other gating, messages, IPC or protocol behaviour.

## Safety boundary

Never connect to, arm or move a physical treadmill. Use only `SimulatorBackend` and fakes in
tests. Don't run anything with real Bluetooth.

## Checks (all must pass)

```bash
node --test --test-isolation=none
uv sync --locked && uv run --frozen python -m unittest discover -s tests -p 'test_*.py'
```

## Rules

- Don't commit, push or create branches. Leave the changes in the working tree.
- Don't edit `PLAN.md` or anything under `docs/handoffs/`.
- Keep the code style of the surrounding file (these files use compact one-line style; match it).
- Report what you changed, why, and the test output.
