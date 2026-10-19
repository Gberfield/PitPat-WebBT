# Closeout handoff — October 19, 2026 (EDT)

The user is using the app and deferred the remaining work. No additional
physical tests, application/safety restarts, shell/desktop operations or firmware
investigation are armed by this handoff. Obtain fresh readiness/action-specific
arming before resuming physical tests. Do not restart the app during a walk.

## Maintained sources and preserved state

- Live services use the retained `codex/dedicated-safety` worktree at
  `/home/gabe/Projects/PitPat-WebBT/.superpowers/worktrees/dedicated-safety`.
  Keep this path in place; it is the installed source, not disposable scratch.
- `/home/gabe/Projects/PitPat-WebBT` on `feature/firefox-bridge` preserves the
  pre-safety implementation used by the reviewed installer rollback. Do not
  overwrite it to make the directories match. Both branches are preserved in Git.
- Existing user systemd services remain manually/on-demand started, `Restart=no`,
  with no login enablement. The independent safety process is the sole BLE owner.
- Private preimages, exact hashes, physical-test receipts, consistent SQLite
  backups and reversible installation manifests remain in ignored task state.
  Browser history, canonical walks, full safety evidence and local wiki stay local.
  Source commits contain no actual Health exports or walk databases.

## Verified outcome and its limits

American units, deterministic export preparation, Firefox/local bridge and
Omarchy tray controls are implemented. The dedicated safety process stopped
an empty BA09-B during supervised application-only SIGKILL and SIGSTOP tests.
The user observed automatic stopping; independent telemetry confirmed Stop.
After resumption, recovery controls appeared without Find treadmill and the
belt stayed stopped. A duplicated-evidence frame overflow was repaired without
removing provenance from saved walks. After that repair the user confirmed
stable tray UI, Stopped/Start enabled and no motion through explicit recovery.
The payload repair was checked on preserved recovery state, without another
moving-belt freeze. Exact physical deceleration times were not measured.

Software verification: 119 Python tests passed; 90 JavaScript tests passed
(the unchanged JS/CJS hashes were checked when reusing that run); actual
Quickshell offscreen recovery/ownership, compilation and whitespace checks passed.
Synthetic tests use a persistent plant outside both child processes. They are
not proof of physical hardware behavior in every failure mode. See
[acceptance evidence](dedicated-safety-acceptance.md).

## Deferred work

- Investigate graceful application shutdown: two prior restarts exceeded the
  35-second stop timeout; the most recent application restart completed normally.
  Do not attribute the cause or declare it fixed without reproduction/evidence.
- Safety-process crash/freeze, actual Bluetooth/BlueZ loss, computer sleep/power
  loss and every other unperformed acceptance case remain separate limitations.
  Earlier single-process loss/crash/freeze tests required a physical stop.
- No manufacturer-supported BA09-B communication watchdog was verified. The
  support inquiry remains unsent; no speculative protocol or firmware changes.
- Follow the existing acceptance checklist for remaining ownership/record/export
  coverage, keeping synthetic safety records out of counted exercise imports.
- Apple Health/Notion reconciliation has its own provenance and review holds;
  this source closeout does not resume or expand any data import.

## Resuming

Read the current project instructions, canonical wiki, governing safety spec,
[acceptance evidence](dedicated-safety-acceptance.md) and retained private ledger.
Check actual installed source/service identities and record state. User-reported
Stopped/Start enabled was the last accepted physical state, not a promise of
current state. Do not infer new motion, test or desktop authorization from it.
