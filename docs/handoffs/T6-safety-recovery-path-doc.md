# T6: Write down the safety authorization states and the fault-recovery path (GitHub issue #36)

## Context

PitPat-WebBT controls a PitPat treadmill. Two processes share control:

- the safety process, `bridge/safety_core.py` `SafetyCore` (which extends the stop kernel
  `bridge/control_core.py` `Controller`), owns Bluetooth, Stop, faults and motion grants;
- the application process, `bridge/controller.py` `Controller`, handles clients (browser,
  tray), walk recording (`bridge/recorder.py`) and talks to safety over a Unix socket
  (`bridge/safety_client.py`, `bridge/safety_ipc.py`, messages in
  `bridge/safety_messages.py`).

## The problem

`SafetyCore.snapshot()` derives an `authorization_state` ('fault-latched', 'stopping',
'ready', 'unarmed') from `fault_id`, `stop_task` and `grant_id`; it is never stored. The way
back from a latched fault to a motion grant runs across both processes as a chain of guard
conditions, roughly: fault latched → a client claims recovery in the application (a
6-second claimant lease, renewable) → the interrupted walk record is resolved →
`recording_ready` is published to safety → a fresh Stop confirmation → `recover` →
`grant()` → ready. Since November 9, 2026 the non-fault `recording_review` gate (#50) also
blocks motion while an interrupted record needs review. No single place spells this out,
which makes changes that add or relax a guard hard to review.

The steps above are a summary from the issue. **The code is the authority**: read it and
describe what it actually does, and say so in your report wherever it differs from this
summary.

## What to do

1. Write a new doc, `docs/safety-states.md`, describing as they are in the code today:
   - the safety authorization states that `snapshot()` reports, what each means, and the
     exact condition for each;
   - the separate non-fault gates on motion: health (`HealthMonitor`), owner lease,
     telemetry freshness, `recording_ready`, `recording_review`, `storage_fault` and any
     other you find, and which of them trips a fault versus only refusing motion;
   - the fault-recovery path from fault latched to ready, step by step, naming for each step
     which process acts, the operation or client action involved, and the guard(s) that
     must hold (with the time limits, such as the 6 s leases and the 5 s freshness bounds),
     with file and function references;
   - how taking control while stopped without a fault (`acquire`) differs from recovery;
   - what resets on application attach/detach and on safety reconnect.
2. Include a state diagram as a Mermaid `stateDiagram-v2` block, with each transition
   labelled by its trigger and guard. Keep it readable; put detail in the text.
3. Link the new doc from `docs/README.md` (a short line in a sensible section) and from the
   "Safety IPC contract" section of
   `docs/superpowers/plans/2026-10-15-dedicated-safety-process.md`.
4. Docs only. Don't change any code or tests. If you find a guard that looks wrong or a
   path that looks unsafe, describe it in your report; don't fix it.

## Safety boundary

Never connect to, arm or move a physical treadmill. No code changes in this task.

## Checks (all must pass)

```bash
node --test --test-isolation=none
uv sync --locked && uv run --frozen python -m unittest discover -s tests -p 'test_*.py'
```

## Rules

- Don't commit, push or create branches. Leave the changes in the working tree.
- Don't edit `PLAN.md` or anything under `docs/handoffs/`.
- Write plainly, in the style of the existing docs (short sentences, US English).
- Report what you wrote, every place where the code differed from the summary above, and
  anything that looked wrong.
