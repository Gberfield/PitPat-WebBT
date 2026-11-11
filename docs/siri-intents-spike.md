# T9 App Intents spike

Source implementation and checks, November 11, 2026. This is an uninstalled
spike; Shortcuts registration and Siri execution still need Claude/owner checks
with simulator services. No intent or app executable was launched in these checks.

## Build choice

Tried the existing package first, from `integration/macos/PitPatMenuBar`:

```sh
xcodebuild -scheme PitPatMenuBar -destination 'platform=macOS' -derivedDataPath .build/xcode build
```

Xcode 27.2 (27B52) returned exit 66:
`does not contain an Xcode project, workspace or package.` This attempt did not
reach compilation or metadata extraction; it does not establish what other
Xcode versions would do with a package executable.

Chose a minimal checked-in `PitPat.xcodeproj` with one app target. Its synchronized
source group compiles the same `Sources/PitPatMenuBar` files as SwiftPM; no source
copies or third-party generators. The existing Swift package remains unchanged.
Xcode supplies the compiler constant-value extraction, source/dependency lists,
SDK, deployment target, binary and bundle identifier to its
`ExtractAppIntentsMetadata` step. That step actually ran and wrote
`extract.actionsdata` and `version.json`. Inspection found `PitPatStatusIntent`,
title `PitPat Status`, both phrases, and `openAppWhenRun: false`.

Rejected a hand-written metadata processor invocation: its help and the actual
Xcode invocation have different inputs (including compiler-produced constant
values); reproducing that pipeline would couple the script to toolchain details.
The small project uses Xcode's supported build integration instead. An SPM-only
build cannot provide the required metadata here.

The build script requires full Xcode, uses derived data under `.build/xcode`,
checks for nonempty metadata, copies the app to `.build/PitPat.app`, and signs it
ad hoc. `GENERATE_PKGINFO_FILE = NO` keeps the app within the installer's existing
fixed files plus the metadata subtree. Safety still builds with SwiftPM and is
copied to `.build/PitPatSafety`. Neither build runs an executable or installs it.
The script stops on errors; a successful app stage alone is not a successful
complete build.

## Read-only behavior and installer

`PitPatStatusIntent.perform()` runs on the main actor and reads the existing
AppDelegate Service through a minimal accessor. It only reads `authorized` and
`model`. The pure `statusDialog` function uses the model's label, speed, distance
and duration, or the exact services-disconnected reply. It does not invoke any
Service operation. Fixture tests cover every model case and explicitly require
stopped, walking, stale, fault and simulator cases; a separate test checks that
unauthorized status discards even a walking snapshot.

The installer allows files beneath exactly
`Contents/Resources/Metadata.appintents`, copies their bytes at mode 0644, and
includes them in existing signing/manifest/rollback handling. Metadata is opaque,
not subject to template substitution. Builds without metadata remain accepted.
Tests cover nested files, signing/manifest hashes, upgrade and downgrade rollback,
sibling rejection, symlink rejection, and traversal rejection.

## Launch detection: finding and remaining uncertainty

Apple's [runtime documentation](https://developer.apple.com/documentation/appintents/configuring-the-runtime-behavior-of-your-app-intents)
allows intents in an app bundle to execute in the background. Background execution
is not a guarantee that the app process never launches. `openAppWhenRun = false`
is not a service-start guard.

At the existing `applicationDidFinishLaunching` callback, before `ServiceStart.run`,
AppKit provides [launchIsDefaultUserInfoKey](https://developer.apple.com/documentation/appkit/nsapplication/launchisdefaultuserinfokey).
It distinguishes default launches from a broad class of other launches, including
file opens, Services and restored state. Apple does not document this flag as a
unique App Intents discriminator, or promise its value for every Siri/Shortcuts
launch. The installed SDK's `NSApplication.h` describes the same broad contract.
An accessory app's inactive state also cannot distinguish manual opening from an
intent.

Newer App Intents exposes an intent's `systemContext` during execution, described
in the runtime documentation above. That is not a documented process-wide,
pre-launch-callback signal. Setting a flag in `perform()` cannot be assumed to
happen before `applicationDidFinishLaunching`. No documented reliable signal was
found that proves an intent-only cold launch before the current service start.
Undocumented arguments/environment keys, timing delays and current Apple event
inspection should not be treated as a hard safety guarantee.

No launch behavior was changed: `ServiceStart`, `applicationDidFinishLaunching`
and the quit path are untouched. Consequently the existing lifecycle may start
services on an intent cold launch. Do not accept this spike as satisfying the
owner's no-service-start rule. Runtime launch notification/event ordering and
values remain unobserved; Claude/owner must check them with simulator services.
For a guaranteed rule, a later task should consider starting services only from
an explicit user-open action, or isolating cold intents in an extension, rather
than relying on an undocumented intent-launch marker. Those are design decisions,
not changes made by this spike.

## Check results

- `node --test --test-isolation=none`: 93 tests, 93 pass, 0 fail.
- `uv sync --locked && uv run --frozen python -m unittest discover -s tests -p 'test_*.py'`:
  exit 2 at sync; `Could not acquire lock`, `Could not create temporary file`,
  `Operation not permitted (os error 1)` under `/Users/gabe/.cache/uv/`.
  The unittest command after `&&` did not execute.
- Supplemental system-Python full suite: 191 tests, 2 failures, 25 errors, 8 skips.
  Of the errors, 23 were sandbox socket bind denials (`PermissionError: [Errno 1]
  Operation not permitted`) in bridge-native, safety-client, safety-facade,
  safety-IPC and safety-native-frame tests. Two import errors and both assertion
  failures came from absent `aiohttp` in system Python. These dependency failures
  are not test regressions demonstrated against the locked environment.
- Final targeted `python3 -m unittest discover -s tests -p 'test_macos_*.py'`:
  20 tests, OK, 7 skipped. The installer tests sign only disposable fake-home apps.
- `(cd integration/macos/PitPatMenuBar && swift test)`: exit 1 before compilation;
  cannot write `/Users/gabe/.cache/clang/ModuleCache/Swift-18Y2CYADWFGX0.swiftmodule`
  (`Operation not permitted`), then `unable to load standard library for target
  'arm64-apple-macosx14.0'`. New Swift tests remain unexecuted.
- `scripts/build-menubar.sh && ls .../Metadata.appintents`: Xcode app build reports
  `BUILD SUCCEEDED`, metadata extraction and app signing complete, then the
  Safety SwiftPM build fails with the same module-cache denial. Overall exit 1;
  the chained `ls` is not reached. A separate `ls` confirms `extract.actionsdata`
  and `version.json` in `.build/PitPat.app/Contents/Resources/Metadata.appintents`.
  Xcode also logged unrelated CoreSimulator connection/version warnings; these
  did not prevent the macOS app build. Complete Safety output remains unverified.
- Repeating the full build: Xcode again reports `BUILD SUCCEEDED`, then cleanup
  fails with `rm: .build/PitPat.app/Contents/...: Operation not permitted`,
  including `MacOS`, `_CodeSignature`, and metadata temporary directories named
  `(A Document Being Saved By appintentsmetadataprocessor ...)`. Overall exit 1.
  Cleanup partially removed the assembled copy; `.build/PitPat.app` is currently
  incomplete. The complete Xcode product remains under
  `.build/xcode/Build/Products/Release/PitPat.app`. No sandbox settings were changed.
- `codesign --verify --deep --strict .../.build/PitPat.app`: initially exit 0,
  no output. After the repeat cleanup failure it reports `bundle format
  unrecognized, invalid, or unsuitable`; this is not a currently verified artifact.
- Supplemental generated-metadata assertions and installer plan against the
  complete Xcode product: PASS. Checks exactly one intent, `openAppWhenRun: false`,
  two phrase templates, and two metadata file operations. Planning writes nothing
  to the disposable home. The first attempt against the partially removed copy
  failed with `FileNotFoundError` for `extract.actionsdata`; it was rerun against
  the intact Xcode product.
- `sh -n scripts/build-menubar.sh`, `plutil -lint .../project.pbxproj`,
  `git diff --check`: pass (`plutil`: `OK`; others no output).

The normal locked Python suite, Swift package tests/build and complete build
script need rerunning outside the sandbox. No global configuration was changed.
No hardware, real services, GUI registration, installation, commit, branch creation
or push was performed.
