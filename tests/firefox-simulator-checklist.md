# Firefox simulator acceptance

This procedure uses no real Bluetooth adapter. Run `uv run --frozen python -m
bridge --simulate --port 8767` and visit `http://127.0.0.1:8767/` in Firefox.

- [x] Confirm the prominent SIMULATOR label before connecting.
- [x] Connect, select the synthetic treadmill, and see idle metrics and an enabled Stop.
- [x] Start and verify that Stop remains clickable during countdown.
- [ ] Verify keyboard Stop activation during countdown (mouse activation observed).
- [x] Start again, wait for running, change MPH, pause, resume and observe counters.
- [x] Stop & Disconnect; confirm the success message persists and Connect returns.
- [x] Reconnect and reload; verify nothing starts automatically and tracking continuity remains explicit.
- [ ] Open a second tab: it must report busy and cannot control or receive the owner's telemetry.
- [ ] Close the owner while running. Within the lease deadline plus stop deadline the backend must request Stop; reconnect and confirm simulator stopped. HTTP/WebSocket tests independently inspect backend state for this case.
- [x] Navigate Controls/History with clicks and arrow keys.
- [ ] Inspect the network/error console for missing local assets or CSP violations; no CDN/font resources should be requested.

Reload while moving was observed to stop the simulator, and explicit tracking
continuation did not start motion. Closing a tab and waiting for lease expiry
is covered by the HTTP/controller checks; its distinct GUI exercise remains above.
- [ ] History export/import preserves IDs; an identical reimport does not duplicate records.

Record Firefox version and actual outcomes in `docs/firefox-bridge-acceptance.md`.
Leave tests unchecked until observed. A paused/unbound hidden desktop is not GUI
acceptance, and test cleanup must not stop any desktop without explicit approval.
