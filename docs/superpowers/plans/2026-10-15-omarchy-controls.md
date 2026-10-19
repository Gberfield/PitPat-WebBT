# Omarchy Controls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver native Omarchy controls backed by one BLE owner and one durable record for each new walk, including walks with Firefox closed.

**Architecture:** Extend the accepted Python bridge with shared recording, observer/controller roles and private Unix IPC. A shared Quickshell plugin service owns the native lease; per-monitor widgets display its state and popup. The browser reads canonical bridge walks alongside preserved local history and retains the existing Notion export mapping.

**Tech Stack:** Existing Python/aiohttp/Bleak environment, standard-library SQLite/Unix sockets, vanilla JavaScript, installed Quickshell 0.3.1 and Omarchy QML APIs, Hyprland Lua, user systemd.

**Spec:** [Approved specification](../specs/2026-10-15-omarchy-controls-design.md).

**Execution:** Current chat only, no additional agents/model calls. Plan reviewed and approved; implementation and scoped installation performed. Host/physical/export acceptance remains pending in Task 7. Preserve the current uncommitted Firefox implementation and all earlier changes; Git author identity is not configured, so defer commits rather than invent authorship. No desktop restart or shutdown is authorized.

## Global Constraints

- Use the accepted real dashboard origin `http://127.0.0.1:8766/`; preserve its history.
- One motion owner; observers never renew its lease or record separate live walks.
- Owner renewal every second; six seconds without renewal requests Stop.
- Stop requires write completion and fresh stopped/zero-speed telemetry within five seconds.
- Five seconds without valid telemetry blocks motion and requests Stop.
- Motion speed is integer 1000–6000 in increments of 100; preserve MPH rounding and Cal/miles display.
- Transfer only on fresh stopped/zero state, with no in-flight Stop, orphan/recovery or storage fault.
- Closing a controlling browser tab stops its walk; closing a browser observer does not stop a tray-owned walk.
- Closing the tray popup retains its lease; losing the last native widget/controller requests Stop.
- Startup, connect, observation, transfer, reconnect and record reconciliation never start motion.
- No login startup or automatic service restart. No packaged Omarchy edits or changes to `gabe.tray`.
- Protect runtime directory mode 0700, native socket 0600 and peer UID; retain browser Host/Origin/token checks.
- Keep existing browser histories and backups. No silent legacy upload, deletion or reconciliation.
- Exercise timestamps display in America/New_York; raw precise instants remain machine data.
- Use synthetic backends during automated checks; physical and real-host GUI acceptance is separately supervised.

## Review Focus

1. A browser losing ownership during a pending motion command must not replay it or renew the replacement owner — Task 2.
2. A database commit stalling/failing mid-walk must not block Stop or falsely report a saved finished record — Task 1.
3. An observer opening while already walking must see the active walk without creating another record or making Start available — Tasks 2 and 4.
4. Removing one widget on a multi-monitor desktop must retain the remaining native controller, while removing the last requests Stop — Task 5.
5. User config changing after staging must cause installation/rollback to refuse stale overwrites — Task 6.

## Files and responsibilities

| Files | Responsibility |
| --- | --- |
| `bridge/store.py`, `bridge/recorder.py` | Private transactional walk store and telemetry-driven session lifecycle |
| `bridge/controller.py` | Roles, ownership transfer, global Stop, recording/fault integration |
| `bridge/messages.py`, `bridge/native.py` | Shared message validation and bounded peer-authenticated Unix IPC |
| `bridge/server.py`, `bridge/__main__.py` | Observer-aware WebSockets, protected history routes and runtime startup |
| `transports.js`, `treadmill.js`, `walks.js`, `index.html` | Observer/owner UI, canonical history, legacy merge and Notion mapping |
| `integration/omarchy/gabe.pitpat/manifest.json` | Service/bar-widget manifest, one plugin ID, no multiple copies per bar |
| `integration/omarchy/gabe.pitpat/Service.qml` | One native connection, leases, state, widget registration and IPC methods |
| `integration/omarchy/gabe.pitpat/Widget.qml`, `Model.js` | Popup/bar view and pure UI enablement/unit formatting |
| `bridge/desktop.py`, `integration/bin/pitpat` | Launcher/shortcut routing, on-demand service start and native Stop |
| `integration/systemd/pitpat-bridge.service`, `integration/applications/pitpat.desktop` | Manually startable user service and launcher templates |
| `scripts/install-omarchy.py` | Plan/apply/rollback with scoped backups and drift checks |
| `tests/test_bridge_store.py`, `tests/test_bridge_recorder.py`, `tests/test_bridge_native.py` | Durable recording and actual Unix socket boundary tests |
| Existing controller/server/browser suites; `tests/omarchy-model.test.cjs` | Ownership, browser and native model regressions |
| `tests/test_omarchy_install.py`, `tests/omarchy-acceptance.md` | Disposable config tests and actual host/hardware checklist |
| `README.md`, `docs/omarchy-controls-acceptance.md` | Operation, verified outcomes, pending gates and rollback |

## Task 1: Durable shared recording without a browser

**Interfaces:** `WalkStore(path: Path)` exposes `save(walk: dict, current: bool)`, `page(limit:int, before:str|None) -> dict`, `current() -> dict|None`, and `merge(records:list[dict]) -> dict`. Store schema version is 1; preserve complete JSON payloads and unknown fields, keyed by `sessionId`. `Recorder(store, clock_ms)` exposes `before_start(report)`, `observe(report)`, `interrupt(reason)`, `resolve(session_id, choice)`, and `snapshot()`. Lifecycle methods are async where they persist. `RecordingWorker(recorder,on_fault,on_update)` exposes synchronous `offer(kind,payload) -> bool` and async `drain()`; it serializes lifecycle operations through a bounded 256-item FIFO. Callbacks publish state/fault events without waiting on clients. Recording output remains schemaVersion 2/trackingVersion 1 compatible with `walks.js`.

- [x] Add failing `test_bridge_store.py` cases using temporary directories: exact unknown-field roundtrip, duplicate identical import is a no-op, conflicting ID import rolls back the whole batch, active ID/payload update is atomic, bad schema versions refuse without deletion, and database/runtime permissions remain private under a permissive process umask. Independent assertions include `len(store.page(50,None)['walks']) == 1` after two identical imports and unchanged payload after a conflicting import.
- [x] Add recorder fixtures with literal counters: pre-start zero baseline then running 600 seconds/1000 steps/0.5 mi/30 Cal yields one 600-second record; pause/resume keeps its ID; a second walk with counters 660 seconds/1100 steps/0.6 mi/35 Cal yields 60 seconds/100 steps/0.1 mi/5 Cal using an observed 600-second stopped baseline. Assert count two, not cumulative duplication. Countdown followed by Stop creates no counted walk.
- [x] Add reset/gap tests: stopped counter reset preserves prior totals; moving reset preserves the old segment and marks coverage partial; missing baseline never fabricates zero-based coverage; restart retains interrupted ID; `resolve(id,'continue')` preserves ID/partial coverage, and `resolve(id,'new')` retains the previous evidence and establishes a new observed boundary. Neither writes any motion command.
- [x] Add `test_stalled_commit_does_not_block_stop`: hold the storage worker at its I/O boundary while the real controller accepts Stop and confirms it from fresh telemetry. Assert Stop succeeds before releasing the commit gate. For a failed commit, assert a storage-fault event, blocked motion, no false saved-completion event, and unchanged last committed row.
- [x] Run `uv run --frozen python -m unittest tests.test_bridge_store tests.test_bridge_recorder -v`; observe failures for missing functionality, then implement `store.py` and `recorder.py`. Use private paths `XDG_STATE_HOME/pitpat/walks.sqlite3` or default `~/.local/state/pitpat/walks.sqlite3`; simulator uses `pitpat/simulator/`. Reject symlinked/unowned state paths. SQLite WAL transactions run via a serialized worker outside the event loop; bounded recorder queue overflow raises a storage fault and independently requests Stop.
- [x] Integrate validated telemetry recording into the controller without awaiting disk work in the notification/write path. Snapshot a known stopped counter baseline at the actual successful-generation Start-write boundary; create the walk only on observed running. Include every received valid running sample in speed sum/count/max; sample the compact trace at five-second intervals. Mark active duration and active-versus-total energy unknown. Startup must open the store before BLE motion can be enabled.
- [x] Rerun recorder/store and existing controller/protocol suites; expected all green with no hardware access. Preserve a reviewed source snapshot under the ignored task workspace before edits; commits are scoped to Task 1 files when identity becomes available.

## Task 2: Explicit roles, stopped ownership transfer and global Stop

**Interfaces:** Extend `Controller(backend, clock, recorder=None)` with `register_client(id, kind)`, `unregister_client(id)`, `snapshot_for(id) -> dict`. `kind` is assigned by transport (`browser`, `tray`, `helper`), never an arbitrary command-supplied privilege. Add semantic operations `observe`, `take_control`, `resolve_session`; existing motion and Stop methods retain their signatures. Each recipient snapshot includes `is_owner`, owner kind/label, state, blocked/recovery/storage-fault flags, current generation and compact active-session summary. Emit `ownership` and `walk` events as well as existing events.

- [x] Write failing controller tests: observers receive state without acquiring/renewing a lease; observer Start/Pause/speed reject with zero BLE writes; an observer's disconnect has no effect on the owner; an owner's loss requests Stop even with two observers still connected.
- [x] Test `test_transfer_cancels_old_motion_and_renewals`: with fresh stopped/zero telemetry, an explicit `take_control` moves the lease, invalidates queued old-owner motion and rejects its renewals. Assert no Start on transfer, new target 1000, and only new-owner motion can write. Reject stale (>= five seconds), paused, starting, nonzero-speed, pending-Stop, orphan and storage-fault transfers. Increment the connection/control generation on transfer and bind notification callbacks to a separate BLE-link epoch so legitimate telemetry survives control transfer while stale transport commands do not.
- [x] Test authenticated Stop from a non-owner and helper: it cancels pending motion but grants no motion ownership. Test Stop & Disconnect clears ownership for every view only after confirmation. A failed Stop cannot be bypassed by `take_control`; use the existing explicit orphan recovery route.
- [x] Test two subscribed views plus one recorder: both receive identical active IDs/counters; Stop finalizes one row. Test an observer joining mid-walk neither changes coverage nor starts a duplicate. Failed recording blocks Start/speed but never blocks Stop. Unresolved interrupted tracking requires an explicit owner `resolve_session` with matching ID; resolution does not move the belt.
- [x] Run `uv run --frozen python -m unittest tests.test_bridge_controller tests.test_bridge_recorder -v` red, implement the role registry/generation changes and recorder fault handling, then run green. Keep five/six-second deadlines monotonic and owner-specific. Do not weaken heartbeat serialization or accepted fresh-Stop checks.
- [x] Run the whole Python bridge suite. Record passing checks/deviations; commit only scoped changes when identity permits.

## Task 3: Private native IPC and protected observer/history endpoints

**Interfaces:** `NativeServer(controller, runtime_dir)` creates `XDG_RUNTIME_DIR/pitpat/control.sock`; simulator uses `XDG_RUNTIME_DIR/pitpat-simulator/control.sock`. `serve()` and `close()` own listener lifecycle. Native first frame is `{v:1,op:'hello',kind:'tray'|'helper'}` after peer-UID admission. Subsequent newline-delimited frames use existing `{v,id,op,generation,args}` requests. Shared parser/validator moves to `messages.py`, re-exported from `server.py` where existing imports require it. New HTTP bootstrap capabilities are `{recording:'bridge',observers:true}` in addition to existing fields. Authenticated WebSockets invoke `observe` after authorization; observation alone does not connect BLE. History pages return `{walks:[...],next_cursor:string|null}`; the browser passes the opaque next cursor as `before` without deriving it.

- [x] Add actual Unix boundary tests in temporary private directories: foreign UID admission refused using a bounded credential-reader seam; real same-UID connection allowed; socket 0600/directory 0700; symlink/unowned path and occupied listener refused without unlinking it. Acquire an exclusive mode-0600 `service.lock` in the same private runtime directory before opening the database or listeners; a second process must refuse without modifying records or the active socket. Helpers cannot acquire motion ownership. Accepted sockets must call `unregister_client` on EOF and trigger owner loss for a tray lease.
- [x] Test fragmented frames, duplicate JSON keys, invalid UTF-8/types, more than 16 KiB before newline, oversized IDs, speed bounds, request floods, and queue overflow. Reject before dispatch; bounded writer tasks must not hold the BLE writer. Use max 64 outbound events and max eight concurrent requests as on WebSockets. Limit reads before allocation, not after accumulating unlimited data.
- [x] Update HTTP tests for observer snapshots, foreign Host/Origin/token rejection and shared capabilities. Extra authenticated observers may receive status/telemetry now, but never motion authority; replace the old second-client event-isolation assertion with explicit read-only ownership assertions. Preserve all other security tests.
- [x] Add `GET /api/walks?limit=50&before=...`, requiring `X-PitPat-Token` and the existing same-origin protections, with a maximum limit 100 and stable cursor pagination. Add token-protected JSON `POST /api/walks/import` only for explicit user imports, max body 4 MiB, and transactional all-or-nothing conflicts. Exempt only this exact POST route from the old GET-only middleware; do not enable CORS or a general command POST route. Responses are non-cacheable and expose no state-file path. `resolve_session` is a semantic owner command with args `{session_id,choice:'continue'|'new'}`.
- [x] Run `uv run --frozen python -m unittest tests.test_bridge_native tests.test_bridge_server -v` red, implement both boundaries and CLI lifecycle, then green. Extend CLI with `--state-dir` and `--runtime-dir` overrides for explicit simulator/disposable tests, keeping the production default paths above. Preserve existing foreground operation; no daemon reload or real-service replacement yet.
- [x] Run all Python bridge tests. Expected: no real adapter access, no leaked socket/tasks, all deadlines/security checks pass. Commit scoped paths when identity permits.

## Task 4: Browser observation, shared history and unchanged Notion identities

**Interfaces:** Extend `BridgeTransport` with `observe()`, `takeControl()`, `walks({limit,before})`, `importWalks(records)`, `resolveSession(id,choice)`. Renewal depends on server-confirmed `is_owner`; authorization alone is not ownership. Add pure `PitPatWalks.combineHistories(local,shared) -> array`, deduplicating identical stable IDs and throwing on conflicting payloads after normalizing known legacy fields. New bridge capabilities select server recording; direct/old bridge paths retain the accepted local recorder.

- [x] Add failing Node tests: a browser observer renders active metrics/history with Start/Pause/speed disabled and Stop available; it sends no renewal and calls no local live recorder. Closing it leaves a native owner's lease intact. Taking control requires fresh stopped state and resets its target; stale ownership responses cannot restore controls or replay old requests.
- [x] Add legacy/shared-history cases: repeated shared updates replace one live ID in the displayed view, completed rows are not counted twice, a conflicting ID blocks export visibly, raw localStorage and its backup remain byte-identical on page load, and an explicit JSON import succeeds only after server commit acknowledgement. No shared row is deleted by the old local-only Delete action; leave shared deletion unavailable in this task.
- [x] Test Notion export with one real-shaped shared fixture seen by two views: `buildNotionExport(combineHistories(...)).walks.length === 1` and source ID `pitpat:<canonical-sessionId>`. Reusing that export in `scripts/prepare-notion-import.cjs` against an identical destination yields zero creates. Preserve original unknown metadata and no guessed active duration/Calories.
- [x] Run `node --test --test-isolation=none tests/transports.test.cjs tests/units.test.cjs tests/notion-export.test.cjs` red, implement capability-gated browser changes and explicit owner/observer labels/actions, then green. Keep fresh native `fetch` receiver binding and keyboard tab focus fixes. Display storage errors independently of live safety state.
- [x] Run the complete Node suite; expected all accepted direct-path/history/export tests plus new shared cases green. Commit scoped paths when identity permits.

## Task 5: Quickshell service, popup, shortcuts and launcher

**Interfaces:** `gabe.pitpat` manifest declares `service` and `bar-widget`, `keepLoaded:true`, entries `Service.qml`/`Widget.qml`, `allowMultiple:false`. The installed shell's `serviceFor('gabe.pitpat')` lookup supplies one shared service to all widgets. Service methods: `registerView(key)`, `unregisterView(key)`, `connectDevice(id)`, `takeControl()`, `startPause()`, `stop()`, `stopDisconnect()`, `release()`, `setTargetMph(value)`. Use Quickshell.Io `Socket` with `SplitParser` and newline writes/flush, verified against installed qmltypes. `Model.js` exposes pure `view(snapshot,isOwner)` and `targetUnits(mph)` for Node tests.

- [ ] Add failing `omarchy-model.test.cjs` cases for all specified states, stale/disconnected metrics, simulator label, owner-only motion, global Stop during starting, and exact rounded MPH limits. Pure model functions must be importable under Node as well as QML without duplicating unit conversions.
- [ ] Implement shared `Service.qml` using one persistent native socket, one-second owner renewals and bounded pending-request handling. Register each widget with a stable instance key; closing a popup does not unregister. Last-view removal sends Stop & Release where possible and closes native ownership, even though `keepLoaded` keeps the service object alive. A remaining monitor view retains it. Do not reconnect ownership or replay motion automatically after socket loss.
- [ ] Add `IpcHandler` target `gabe.pitpat` with `startPause()` and `stop()` routed through the shared service; popup open/toggle uses the supported shell plugin route. `bridge/desktop.py` exposes `main(argv)` operations `controls`, `start-pause`, `stop`, `dashboard`, `history`. `controls` starts the manually startable bridge service on demand and opens/toggles the widget; `start-pause` only calls the live native service, never silently claims a lease. `stop` may use the authenticated one-shot helper route if the widget is unavailable. Dashboard/history use the standard browser launcher without controlling any existing browser window.
- [ ] Build the popup from installed `Panel`, `KeyboardPanel`, `WidgetButton`, `Label` and `Action` conventions; reuse the existing theme. Device choice is explicit. Provide all approved metrics/actions and persistent fault/owner messages. Keep Stop operable during countdown/loading and render ordinary status separately from faults. No scan/service start from component construction.
- [ ] Run model/helper tests red→green. Add helper boundary tests with controlled command executables: absent shell gives a visible error, Start/Pause never falls back to direct BLE, Stop does not acquire ownership, and service start has no scan/motion side effect. Use exact argv arrays, no shell-interpolated paths/URLs or secret logging.
- [ ] Verify service/widget loading with the installed QML tools in a non-host disposable configuration or already approved hidden desktop, using the explicit simulator runtime/state paths. Test two widget views, popup close, last-view removal, unknown/failing Stop and reconnect without automatic motion. Do not start/stop a desktop outside its lifecycle approval or claim headless syntax checks prove host installation.
- [ ] Run complete Node and Python suites; record QML runtime outcomes separately from mocks. Commit staged integration files when identity permits.

## Task 6: Stage and activate a reversible per-user installation

**Interfaces:** `scripts/install-omarchy.py --plan OUTPUT.json` reads user config and emits exact path/hash/preimage/postimage operations without mutation. `--apply OUTPUT.json` verifies the approved hashes and writes only scoped integration/config files. `--rollback OUTPUT.json` restores only unchanged installed postimages; if files drifted, refuse destructive restoration. Accept `--home`/`--runtime-dir` test roots so automated tests never touch actual user configuration.

- [x] Add installer tests on temporary homes: preserve unrelated bar/plugins/bindings exactly, insert one right-section `gabe.pitpat` entry, install a disabled manually startable service/launcher/helper, back up exact bytes/hashes in a private manifest, reapply without duplication, and refuse symlinked destinations or edited preimages. Rollback must retain the walk database and exported JSON; changed postimages cause a clear hold, not overwrite. Test conflict detection for every proposed shortcut.
- [x] Implement staged templates and installer. User paths are `~/.config/omarchy/plugins/gabe.pitpat/`, `~/.config/omarchy/shell.json`, `~/.config/hypr/bindings.lua`, `~/.config/systemd/user/pitpat-bridge.service`, `~/.local/share/applications/pitpat.desktop`, and `~/.local/bin/pitpat`. Private backup manifest goes under `~/.local/state/pitpat/install-backups/` with Eastern-offset timestamps. No files outside the enumerated plan are modified. Use file-byte backups, atomic replace and preimage rechecks immediately before writes.
- [x] Service template uses repository WorkingDirectory and `.venv/bin/python -u -m bridge --port 8766`, `UMask=0077`, `Restart=no`, `TimeoutStopSec=35`, and no enablement target. Helper launchers use fixed absolute paths recorded in the install plan. No `systemctl enable`, login-startup entry or system package installation.
- [x] Run installer tests red→green and inspect the generated actual-user install plan. Re-read the Omarchy plugin/Hyprland guides, live/default bindings and current file hashes. Proposed bindings are Super+F9 controls, Super+F10 Start/Pause, Super+F11 Stop, using `o.bind` without repeat flags. Preserve Super+Shift+F12. Stop if a conflict appeared rather than rebinding silently.
- [x] Before activation, confirm with the user that the belt is stopped/disconnected and current records are resolved/exported. Snapshot all accepted Firefox runtime source needed for rollback, excluding private data/dependencies. No service interruption before this safe activation condition is established. Write outside-workspace paths only through normal narrow permission approval.
- [x] Stop the old transient `pitpat-bridge.service` once safe, install the approved files, run `systemctl --user daemon-reload`, and start the upgraded manually startable unit. Never run a second real bridge or change port/history origin. Do not enable it. Use supported hot reload for the added widget and `hyprctl reload` followed by `hyprctl configerrors` for bindings. A shell/desktop restart is not a fallback.
- [x] Verify service HTTP 200, private socket/database modes, only one listener/controller, expected files/hashes and no Hyprland errors. If activation fails, keep motion blocked, report exact state and apply only safe manifest rollback; preserve new records. Commit repository templates/docs, not private config snapshots or health data, when identity permits.

## Task 7: Verify real Omarchy flows and one exported physical walk

**Files:** `tests/omarchy-acceptance.md`, `docs/omarchy-controls-acceptance.md`, `README.md`, Notion task 5 progress.

- [ ] Run `node --test --test-isolation=none`, `uv run --frozen python -W error::ResourceWarning -m unittest discover -s tests -p 'test_*.py' -v`, `uv lock --check --offline`, JavaScript syntax checks for changed files, and `git diff --check`. Expected exit zero for every check. Keep source snapshots/ledger and report any missing QML/GUI coverage explicitly.
- [ ] Perform a separate author review of the complete change against spec and Review Focus; no extra agents. Verify storage failure cannot deadlock Stop, observers cannot steal motion, native multi-monitor lifetime is correct, service startup has no BLE activity, and older direct Chromium recording is unchanged. Fix material findings with observed red→green tests, then rerun affected suites.
- [ ] Agree on a brief visible-host handoff if agent GUI operation is needed; otherwise ask the user to perform the checks. Existing task approval does not grant visible desktop control or shell shutdown. Verify bar icon/theme, all states, popup keyboard use, launcher and three shortcuts on the actual Omarchy session. Hidden Firefox success is not host-bar proof.
- [ ] With the user beside the treadmill and physical stop ready, verify tray connect/minimum-speed Start, MPH adjustment, Pause/Resume, Stop during starting, confirmed Stop & Disconnect, and Start/Pause/Stop bindings. Verify stopped ownership transfer both directions; each new owner must explicitly Start. Close Firefox in browser-owned mode (stops) and tray-owned observer mode (continues); then remove/release the last native controller (requests Stop). Keep actual BLE-loss/sleep/crash claims unverified unless separately tested.
- [ ] Verify one real tray-controlled walk remains visible after Firefox was closed and reopened, has one stable canonical ID and one History row, and produces exactly one Notion export source record through existing `walks.js` mapping/import planner. Prepare the concrete export for review; upload only within the user's authorized Notion workflow, never automatically from the widget.
- [ ] Record actual outcomes/remaining limits, retain desktop/profile state, pause any own GUI input and restore any task-specific policy changes. Mark Notion task 5 Done only after required host/hardware/export acceptance; otherwise keep In progress with precise pending checks. Do not close the separate real-link-loss safety follow-up on the strength of tab/tray exit.

## Self-review and handoff

- Tasks 1–4 form the dependent foundation for task 5; install and acceptance follow. They share explicit recorder, controller and message contracts rather than independent competing implementations.
- The existing accepted branch has uncommitted code and no author identity. Preserve its actual working bytes, not just HEAD, for rollback. This plan does not authorize inventing an identity, pushing, merging, enabling login startup or desktop interruption.
- Both transports use the same role registry, validation, serialization and recorder. Native helper Stop is the documented non-owner exception; one-shot helpers never renew or own a motion lease.
- Existing control-generation guards must be split from BLE-link epoch guards during transfer; otherwise rebasing ownership could silently discard valid telemetry. Task 2 explicitly owns and tests this change.
- Every Review Focus item has an assigned test. All approved spec sections map to tasks; no product dependencies, running service, desktop config or history changed while writing this plan.
- Plan approval remains pending. Execution stays in this chat using the preserved inline method.
