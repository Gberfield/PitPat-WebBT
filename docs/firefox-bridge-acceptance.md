# Firefox bridge acceptance

Implementation date: October 15, 2026 (Eastern Time).

## Software evidence

The software suites exercise real protocol parsers, controller state transitions,
HTTP routes and WebSocket connections with synthetic BLE backends. They do not
scan or control the real treadmill.

- Original baseline: 61 Node tests passed before bridge edits.
- Current Node suite: 78 passing tests, including direct-path regressions, protocol
  parity, bridge event ordering, local device selection and storage-failure Stop.
- Python suite: 31 passing tests. Protocol, controller and loopback API tests cover initial-report
  buffering, stale generation rejection, browser lease expiry, orphan recovery,
  failed/hung Stop writes, fresh confirmation, cancellation, authorization,
  bounded discovery/messages, private-file exclusion and slow-consumer Stop.
- Complete HTTP/WebSocket simulator flow checks selection, connect, start, second
  client rejection and confirmed Stop & Disconnect.
- Browser assets are local; an HTTP test fetches every referenced script/style
  under the restrictive CSP and rejects inline/external dependencies.
- Runtime dependencies are locked in `uv.lock` and installed only in `.venv`.

Full task history and local command receipts are retained under the ignored
`.superpowers/sdd/2026-10-15-firefox-bridge/` workspace. BERF preflight returned
`unknown_state` and did not execute checks; ordinary explicit verification was
used. Review was performed by the implementation author in a separate pass,
without additional agents, as required by the approved scope. This is weaker than
independent review.

## Acceptance status

- Core native Firefox simulator check: passed in this chat's explicitly approved
  hidden desktop. Verified device selection, telemetry, MPH adjustment, pause/resume,
  mouse Stop during countdown, confirmed Stop & Disconnect, reload-triggered
  simulator stopping, interrupted-record continuation without motion, history
  rendering, and keyboard tab navigation. Screenshot: `/tmp/pitpat-firefox-simulator.png`.
- Additional GUI exercises (second-tab rejection, downloaded JSON reimport and
  browser console inspection) remain unchecked in the detailed checklist. Their
  underlying API/history behavior is covered by automated tests; do not describe
  them as observed GUI outcomes.
- Firefox testing exposed and corrected native fetch receiver binding, stale
  stopped/starting indications, and anchor scrolling/focus loss in tabs. Each
  correction has an observed failing regression followed by a passing suite.
- Hidden desktop `n-bb6f029bb89b5591476182ab`, generation 1, is retained with Firefox
  running and input paused. Host-lock policy remains `pause`; no other desktops
  were interrupted. No real Bluetooth scans or motion commands were issued.
- User-reported physical BA09-B Firefox checks: all seven prescribed checks passed.
  These covered connection without motion and sensible measurements, minimum-speed
  start with updating counters, speed increase/decrease, pause/resume, Stop with
  zero-speed confirmation, Stop during startup, and Stop & Disconnect stopping
  the belt before returning to Connect. Evidence is the user's “all pass” reply;
  the agent did not operate or independently observe the real treadmill.
- Physical browser-tab-loss Stop while BLE stays connected: passed by user report.
  The user confirmed closing the Firefox control tab stopped the treadmill and
  reconnecting left it stopped. This verifies tab closure through the running
  bridge; it does not establish a device-side watchdog or a measured lease-expiry
  deadline. No stop latency was reported.
- Automatic physical stopping after real BLE loss, sleep, crash or power loss:
  unverified and not guaranteed by this software.

Epic task 4 (Firefox bridge) is accepted: the core native Firefox simulator
checks, seven physical control checks and physical tab-closure/reconnect check
passed. Additional GUI exercises remain explicitly unchecked above. Real radio
loss, sleep, crash and power-loss behavior remains outside the verified results;
the separate safety follow-up is not complete on the basis of tab closure.

## Preserved state and rollback

Existing source/history/export work was retained on `feature/firefox-bridge`.
Git commits are deferred because this checkout has no configured author identity;
no identity was invented. Nothing was pushed or installed as an automatic service.
The existing port 8765 static server was not stopped or replaced by this work;
a final read-only HTTP check found it unavailable. The real bridge is running
on port 8766 and the explicit simulator on 8767, both verified HTTP 200.

Server recovery: the earlier command-session processes later exited; the real
bridge was restored as the manually started transient user unit
`pitpat-bridge.service` on port 8766. Fresh verification showed active/running and
dashboard HTTP 200. The simulator was not restarted. The transient unit has no
login/boot enablement and no automatic restart; startup does not scan or connect
Bluetooth. The previous process returned exit zero with no error output, so the
reason it ended is not established.

With the belt stopped/disconnected, use `systemctl --user stop pitpat-bridge` to
stop this transient instance before launching another bridge on the same port.

With the belt stopped and disconnected, terminate the bridge foreground process
and use `python3 -m http.server 8765 --bind 127.0.0.1` in Chromium. Keep browser
history and exported JSON unchanged. New Firefox/Chromium histories can be merged
using the existing stable-ID import checks.

## Dedicated safety process follow-up

A separate implementation is staged, with synthetic verification documented in
[dedicated safety acceptance](dedicated-safety-acceptance.md). The application and
sole BLE-owning safety process have distinct failure tests. The older acceptance
and failed physical observations above are retained as historical evidence; they
do not establish physical acceptance of the new process split. No live change or
new physical test has been performed for that split.
