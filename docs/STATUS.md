# Project status

Last updated: November 11, 2026 (EST). Update this file whenever the state below
changes. Read it first when picking the project up again.

## Where things stand

Nothing is in progress and nothing is blocked. On November 11, 2026 a Siri
integration plan was proposed ([plan](siri-integration.md), PLAN.md T9–T13) and
the owner settled its decisions D1–D4. Nothing is built; T9 was delegated to Codex the same day. Macs and Linux share one codebase.
On November 4, 2026 the menu bar app began starting both services when it opens
and stopping them when it quits, so `pitpat controls` is no longer needed. It is
merged and installed on the owner's MacBook. Opening **PitPat Safety** by hand now
opens the menu bar app instead of running a second safety process. The owner
checked all of this on the installed app the same day, including a quit with the
treadmill connected: the belt stopped.

On November 6, 2026 the tray could not get control after Connect: the November 5
walk had been left open when the bridge last stopped, so it was held as an
interrupted record, the bridge withheld recording readiness, and the tray only
offered to claim and resolve the record after a safety fault. The tray (Mac and
Omarchy) now offers **Claim control to resolve record** for an interrupted record
without a fault, and **Take control while stopped** works on a settled, ownerless
connection. It was installed on the owner's MacBook the same day and checked
there: the owner claimed, resolved the record, took control and walked; see
[macOS acceptance](macos-acceptance.md). Why the
November 5 walk was left open is not known; the bridge log only shows restarts.

On November 9, 2026 a review of the code's implicit state machines was recorded as
GitHub issues #33–#48, tracked in #49, and four fixes were merged through the Codex
handoff workflow ([PLAN.md](../PLAN.md), briefs in [docs/handoffs/](handoffs/)).
Each fix had a Codex review, and the three safety fixes also had adversarial reviews.
All were tested with the simulator and fakes only. The same day, after a restart
onto `main`, the owner walked on the treadmill with them installed: a normal
Connect, walk and Stop worked; see [macOS acceptance](macos-acceptance.md). The
review gate's blocking paths (an interrupted record that needs review, a telemetry
gap mid-walk) have not been exercised on hardware.

- **#41 (PR #51):** the application blocks motion the moment an interrupt is
  queued, not only once the interrupted record has been written.
- **#44 (PR #52):** the browser records a walk as 'stopping', not 'starting',
  while the belt slows after Stop.
- **#34 (PR #53):** the stop kernel and `SafetyCore` share one rule for the
  motion-blocked flag. Behaviour is unchanged.
- **#50 (PR #54):** a new non-fault `recording_review` safety operation. Motion
  already waiting for the safety writer is cancelled when an interrupted record
  needs review, and new motion is refused until it is resolved. It never trips a
  fault, stops the belt or clears the grant. Safety starts with review on and
  resets it whenever the application attaches or detaches. The operation is
  described in the
  [dedicated-safety plan](superpowers/plans/2026-10-15-dedicated-safety-process.md).

- **macOS:** installed on the owner's MacBook in `~/Applications`, running from the
  repository checkout on `main`. Physical acceptance passed on October 29, 2026; see
  [macOS acceptance](macos-acceptance.md). The services were restarted onto the
  November 9 fixes that day. After any future update, restart both services
  together, never one alone: since #50, an application and safety process from
  before and after it don't understand each other's review messages, and safety
  would trip a fault.
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
5. **Open state-machine issues.** The other issues listed in #49 are recorded
   refactors and documentation, not known bugs. Two were done on November 9,
   2026: #38 (`HealthMonitor.answered` records an accepted answer since attach,
   and `is_healthy()` also checks expiry; behaviour is unchanged) and #36 (the
   safety states and fault-recovery path are written down in
   [safety states](safety-states.md); its two narrow review concerns are filed
   as #61 and #62).
   #35 asks whether a stopped report that arrives before the treadmill has
   processed Stop can count as confirmation; answering it needs a treadmill test.

6. **Stop incident, November 11, 2026, 4:55 PM.** During a 1.0 mph walk the owner
   ran "Stop PitPat" from Spotlight with the Siri T11 build installed (branch codex/t11-stop-intent). The walk record
   ended at 4:55:07 PM on a report of state 3 with zero speed, which is what
   confirms a Stop, but the owner says the belt kept moving until he pressed Stop
   in the menu bar. Later reports showed state 3 with speed 1.0 and frozen
   counters, which the labels showed as "Stopped". Safety restarted soon after,
   so whether the intent's Stop caused the confirmation can't be traced. This is
   the question in #35 and also affects the hotkey and menu bar Stop. Proposed:
   T14 (label) and T15 (Stop log); a supervised treadmill test needs the owner.
   Don't rely on voice or Spotlight Stop until it is understood.

## Owner decisions

Settled; don't reopen them without the owner. Newest first.

- **November 11, 2026: Siri scope.** The owner accepted D1–D4 in
  [Siri integration](siri-integration.md): voice gets Status and Stop first,
  then Pause, and Start only with Siri's spoken confirmation; no speed changes.
  An intent never starts the services. Siri's Stop sends exactly what the Stop
  hotkey sends. Building the menu bar app may require the full Xcode.

- **November 9, 2026: record review is its own safety gate.** An interrupted walk
  record that needs review blocks motion in the safety process through the non-fault
  `recording_review` operation (#50), separate from recording readiness, whose
  false value still trips a fault. The owner approved it as a separate task rather
  than widening the #41 fix.
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
