# T9: Build the menu bar app with App Intents metadata, plus one read-only status intent

## Context

PitPat-WebBT controls a PitPat treadmill. On macOS a SwiftUI/AppKit menu bar app
(`integration/macos/PitPatMenuBar`, a Swift package with executable targets
`PitPatMenuBar` and `PitPatSafety`) is the native controller. Its `Service`
(`Sources/PitPatMenuBar/Service.swift`) holds the socket to the local bridge and
publishes a `snapshot`; `Model.view(snapshot, isOwner)` (`Model.swift`) turns it
into the labels the popover shows (`label`, `speed`, `distance`, `duration`,
`steps`, ...). `AppDelegate` in `App.swift` owns the single `Service`.

The owner wants Siri control, added in stages (design: `docs/siri-integration.md`).
Siri on macOS runs App Intents. This task is the first stage: prove the build can
register an intent, with one intent that only reads state.

`scripts/build-menubar.sh` builds with `swift build -c release`, then hand-assembles
`.build/PitPat.app` (Info.plist + executable) and signs it ad hoc. `swift build`
does not run Xcode's `appintentsmetadataprocessor`, so it emits no
`Contents/Resources/Metadata.appintents`, and macOS will not register intents
without it. `scripts/install-macos.py` copies only the files in
`BUNDLES[MENUBAR_APP]` (`Contents/Info.plist`, `Contents/MacOS/PitPatMenuBar`)
into `~/Applications/PitPat.app` and raises "Unexpected file in menu bar build" for
anything else in the build.

## What to do

1. **Build.** Change `scripts/build-menubar.sh` so the produced `.build/PitPat.app`
   contains `Contents/Resources/Metadata.appintents` for the intent below, still
   ad-hoc signed, still at the same output path, still also producing
   `.build/PitPatSafety`. First try `xcodebuild` on the existing package (the
   package scheme, `-destination 'platform=macOS'`, a derived-data path under
   `.build/`) and check whether it runs the metadata processor for an executable
   target. If it doesn't, find the smallest alternative (for example running
   `xcrun appintentsmetadataprocessor` explicitly with the inputs Xcode passes it,
   or a minimal checked-in Xcode project) and explain the choice. Don't add
   third-party tools (no XcodeGen, Tuist or packages). `swift build` and
   `swift test` for the package must keep working. Requiring the full Xcode for
   the app build is accepted; the script must fail with a clear message if only
   the command line tools are selected.
2. **Status intent.** Add `Sources/PitPatMenuBar/Intents.swift` with one
   `AppIntent`, `PitPatStatusIntent` (title "PitPat Status"), and an
   `AppShortcutsProvider` with phrases such as "PitPat status in
   \(.applicationName)" / "How's my walk in \(.applicationName)". `perform()` runs
   on the main actor, reads the running app's `Service` (add a minimal accessor;
   don't restructure `AppDelegate`), and returns a dialog built only from
   `Model.view` fields, for example `"<label>. <speed>, <distance>, <duration>."`
   When the service is not authorized (bridge not reachable), reply "PitPat isn't
   connected to its services." Set `openAppWhenRun` to false. The intent must not
   send any request, take control, connect, or start or stop services.
3. **Launch behaviour (record, don't change).** Don't change
   `ServiceStart`, `applicationDidFinishLaunching` or the quit path. Instead, find
   out from the documentation and the API whether the app can tell, before
   `ServiceStart.run`, that it was launched only to run an intent, and write what
   you found in your report. The owner has decided that an intent must never start
   the services; a later task implements that based on your findings.
4. **Installer.** Let `scripts/install-macos.py` accept and install the
   `Contents/Resources/Metadata.appintents` tree from the build (it is a directory
   of files), keep rejecting every other unexpected file, and keep the existing
   signing and manifest behaviour. A build without the metadata should still
   install (older builds). Update `tests/test_macos_install.py` and, if relevant,
   `tests/test_macos_bundle.py`: metadata files are copied, an unexpected file
   next to them is still refused.
5. **Tests.** Add Swift tests for the dialog text: authorized snapshots from
   `tests/fixtures/model-cases.json` (stopped, walking, stale, fault, simulator)
   and the not-authorized case. Factor the text into a pure function so it can be
   tested without running the intent.

## Safety boundary

Never connect to, arm or move a physical treadmill. Use simulator services and
fakes only. The intent is read-only: if reading state turns out to need a new
request or protocol op, stop and report instead of adding one. Don't change the
BLE protocol, safety timeouts, Stop handling, recovery rules or the on-demand
service policy (PitPat never starts at login; opening the app starts both
services, quitting stops them).

## Checks (all must pass)

```bash
node --test --test-isolation=none
uv sync --locked && uv run --frozen python -m unittest discover -s tests -p 'test_*.py'
(cd integration/macos/PitPatMenuBar && swift test)
scripts/build-menubar.sh && ls "integration/macos/PitPatMenuBar/.build/PitPat.app/Contents/Resources/Metadata.appintents"
```

`xcodebuild`, Swift builds and socket tests may fail inside the Codex sandbox
(cache writes, sockets). Report exactly which ones and the error, and Claude will
run them outside it. Don't work around the sandbox by changing global config.

Claude checks registration afterwards (the intent appears in the Shortcuts app and
Siri answers it on simulator services); you can't, so don't try to drive the GUI.

## Rules

- Don't commit, push or create branches. Leave the changes in the working tree.
- Don't edit `PLAN.md` or anything under `docs/handoffs/`.
- Don't install into `~/Applications` or start the real services.
- Match the surrounding code style (compact Swift; compact one-line style in
  `install-macos.py`).
- Report what you changed, why, the build approach you chose and what you rejected,
  the launch-detection findings, and the check output.
