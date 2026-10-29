# 04 — Bleak/CoreBluetooth backend and Bluetooth permission

**Depends on:** 01. **Size:** medium. **Touches real hardware:** only in the
final, owner-run step. Everything an implementer does uses `--simulate` or no
treadmill at all.

## Why

`bridge/backends.py:BleakBackend` uses Bleak, which supports macOS through
CoreBluetooth. The code is mostly portable, but macOS differs in ways that matter:

1. **Device IDs.** On macOS `BLEDevice.address` is a CoreBluetooth UUID
   (e.g. `9A1C…-…`), not a MAC address, and it is stable only per Mac. The code
   treats the ID as an opaque string ≤128 chars (`messages.validate_request`),
   which is fine. Nothing may assume a MAC format. Confirm no UI or test parses it.
2. **Bluetooth permission (TCC).** macOS requires the *responsible app* to have
   Bluetooth permission. Run from Terminal/iTerm/Ghostty → that terminal app gets
   the prompt once. Run from launchd (plan 05) → there is no app bundle, the
   prompt cannot be shown, and CoreBluetooth reports `unauthorized` (Bleak raises
   `BleakBluetoothNotAvailableError` or discovery returns nothing).
3. **Adapter state.** If Bluetooth is off, Bleak raises on scan. The bridge must
   report "Bluetooth is off or not permitted" instead of a generic failure.
4. **Already-connected devices** (e.g. the phone app holding the treadmill) do
   not advertise. Same as Linux; keep the existing "No treadmill found" text.

## Steps

1. Read `bridge/backends.py`, `bridge/safety_core.py` (how `discover`/`connect`
   errors become user messages) and the "No treadmill found" path in
   `bridge/server.py` / `treadmill.js`.

2. In `BleakBackend.discover`, catch Bleak's adapter/permission errors and raise
   `ValueError` with a fixed, user-facing message. Use the exception classes from
   `bleak.exc` that exist in the locked Bleak version (check `uv.lock`; Bleak 3.x
   has `BleakBluetoothNotAvailableError` with a `reason` attribute). Messages:
   - powered off → `'Bluetooth is off. Turn it on in Control Center.'`
   - unauthorized → `'Bluetooth permission denied. Allow it in System Settings → Privacy & Security → Bluetooth for the app running PitPat.'`
   - other → keep the current behavior.
   `ValueError` messages already reach the UI verbatim
   (`str(exc) if isinstance(exc, ValueError)` in `native.py`); verify the safety
   process path does the same, or route it there.

3. Do **not** add `cb=dict(use_bdaddr=True)` or other macOS-only Bleak options.
   The UUID IDs are fine.

4. Add `bridge/backends.py` unit tests with a fake `bleak` module injected into
   `sys.modules` (the module imports Bleak lazily inside methods, which makes
   this easy). Cover: powered-off → message, unauthorized → message, a UUID-style
   `address` round-trips through `discover` → `connect`.

5. Bundle for permission (needed by plan 05's launchd agent). Produce the
   smallest possible app bundle that launches the safety process, so macOS can
   attribute Bluetooth use and show the prompt:

   ```
   integration/macos/PitPat Safety.app/Contents/Info.plist
   integration/macos/PitPat Safety.app/Contents/MacOS/pitpat-safety   (shell script)
   ```

   `Info.plist` keys: `CFBundleIdentifier=com.gberfield.pitpat.safety`,
   `CFBundleName`, `CFBundleExecutable=pitpat-safety`, `CFBundlePackageType=APPL`,
   `LSUIElement=true` (no Dock icon), `LSMinimumSystemVersion=13.0`,
   `NSBluetoothAlwaysUsageDescription="PitPat connects to your treadmill to show
   telemetry and send Stop."`.
   The executable is a template like `integration/bin/pitpat`
   (`@REPO_SHELL@`/`@PYTHON_SHELL@` placeholders, `exec ... -m bridge.safety_main "$@"`).
   The installer (plan 07) fills placeholders and ad-hoc signs it
   (`codesign --force --sign - <app>`).

   **Open question for the owner, record in the PR:** whether TCC attributes
   Bluetooth to a script-executable bundle reliably on the current macOS. If not,
   the fallback is a ~30-line Swift launcher (`posix_spawn` the Python process as
   a child so the bundle stays the responsible process). Implement the script
   version first; do not build the Swift launcher unless the owner's test shows
   it is needed.

   **Answered October 29, 2026:** it does not. The owner's first Connect put only
   `python3.14` under Privacy & Security → Bluetooth. The Swift launcher was built
   in #20 (`Sources/PitPatSafety`); the script moved to `Contents/Resources`.

## Owner-run hardware check (implementer: do not perform)

Write these steps into the PR description; the owner runs them:

1. Treadmill powered, phone app disconnected, belt stopped, physical stop reachable.
2. Terminal 1: `uv run --frozen python -m bridge.safety_main`; Terminal 2:
   `uv run --frozen python -m bridge --port 8766`; open `http://127.0.0.1:8766/`.
3. Allow the Bluetooth prompt. Click Connect, select the treadmill. Expect
   telemetry and "Stopped". **Do not press Start** for this check.
4. Stop & Disconnect. Expect confirmed stop and clean disconnect.
5. Repeat via the `PitPat Safety.app` bundle once plan 05/07 exist.

## Acceptance

- Unit tests for the new error mapping pass on both OSes.
- Simulator path (`--simulate`) works on macOS end to end in a browser.
- PR lists the owner-run steps; hardware result filled in by the owner, not
  the implementer.

## Don't

- Don't change write-with/without-response logic, MTU, timing or packets.
- Don't scan at startup. The safety process must not touch Bluetooth until
  Connect (current behavior; preserve it).
