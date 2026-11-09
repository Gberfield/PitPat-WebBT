# Project Plan

Goal: fix the implicit-state-machine defects recorded in GitHub issue #49 (2026-11-09). The other issues listed there stay recorded for later.

## Tasks

| ID | Task | Files | Acceptance check | Model | Effort | Status |
| --- | --- | --- | --- | --- | --- | --- |
| T1 | Block motion as soon as an interrupt is queued; one tracking_review rule (#41). Brief: docs/handoffs/T1-latch-tracking-review.md | bridge/controller.py, bridge/control_core.py, bridge/recorder.py, tests/test_safety_facade.py or a new focused test | New test refuses motion between queuing and writing an interrupt; both check commands pass; Codex review + adversarial review | gpt-6.1-sol | high | done |
| T2 | Browser records 'stopping' while the belt decelerates (#44). Brief: docs/handoffs/T2-browser-stopping-status.md | treadmill.js, possibly walks.js, tests/units.test.cjs | New test: running → state 3 moving → state 3 stopped gives stopping then completed; both check commands pass; Codex review | gpt-6.1-sol | medium | done |
| T3 | One motion-gate rule in the stop kernel and SafetyCore (#34). Brief: docs/handoffs/T3-single-motion-gate.md | bridge/control_core.py, bridge/safety_core.py, tests/test_bridge_controller.py, tests/test_safety_core.py | Existing tests unchanged and passing; new agreement tests; Codex review + adversarial review | gpt-6.1-sol | xhigh | done |
| T4 | Enforce the record-review gate at the serialized write boundary with a non-fault review state in SafetyCore (#50). Brief: docs/handoffs/T4-review-gate-at-writer.md. Starts from main after T1 and T3 are merged. | bridge/safety_core.py, bridge/controller.py, bridge/control_core.py, bridge/safety_client.py if needed, tests/test_safety_core.py, tests/test_safety_facade.py, tests/test_bridge_controller.py, docs on safety IPC ops | Facade repro (queued set_speed behind held writer, then telemetry gap) is refused; review never trips a fault or blocks Stop; both check commands pass; Codex review + adversarial review | gpt-6.1-sol | xhigh | done |

Status values are proposed, approved, delegated, verify, done or blocked

Model is gpt-6.1-sol unless the human names another one for that task

Effort is low, medium, high or xhigh, fitted by Claude per task and adjustable by the human on approval

## Decisions

- 2026-11-09: T1's adversarial review found that motion queued before an interrupt can still be written (#50, already on main). The owner chose to keep T1 as is, since it narrows the window, and to fix the write boundary separately as T4.

