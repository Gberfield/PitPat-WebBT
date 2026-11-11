# T15: Keep a durable log of every Stop and the reports around it

## Context

PitPat-WebBT controls a PitPat treadmill. The safety process
(`bridge/safety_main.py`, `bridge/safety_core.py` `SafetyCore`, IPC in
`bridge/safety_ipc.py`) owns Bluetooth and Stop. `Controller.stop()` /
`perform_stop()` in `bridge/control_core.py` write the Stop command and confirm
it when a report after the write has state 3 and zero speed
(`receive_packet`, `Telemetry.stopped`), within `STOP_TIMEOUT` (5 s). Stop
requests arrive from the application (`handle_application`, e.g. the menu bar,
browser or tray) and from helpers (`kind:"helper"`, e.g. `pitpat stop`, the
macOS Stop hotkey and the Siri Stop intent), plus internal callers
(trips, initial connection verification, disconnects).

Under launchd, safety's stdout and stderr go to `~/Library/Logs/PitPat/safety.log`
(`integration/launchd/com.gberfield.pitpat.safety.plist`; systemd on Linux keeps
its own journal). Today nothing is written there after startup, and the
in-memory evidence ring is lost when safety restarts.

On November 11, 2026 a Stop was reported as stopped while the owner says the belt
kept moving. Safety had restarted before anyone could look, so it can't be
traced. This task makes the next one traceable. It must not change behaviour.

## What to do

1. In the safety process, log one line per event, as compact JSON with an ISO
   UTC timestamp, to stderr (so launchd/systemd capture it), flushed per line:
   - every Stop request: source (`helper`, `application` with the client kind if
     known, or the internal reason such as a trip or initial verification),
     the reason string, link state, connected, authorization state, and the last
     report's state, `speed_raw` and age;
   - every Stop result: outcome, confirmed, the confirming report's state and
     `speed_raw` (or why it wasn't confirmed: timeout, link change, writer
     uncertain), and elapsed time;
   - every telemetry report from the Stop write until 15 seconds after the Stop
     finishes, with sequence, state, `speed_raw`, distance and duration;
   - fault trips and recovery acknowledgements (id, reason).
   Logging must never raise into or block the safety paths: wrap it so a write
   error is swallowed, and do no I/O other than the line write. Don't log raw
   packets beyond the fields above.
2. In the macOS menu bar, log each `SafetyStop` outcome (from the Stop hotkey,
   `App.swift` `safetyStop()`) with `os.Logger` (subsystem
   `com.gberfield.pitpat.menubar`), so `log show` can find them. This task
   starts from `main`; Siri intents live on an unmerged branch and get the same
   logging when merged, so don't add intent code here.
3. Document how to read these logs in `docs/macos-operations.md`
   (Troubleshooting) in two or three lines.
4. Tests: with the simulator backend and fakes, assert the Stop request/result
   lines and the post-Stop report window are logged for a confirmed Stop, an
   unconfirmed Stop (timeout) and a helper Stop; assert a failing log write
   doesn't change the Stop outcome. Existing tests must pass unchanged.

## Safety boundary

Safety-critical code: behaviour must not change at all (same Stop writes,
confirmation rule, timeouts, faults, refusals and timing apart from the log
writes). Never connect to, arm or move a physical treadmill; tests use
`SimulatorBackend` and fakes only. If logging can't be added without changing
behaviour, stop and report.

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
- Match the surrounding compact style (one-line style in `safety_core.py`).
- Report what you changed, a sample of each log line, and the check output.
