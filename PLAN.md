# Project Plan

Goal: fix the implicit-state-machine defects recorded in GitHub issue #49 (2026-11-09). The other issues listed there stay recorded for later. T5 and T6 (proposed the same day) take the two cheapest of those, which lower risk in the safety code.

## Tasks

| ID | Task | Files | Acceptance check | Model | Effort | Status |
| --- | --- | --- | --- | --- | --- | --- |
| T1 | Block motion as soon as an interrupt is queued; one tracking_review rule (#41). Brief: docs/handoffs/T1-latch-tracking-review.md | bridge/controller.py, bridge/control_core.py, bridge/recorder.py, tests/test_safety_facade.py or a new focused test | New test refuses motion between queuing and writing an interrupt; both check commands pass; Codex review + adversarial review | gpt-6.1-sol | high | done |
| T2 | Browser records 'stopping' while the belt decelerates (#44). Brief: docs/handoffs/T2-browser-stopping-status.md | treadmill.js, possibly walks.js, tests/units.test.cjs | New test: running → state 3 moving → state 3 stopped gives stopping then completed; both check commands pass; Codex review | gpt-6.1-sol | medium | done |
| T3 | One motion-gate rule in the stop kernel and SafetyCore (#34). Brief: docs/handoffs/T3-single-motion-gate.md | bridge/control_core.py, bridge/safety_core.py, tests/test_bridge_controller.py, tests/test_safety_core.py | Existing tests unchanged and passing; new agreement tests; Codex review + adversarial review | gpt-6.1-sol | xhigh | done |
| T4 | Enforce the record-review gate at the serialized write boundary with a non-fault review state in SafetyCore (#50). Brief: docs/handoffs/T4-review-gate-at-writer.md. Starts from main after T1 and T3 are merged. | bridge/safety_core.py, bridge/controller.py, bridge/control_core.py, bridge/safety_client.py if needed, tests/test_safety_core.py, tests/test_safety_facade.py, tests/test_bridge_controller.py, docs on safety IPC ops | Facade repro (queued set_speed behind held writer, then telemetry gap) is refused; review never trips a fault or blocks Stop; both check commands pass; Codex review + adversarial review | gpt-6.1-sol | xhigh | done |
| T5 | One health check that includes expiry: rename `HealthMonitor.healthy`, add `is_healthy()` (#38). Brief: docs/handoffs/T5-health-monitor-is-healthy.md | bridge/safety_health.py, bridge/safety_core.py, tests/test_safety_ipc.py, tests/test_safety_client.py, a HealthMonitor unit test | Behaviour unchanged; existing tests pass after the rename; new HealthMonitor tests for expiry; both check commands pass; Codex review + adversarial review | gpt-6.1-sol | medium | done |
| T6 | Document the safety authorization states and fault-recovery path, with a state diagram (#36). Brief: docs/handoffs/T6-safety-recovery-path-doc.md | docs/safety-states.md (new), docs/README.md, docs/superpowers/plans/2026-10-15-dedicated-safety-process.md | Docs only; Claude checks every guard and time limit against the code; both check commands pass; Codex review | gpt-6.1-sol | medium | done |

### Siri integration (proposed November 11, 2026)

Design, owner decisions D1–D4 (settled 2026-11-11) and acceptance: docs/siri-integration.md. T9 brief: docs/handoffs/T9-siri-intents-spike.md. T10–T13 briefs follow T9's findings; they start from main after T9 is merged. T7 and T8 (the #61 and #62 fixes, 2026-11-09) are on the unmerged branch codex/t7-confirmation-bound-to-fault, not on main yet.

| ID | Task | Files | Acceptance check | Model | Effort | Status |
| --- | --- | --- | --- | --- | --- | --- |
| T9 | Spike: build emits App Intents metadata; one read-only status intent; installer copies the metadata; record launch-while-closed behaviour | scripts/build-menubar.sh, scripts/install-macos.py, integration/macos/PitPatMenuBar/ (Package.swift or a new Xcode project, a new Intents.swift), tests for the installer | Built app contains Metadata.appintents; installer test passes; intent listed in Shortcuts on simulator services; findings recorded; both check commands and swift test pass; Codex review | gpt-6.1-sol | high | verify |
| T10 | Status intents: state, speed, distance, time, steps from Model.view | integration/macos/PitPatMenuBar/Sources/PitPatMenuBar/Intents.swift, Tests/ | Swift tests over model-cases.json fixtures for every snapshot kind; both check commands and swift test pass; Codex review | gpt-6.1-sol | medium | proposed |
| T11 | Stop intent through SafetyStop.run; "Stopped" only on stopped_confirmed | Intents.swift, SafetyStop.swift if needed, Tests/ | Fake safety.sock tests for confirmed, unconfirmed, timeout and missing socket; both check commands and swift test pass; Codex review + adversarial review | gpt-6.1-sol | high | proposed |
| T12 | Motion intents allowed by D1 (Pause; Start with confirmation) through the owner's Service path | Intents.swift, Service.swift if needed, Tests/ | Refused when not owner or canStartPause is false; no take-control or connect by voice; simulator walk test; both check commands and swift test pass; Codex review + adversarial review | gpt-6.1-sol | xhigh | proposed |
| T13 | Siri docs: README, macOS operations, acceptance section, STATUS | README.md, docs/macos-operations.md, docs/macos-acceptance.md, docs/STATUS.md | Docs only; Claude checks phrases and wording against the code; Codex review | gpt-6.1-sol | low | proposed |

### Stop incident follow-ups (proposed November 11, 2026)

On 2026-11-11 at 4:55 PM a Stop during a 1.0 mph walk was reported as stopped (the walk ended on a state 3, zero-speed report) while the owner says the belt kept moving; later reports showed state 3 with speed 1.0 and the labels said "Stopped". See docs/STATUS.md. T14 and T15 start from main; the Siri tasks (T9–T13) are on unmerged branches.

| ID | Task | Files | Acceptance check | Model | Effort | Status |
| --- | --- | --- | --- | --- | --- | --- |
| T14 | "Stopped" label only for state 3 with zero speed, otherwise "Stopping" (tray, menu bar, Siri status, browser). Brief: docs/handoffs/T14-stopped-label-needs-zero-speed.md | integration/omarchy/gabe.pitpat/Model.js, integration/macos/PitPatMenuBar/Sources/PitPatMenuBar/Model.swift, treadmill.js, tests/gen-model-cases.cjs, tests/fixtures/model-cases.json, Swift tests | New stopped-state-moving fixture shows Stopping in JS and Swift; no control rule changes; all checks pass; Codex review | gpt-6.1-sol | medium | verify |
| T15 | Durable safety log of every Stop request/result, the reports for 15 s after, trips and recoveries; os.Logger lines for menu bar Stops and intents. Brief: docs/handoffs/T15-stop-outcome-log.md | bridge/safety_core.py, bridge/control_core.py, bridge/safety_ipc.py, menu bar Swift, tests, docs/macos-operations.md | Log lines for confirmed, unconfirmed and helper Stops; failing log write doesn't change outcomes; existing tests unchanged; all checks pass; Codex review + adversarial review | gpt-6.1-sol | high | verify |

Status values are proposed, approved, delegated, verify, done or blocked

Model is gpt-6.1-sol unless the human names another one for that task

Effort is low, medium, high or xhigh, fitted by Claude per task and adjustable by the human on approval

## Decisions

- 2026-11-11: the owner accepted the Siri recommendations D1–D4 in docs/siri-integration.md: Status and Stop first, then Pause, Start only with spoken confirmation, no speed changes; intents never start the services; Siri Stop matches the Stop hotkey exactly; the full Xcode may become a build requirement.
- 2026-11-09: T1's adversarial review found that motion queued before an interrupt can still be written (#50, already on main). The owner chose to keep T1 as is, since it narrows the window, and to fix the write boundary separately as T4.

