# Firefox Bluetooth Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Control and track the BA09-B from Firefox through a local service, preserving current walk data and confirmed-stop behavior.

**Architecture:** A Python service serves the dashboard and an authenticated same-origin WebSocket on loopback. A single controller owns BLE, command serialization, lease expiry and stop confirmation. A browser transport adapter feeds the existing dashboard and session model; Chromium's static-server direct route remains supported.

**Tech Stack:** Existing vanilla JavaScript and Node test runner; Python 3.14 on this host; aiohttp, Bleak, uv project lockfile; standard-library unittest with asyncio; synthetic BLE simulator.

**Spec:** [Approved design](../specs/2026-10-15-firefox-bridge-design.md).

**Execution status:** Software implemented; core native Firefox simulator and user-supervised physical acceptance passed, including tab closure and reconnect without motion. Epic task 4 accepted. See `docs/firefox-bridge-acceptance.md` for evidence, optional unchecked GUI exercises and unverified radio-loss/sleep/crash behavior. Git commits remain deferred for missing author identity.

**Execution:** Implement in the current chat, without additional agents or model calls. Review this plan before implementation. Preserve the current uncommitted source changes: they are the working units, tracking and stop-safety baseline, not disposable edits.

## Global Constraints

- Bind only `127.0.0.1`; normal URL `http://127.0.0.1:8765/`.
- Speed is an integer metric protocol value, 1000–6000 inclusive in increments of 100.
- Browser lease heartbeat every second; monotonic lease expiry after six seconds.
- Stop deadline five seconds for both write completion and fresh stopped/zero-speed telemetry.
- Five seconds without valid telemetry blocks motion and requests Stop.
- No motion on connect, reload, reconnect, startup or automatic transport fallback.
- Keep Stop available during starting/countdown; only confirmed Stop permits intentional BLE disconnection.
- One controller; serialized writes; connection generations invalidate obsolete operations.
- Keep browser history, stable IDs, backups and Notion mappings intact. Firefox history transfers through existing export/import.
- Exact Host and Origin checks, non-cacheable bootstrap, per-process token in first WebSocket message, no CORS or arbitrary GATT writes.
- Synthetic checks never scan or command hardware. Physical acceptance remains separately user supervised.
- No system-package replacement, tray configuration, automatic startup, Notion writes or health-data fixtures.
- True BLE loss, service crash and computer sleep cannot guarantee delivery of Stop.

## Review Focus

1. A browser closing during connection establishment must not leave a late BLE connection ownerless and able to accept motion — Task 2.
2. A slow telemetry consumer must not delay backend heartbeats or emergency Stop — Tasks 2 and 3.
3. A response from a replaced socket/connection must not change current UI state or resolve a new request — Tasks 2 and 4.
4. Oversized scans/messages and path traversal must fail without BLE writes or exposing repository/private files — Task 3.
5. Browser-storage failure during a walk must not interrupt bridge lease renewal, Stop, or telemetry processing — Task 4.

## File structure

| Files | Responsibility |
| --- | --- |
| `bridge/__init__.py`, `bridge/__main__.py` | Package and foreground CLI entry point |
| `bridge/protocol.py` | Packet framing, decoded safety state, semantic-command encoding |
| `bridge/backends.py` | Backend protocol, Bleak implementation, explicit simulator |
| `bridge/controller.py` | Ownership, command queue, telemetry freshness, Stop and recovery |
| `bridge/server.py` | Static allowlist, bootstrap, WebSocket authorization and schema |
| `pyproject.toml`, `uv.lock`, `.gitignore` | Isolated dependencies and generated-file exclusions |
| `protocol.js` | Pure browser protocol helpers extracted from `treadmill.js` |
| `transports.js` | Direct BLE and bridge adapters with one browser-facing interface |
| `treadmill.js` | Existing UI/session integration; transport selection and state events |
| `dashboard.css`, `dashboard-ui.js`, `index.html` | Local styling, tabs, loading, toast and device picker |
| `tests/fixtures/protocol.json` | Synthetic shared packet cases, no real identifiers |
| `tests/__init__.py`, `tests/test_bridge_protocol.py`, `tests/protocol.test.cjs` | Importable Python test package and cross-language protocol agreement |
| `tests/test_bridge_controller.py`, `tests/test_bridge_server.py` | Safety and HTTP/WebSocket behavior |
| `tests/transports.test.cjs`, `tests/units.test.cjs` | Browser adapters and dashboard regressions |
| `tests/firefox-simulator-checklist.md`, `README.md` | Native Firefox acceptance procedure and operation/rollback |

## Task 1: Establish protocol parity and isolated runtime

**Files:** Create protocol modules, shared fixtures, Python project files and protocol tests from the table. Modify `.gitignore`, script ordering in `index.html`, `treadmill.js` protocol call sites and the VM harness in `tests/units.test.cjs`.

**Interfaces:**
- JavaScript `PitPatProtocol.parseTelemetry(bytes: Uint8Array) -> object` returns existing raw measurement fields, `running_state`, and `packetHex`; throws on invalid framing. `makePacket(type, speed=1000) -> Uint8Array` preserves existing command bytes.
- Python `parse_telemetry(packet: bytes) -> Telemetry` returns an immutable object with `speed_raw`, `state`, `unit_mode`, counters and original bytes. `encode_command(op: str, speed: int=1000) -> bytes` implements only start, pause, stop and set_speed. `HEARTBEAT: bytes` is the existing five-byte reply.
- Browser and bridge command validators reject booleans, strings and nonfinite/fractional/out-of-step speed values; browser MPH conversion still rounds before encoding.

Test contract: `test_stopped_requires_zero_speed` decodes a valid stopped-flag
fixture with speed 1000 and asserts `report.state == 3` and
`report.speed_raw == 1000`; consumers must not equate the state alone with Stop.
`test_command_speed_validation` asserts `encode_command("start", 1000)[12] == 4`
and `encode_command("stop", 1000)[12] == 0`, and asserts `ValueError` for every
invalid speed listed below.

- [ ] Write fixture-driven tests for synthetic 0x67 reports and 53-byte 0x66 idle reports; metric/imperial units; starting/running/paused/stopped bits; nonzero speed with stopped flags; checksum, declared-length, terminator and truncation failures. Preserve exact known command bytes.
- [ ] Add explicit assertions in both languages: minimum speed 1000 and maximum 6000 accepted; 999, 6001, 1050, `true`/`True`, `"1000"`, NaN and unknown operations rejected. Assert stop encodes command byte zero and correct XOR.
- [ ] Run `node --test --test-isolation=none tests/protocol.test.cjs` and `python3 -m unittest tests.test_bridge_protocol -v`; observe failures from missing helpers before implementing them.
- [ ] Implement the pure helpers and refactor existing browser parsing/encoding to call them. Preserve the rejected-telemetry warning and existing session measurements. Update the VM harness to load `protocol.js` before `treadmill.js`.
- [ ] Add uv project metadata for Python >=3.11, aiohttp >=3.11,<4 and Bleak >=3,<4; resolve and lock compatible versions, install only in `.venv`. Exclude `.venv`, Python caches and logs. No dependencies needed for pure protocol tests.
- [ ] Run both protocol suites and the existing Node suite. Expected: all pass and fixture results agree. Record baseline failures separately if any.
- [ ] Commit only Task 1 paths when author identity is configured; otherwise retain the validated changes without inventing identity or changing global Git configuration.

## Task 2: Implement the single-owner safety controller

**Files:** Create `bridge/backends.py`, `bridge/controller.py`, `tests/test_bridge_controller.py`.

**Interfaces:**
- Backend async methods: `discover(timeout: float) -> list[Device]`, `connect(device_id: str, on_packet, on_lost) -> None`, `write(packet: bytes) -> None`, `disconnect() -> None`. Device IDs must come from the current bounded discovery result. Real backend uses only the existing FBA0/FBA1/FBA2 UUIDs.
- `Controller(backend, clock=time.monotonic)` exposes async `dispatch(client_id: str, request: dict) -> dict`, `client_lost(client_id: str)`, `tick()`, `shutdown()`; synchronous `subscribe(callback) -> unsubscribe` publishes nonblocking immutable events.
- Request envelope: `{v:1,id:string,op:string,generation:integer,args:object}`. Connect uses the current discovery ID; motion uses the established connection generation. `renew` is the lease-only heartbeat operation. Responses echo ID/generation with `ok` and result or an error code. Events have `v`, `generation`, increasing `seq`, `event`, and `data`.
- State reports distinguish disconnected, connecting, awaiting_telemetry, ready, stopping and orphaned. Recovery claim is `connect` with `args.recover=true`, allowed only without an active owner; it reuses the retained link and permits Stop only until stopped/zero telemetry confirms recovery.

Test contracts: `test_lease_expiry_requests_stop_without_disconnect` advances the
fake clock from last renewal by 6.0 seconds, calls `tick()`, and asserts exactly
one Stop write and zero disconnect calls before confirmation.
`test_stop_requires_write_and_new_zero_report` asserts the Stop task remains
pending after a stale zero report and after a fresh nonzero report; only a fresh
stopped/zero report plus resolved write yields `confirmed == True`.
`test_late_connect_after_owner_loss` asserts zero motion writes and a Stop attempt
after the deferred connection resolves.

- [ ] Write async tests with a fake backend, manually controlled writes and fake monotonic clock. Assert a second owner is rejected; old-generation commands and duplicate motion request IDs write nothing; invalid speed writes nothing; a pending Stop cancels queued motion and blocks further motion.
- [ ] Add races: browser loss while `connect()` is pending triggers Stop on a late successful connection without enabling motion; replaced connection callbacks are ignored; slow subscribers cannot block a Stop or notification heartbeat. Bound subscriber queues and disconnect slow clients instead of accumulating packets.
- [ ] Test Stop joins, hung/failed writes, telemetry arriving before write begins, stopped flags with nonzero speed, confirmed write plus fresh stopped/zero report, and failure after five seconds. Test monotonic six-second lease loss and five-second telemetry staleness without real sleeping.
- [ ] Test browser loss retains an unconfirmed link as orphaned; recovery is explicit, cannot start, and unlocks only after fresh stopped/zero telemetry. Test true BLE loss clears queued commands and reports unknown motion. Test graceful shutdown requests bounded Stop without claiming confirmation when absent.
- [ ] Run `python3 -m unittest tests.test_bridge_controller -v`; observe red tests, then implement the controller and backend boundary. Stop can use the write serializer without waiting on a browser or telemetry consumer. Do not await a hung write indefinitely after its deadline.
- [ ] Implement Bleak discovery/connect/notify/write explicitly using the existing UUIDs; simulator supplies synthetic idle and motion packets and configurable write failures/loss. No real backend is instantiated during tests.
- [ ] Rerun protocol and controller suites. Expected: all pass, no real sleeps/scans/device writes. Commit scoped paths subject to the Git identity constraint.

## Task 3: Serve a restricted local dashboard and WebSocket API

**Files:** Create `bridge/server.py`, `bridge/__main__.py`, `tests/test_bridge_server.py`; update project CLI metadata and static asset allowlist as later assets arrive.

**Interfaces:**
- `create_app(controller: Controller, *, port: int=8765, simulator: bool=False) -> aiohttp.web.Application`.
- `GET /api/bootstrap` returns `{v:1,transport:"bridge",simulator,token,lease_ms:6000}` with no side effects and `Cache-Control: no-store`.
- `GET /api/ws` validates exact Host and Origin before upgrading. First JSON message `{v:1,op:"authorize",token}` must arrive within three seconds; no operation runs before authorization. Subsequent messages use Task 2's contract; `renew` is acknowledged without scanning/writing BLE.
- CLI `uv run python -m bridge [--simulate] [--port PORT]` binds only 127.0.0.1; port is validated 1–65535. No wildcard bind option. Simulator and real BLE modes are mutually exclusive startup choices.

Test contracts: `test_foreign_origin_never_dispatches` asserts a WebSocket
handshake with Origin `https://example.org` gets HTTP 403 and the controller's
dispatch count remains zero. `test_bad_token_never_dispatches` asserts the socket
closes after invalid authorization with zero controller commands.
`test_static_allowlist_excludes_private_files` asserts `/.git/config`,
`/.venv/pyvenv.cfg` and `/export.xml` return 404 with no file contents.

- [ ] Write real aiohttp HTTP/WebSocket boundary tests using the fake controller/backend and ephemeral loopback ports. Assert exact-host rejection, missing/null/foreign Origin rejection, invalid/missing token, authorization timeout, duplicate/unknown schema fields, malformed JSON and no BLE writes for rejected input.
- [ ] Assert 16 KiB message limit, 64-character request-ID limit, five-second discovery duration, maximum 32 returned devices and only IDs from that discovery accepted. Reject concurrent scans and discovery while connected. Authorization is not renewed by malformed traffic.
- [ ] Assert traversal/encoded traversal, `.git`, `.venv`, export files and unlisted paths are inaccessible; static allowlist contains only required dashboard files. No CORS headers; bootstrap is non-cacheable; reject cross-site fetch metadata; set framing and CSP headers.
- [ ] Assert bounded per-client outbound queue (64 events): overflow closes the client and triggers lease-loss handling without blocking controller work. WebSocket close always calls `client_lost`; shutdown calls `shutdown` once.
- [ ] Run `uv run python -m unittest tests.test_bridge_server -v` red, implement server/CLI, then rerun green. Use a random per-process token, constant-time comparison, no token/identifier logging, and bounded user-safe errors. Use CSP `default-src 'self'`, `connect-src 'self'`, `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'none'`; move existing inline styles to the local stylesheet as necessary.
- [ ] Verify simulator CLI startup on an unused test port and graceful termination with no attached hardware; this is a server process, not a desktop lifecycle. Leave the existing server on 8765 running. Commit scoped paths subject to identity availability.

## Task 4: Integrate browser transports without changing walk identities

**Files:** Create `transports.js`, `tests/transports.test.cjs`; modify `treadmill.js`, `tests/units.test.cjs`, `index.html`.

**Interfaces:**
- `PitPatTransports.select({fetch, bluetooth, WebSocket, location}) -> Promise<Transport>` chooses bridge on valid bootstrap; uses direct only on an actual absent-endpoint response from a static server. Bootstrap network errors or malformed bridge replies remain visible errors; never silently fall back.
- Transport async methods `discover()`, `connect(deviceId)`, `command(op,args={})`, `stop() -> {confirmed:boolean}`, `stopDisconnect() -> {confirmed:boolean}`; `onEvent(callback)` emits telemetry, state, safety and lost events. Direct `discover` invokes the existing chooser and returns its selection; bridge discovery returns the picker list.
- Bridge adapter owns authorization, request IDs, current generation and one-second lease renewal. It accepts only increasing sequences from its current socket/generation and never retries motion. Direct adapter retains current confirmed-stop semantics; move its state machinery intact before simplifying duplicated UI code.
- Dashboard receives the same raw telemetry schema as before, keeps current tracking functions and persists history only through existing helpers. Backend-confirmed stop results drive bridge safety text; browser notifications cannot independently claim a bridge stop succeeded.

Test contracts: `old socket cannot resolve current request` sends a matching ID
from a replaced socket and asserts the current request is still pending.
`bridge notifications never send browser heartbeats` emits two valid telemetry
events and asserts no raw-write or heartbeat command is submitted by the adapter.
`storage failure leaves Stop usable` makes localStorage throw, renews the lease,
then requests Stop and asserts both operations still reach the bridge.

- [ ] Write adapter tests for bridge/direct selection, unsupported browsers, unavailable bridge, second-client busy, rejected authorization and no fallback after bridge failure. Test duplicate, out-of-order and stale socket/generation events, outstanding request rejection on socket loss, and no replay on reconnect.
- [ ] Extend dashboard VM tests for bridge telemetry, counters, MPH and Cal parity, interrupted-session continuity, Stop during starting, timeout warnings, and successful Stop & Disconnect with no late-error overwrite.
- [ ] Add assertions that bridge telemetry produces no browser-generated heartbeat GATT writes; localStorage exceptions do not prevent lease renewal, incoming state processing or Stop. Export/import the same stable IDs between isolated Chromium/Firefox-like stores without duplication.
- [ ] Run focused Node suites red, implement adapters/integration, then run all Node tests green. Add `pause` routing from the existing Start/Pause button and metric-rounded speed commands without changing session-counter semantics.
- [ ] Ensure opening/reloading the page only initializes transport capabilities; scans require Connect and device selection. Browser unload must not claim Stop success; the backend lease handles loss independently.
- [ ] Commit scoped changes subject to identity availability.

## Task 5: Replace external UI dependencies and prove Firefox simulator flows

**Files:** Create `dashboard.css`, `dashboard-ui.js`, `tests/firefox-simulator-checklist.md`; modify `index.html`, toast/loading/tab integration in `treadmill.js`, asset allowlist and focused Node UI tests.

**Interfaces:**
- `PitPatUI.init()` binds local accessible tabs and a device picker. `chooseDevice(devices) -> Promise<string|null>` resolves only explicit selection/cancel. `toast(message)` uses the existing snackbar live region; loading state keeps Stop accessible whenever a connection exists.
- Preserve existing button/metric/history IDs and keyboard use. Transport and simulator labels remain visible; history transfer help explains browser-local storage.

Test contracts: `cancelled device picker never connects` asserts picker cancel
returns null and connect call count is zero. `Stop is usable during loading`
asserts Stop is enabled once BLE is connected even while telemetry is pending,
and pointer/keyboard events are not intercepted by the loading overlay.

- [ ] Write focused tests for cancel/empty scan, keyboard tab navigation, unsupported browser/adapter errors, visible simulator indicator, and loading/countdown not preventing Stop. Verify page asset references contain no MDL/font CDN requests.
- [ ] Run tests red, remove external scripts/fonts and replace required MDL behavior with local UI code/CSS, then rerun green. Move inline styles required by CSP without broad visual redesign.
- [ ] Start simulator on an unused port and exercise actual Firefox HTTP/WebSocket flows: select/connect, readings, start, pause, rounded speed, Stop during starting, confirmed disconnect, reload without motion, closed-tab lease expiry and busy second client. Use the current chat's hidden desktop only if authorized and available; read omarchy-control before GUI work. Do not create/stop a desktop without required approval.
- [ ] If hidden GUI is unavailable, retain a user-executable checklist and mark native Firefox acceptance pending; Node mocks are not Firefox proof. Record actual outcomes, not planned successes.
- [ ] Commit validated assets and evidence instructions, subject to identity availability.

## Task 6: Verify, document and hand off physical acceptance

**Files:** Modify `README.md`; add `docs/firefox-bridge-acceptance.md` with software results and separately recorded user hardware outcomes. Update task 4 in Notion only to match verified status.

- [ ] Run `node --test --test-isolation=none`, `node --check protocol.js`, `node --check transports.js`, `node --check treadmill.js`, `node --check dashboard-ui.js`, `uv run python -m unittest discover -s tests -p 'test_bridge_*.py' -v`, `uv lock --check`, and `git diff --check`. Expected: exit zero for each; rerun only failures or checks affected by further edits.
- [ ] Review the full change against the spec: one command owner, no auto-motion/fallback/replay, backend-owned heartbeats, fresh stop evidence, generation races, local authorization, data preservation and no public private-data fixtures. Keep hardware/sleep/radio-loss limits explicit.
- [ ] Document isolated setup, foreground real/simulator commands, controller recovery, browser history transfer, diagnostics, missing adapter/dependency errors and rollback to the existing Chromium static server. No automatic startup or desktop configuration changes.
- [ ] With the user present and physical stop ready, arrange switching from the static server to the bridge only while the belt is stopped/disconnected. Do not interrupt a live walk. In Firefox verify low-speed start, live measurements, speed change, Stop during starting and Stop & Disconnect; record user observations independently of telemetry.
- [ ] Separately arrange a browser-loss test while BLE remains available. Verify the physical belt stops and the bridge reports its actual confirmation result. Do not infer a device watchdog or test radio loss/sleep as part of this acceptance.
- [ ] If any required GUI/hardware test is pending, leave task 4 In progress and list the specific check. Only mark complete after both software checks and Firefox/user hardware acceptance pass.
- [ ] Preserve all existing work and exports. Commit only reviewed scoped paths once identity is available; do not push, merge or install a service. Summarize exact test evidence, remaining limitations and rollback.

## Plan self-review

- Protocol, safety, browser, authorization, UI, delivery and acceptance requirements each have an owning task above.
- `renew` is explicitly lease-only; discovery never happens during bootstrap. Recovery uses the same controller/API contract as normal connect with an explicit recovery flag.
- Both protocols share golden fixtures; the bridge owns notification replies in bridge mode, preventing two heartbeat writers.
- All five Review Focus races/input classes have tests assigned to their owning tasks.
- Git author identity is currently unavailable. The design document was staged but its commit failed; no identity was invented and no global configuration changed. This does not block writing/reviewing the plan or preserving existing source.
- Implementation is pending plan approval. No product code, dependencies, running server or device state changed while preparing this plan.
