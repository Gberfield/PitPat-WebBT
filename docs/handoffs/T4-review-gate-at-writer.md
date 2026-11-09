# T4: Enforce the record-review gate at the serialized write boundary (GitHub issue #50)

## Context

PitPat-WebBT controls a PitPat treadmill. In production, Bluetooth is owned by a separate
safety process: `bridge/safety_core.py`, `SafetyCore`, which extends the stop kernel
`bridge/control_core.py` `Controller`. The application process (`bridge/controller.py`
`Controller`) does IPC and walk recording only, and talks to safety through
`bridge/safety_client.py` over a Unix socket (`bridge/safety_ipc.py`).

`tracking_review` in the application controller blocks start / pause / set_speed while an
interrupted walk record is unresolved. Issue #41 (already on this branch's base) made it
latch the moment an interrupt or safety-evidence record is queued, using
`RecordingWorker.requires_review()` in `bridge/recorder.py`.

## The defect

The gate is checked only when a motion request is dispatched. Motion that passed the check
and is waiting for the serialized writer (`write()` holds `self.lock`, for example behind a
heartbeat) is still written after the gate latches:

- **SafetyCore:** `handle_application`'s `before()` callback checks the fault, health,
  grant, lease and telemetry freshness, but not recording readiness or review state.
- **Application:** it never tells safety that a record needs review. The only existing
  signal, `recording_ready=False`, trips a safety fault (stops the belt, needs explicit
  recovery). That is too heavy for a telemetry gap and must not be used for this.
- **Stop kernel:** in `control_core.py`, `record('interrupt')` changes neither
  `motion_generation` nor `blocked`, so `write()` doesn't cancel queued motion.

Repro, as reported by review: hold the writer lock, dispatch set_speed, deliver a
telemetry-sequence gap, drain recording, release the lock. The speed command succeeds while
the walk is interrupted.

## What to do

1. **SafetyCore:** add a non-fault review state, for example `recording_review`, with a
   revision counter like `readiness_revision`, set through a new application op (for
   example `recording_review` with args `review: bool, revision: int`, rejecting old
   revisions the same way `recording_ready` does).
   - Setting review to true must bump `motion_generation`, so motion already waiting for the
     writer is cancelled by `write()`'s existing `motion != self.motion_generation` check.
   - While it is true, `check_authority(..., motion=True)` and `before()` must both refuse
     motion with a clear `ValueError` / `CommandCancelled`.
   - It must not trip a fault, stop the belt, clear the grant, or affect Stop, owner_lost,
     release, recover, acquire or any telemetry or health deadline.
   - Include it in `snapshot()`.
   - Reset it on `attach_application` / `detach_application`, the same way
     `recording_ready` is reset. Decide and document whether a new application starts with
     review true or false. Prefer fail-closed: true until the application publishes false.
2. **Application controller:** when `tracking_review` turns on, send review=true to safety
   immediately and synchronously at the point the interrupt is queued. `SafetyClient.send`
   writes to the socket synchronously, so ordering on the socket is preserved. When it turns
   off (after resolution, in `recorded()`), send review=false.
   - Don't await inside `received()`; it's a synchronous callback. Use a fire-and-forget
     send, or `spawn`, and make sure a send that is lost because safety is unavailable
     leaves motion blocked: safety resets to fail-closed on reattach, and
     `publish_readiness` / reconnect must republish the current review state.
   - Republish the review state after `initialize()` and after a safety reconnect.
3. **Stop kernel:** in `control_core.Controller.record()`, when an interrupt or
   safety_evidence is queued, bump `motion_generation`, so queued motion in `write()` is
   cancelled. Keep the existing dispatch check.
4. **Tests:**
   - SafetyCore unit tests (`tests/test_safety_core.py`): review=true cancels a motion write
     queued behind the held writer lock; refuses new motion; does not trip a fault, stop or
     clear the grant; old revisions are rejected; detach/attach resets fail-closed; review
     doesn't block Stop.
   - Facade test (`tests/test_safety_facade.py`, real `SafetyCore` + `SimulatorBackend`
     over IPC): the exact repro above now fails the queued set_speed, and motion works again
     after `resolve_session`.
   - Kernel test: queued motion behind the lock is cancelled by a queued interrupt.
   - All existing tests must still pass.
5. Update `docs/` where the safety IPC operations are described (search for
   `recording_ready`) to document the new op.

## Safety boundary

This is safety-critical code. Never connect to, arm or move a physical treadmill. Tests use
`SimulatorBackend` and fakes only. If a step can't be done without changing Stop, fault or
recovery behaviour, stop and report instead.

## Checks (all must pass)

```bash
node --test --test-isolation=none
uv sync --locked && uv run --frozen python -m unittest discover -s tests -p 'test_*.py'
```

Socket-based tests may fail inside the Codex sandbox with PermissionError. Report which ones,
and Claude will run them outside it.

## Rules

- Don't commit, push or create branches. Leave the changes in the working tree.
- Don't edit `PLAN.md` or anything under `docs/handoffs/`.
- Match the surrounding code style (compact one-line style in safety_core.py and controller.py).
- Report what you changed, why, and the test output.
