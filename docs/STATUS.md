# Project status

Last updated: November 4, 2026 (EST). Update this file whenever the state below
changes. Read it first when picking the project up again.

## Where things stand

Nothing is in progress and nothing is blocked. Macs and Linux share one codebase.
On November 4, 2026 the menu bar app began starting both services when it opens
and stopping them when it quits, so `pitpat controls` is no longer needed. It is
merged and installed on the owner's MacBook. Opening **PitPat Safety** by hand now
opens the menu bar app instead of running a second safety process. The owner
checked all of this on the installed app the same day, including a quit with the
treadmill connected: the belt stopped.

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

## Owner decisions

Settled; don't reopen them without the owner. Newest first.

- **November 4, 2026: PitPat never starts at login.** The owner opens PitPat when
  they want it. Opening the menu bar app starts both services, and quitting it
  stops them. Don't add `PitPat.app` to Login Items or set `RunAtLoad`. This is
  the "on-demand service policy" in the safety rules below.
- **October 30, 2026: no wiki.** This repository is the complete record. Don't
  enroll it in a wiki or keep project knowledge in an agent's memory. Record it
  here or in the docs linked from [docs/README.md](README.md).

## Safety rules for any new work

Automated work uses `--simulate` only. Never connect to, start or stop the real
treadmill without the owner's go-ahead in chat. Do not change the BLE protocol,
safety timeouts, Stop confirmation, recovery rules or the on-demand service policy
without the owner's decision.
