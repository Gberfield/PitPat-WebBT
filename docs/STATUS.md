# Project status

Last updated: October 30, 2026 (EDT). Update this file whenever the state below
changes. Read it first when picking the project up again.

## Where things stand

Nothing is in progress and nothing is blocked. All work is on `main`, with no open
pull requests or issues. Macs and Linux share one codebase.

- **macOS:** installed on the owner's MacBook in `~/Applications`, running from the
  repository checkout on `main`. Physical acceptance passed on October 29, 2026; see
  [macOS acceptance](macos-acceptance.md).
- **Linux (`desk`):** not checked since the October 19, 2026 handoff. Per
  [closeout handoff](closeout-handoff.md), its live services run from a retained
  `codex/dedicated-safety` worktree there, and that handoff's holds still apply. The
  GitHub branch was deleted on October 30, 2026 after merging into `main`. That
  doesn't touch the worktree on `desk`, but the worktree is now behind `main`, and
  its upstream branch is gone.
- **Documentation:** this repository is the complete record, indexed from
  [docs/README.md](README.md). There is no wiki, by the owner's decision.

## Optional work

None of this is required. Each item waits on the owner.

1. **Mac sleep test.** Not run, because system sleep is disabled on the owner's Mac.
   Run it once on an empty belt if sleep is enabled or on another Mac. A Stop is not
   guaranteed, so record what happens. App Nap is unverified too.
2. **Crash-stop timing.** The crash test passed, but time to stop was not measured.
3. **Linux update.** Move `desk` from the retained worktree onto `main`. This is a
   deliberate change to the installed source: read the closeout handoff first, and
   do not restart anything during a walk.
4. **`pitpat stop` with nothing connected.** It latches a fault, so the next Connect
   needs recovery. This was left unchanged on purpose: changing it means changing
   the recovery rules, which needs the owner's decision.

## Safety rules for any new work

Automated work uses `--simulate` only. Never connect to, start or stop the real
treadmill without the owner's go-ahead in chat. Do not change the BLE protocol,
safety timeouts, Stop confirmation, recovery rules or the on-demand service policy
without the owner's decision.
