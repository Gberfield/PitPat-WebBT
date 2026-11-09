
## Local project LLM wiki

Exception (October 30, 2026): on macOS this project has no wiki. The repository is the complete record; start from `docs/README.md`. The rules below apply only where the Linux wiki exists.

- Read `wiki/index.md` and the relevant linked pages before material work in this project. The wiki is a derived synthesis; current governing instructions, specifications, source code and evidence retain authority.
- During authorized project work, maintain `wiki/architecture.md`, `wiki/decisions.md`, `wiki/open-questions.md`, `wiki/sources.md` and `wiki/log.md` when material findings change. Record reasons, source links, dated verification, contradictions and explicit unknowns; preserve historical decisions with supersession rather than silently replacing them. Do not produce a session transcript or copy raw/private payloads.
- Update `wiki/sources-json.md` hashes only for sources actually reviewed and incorporated. A changed hash is not proof of understanding or acceptance. Keep notes specific and useful; do not change knowledge merely to clear a health warning.
- QMD indexes the maintained wiki by default and source documentation separately. Use the matching `*-wiki` collection first, then the source collection and actual files. The hourly job refreshes registry coverage, search and source/link health; it does not synthesize or authorize actions.
- Preserve existing holds, user notes, source custody, tests and deployment/desktop/authentication gates. Coordinate with an existing source writer before cross-task edits. If writing is outside this task's permission or sole-writer scope, report the pending wiki delta instead of claiming it was maintained.

- `wiki/` is a local shortcut to this project's canonical Obsidian vault wiki. Human and Codex edits share the same files. Use the guarded wiki_storage.py writer with the reviewed page SHA256 before replacing shared content; preserve and reconcile concurrent edits. See /home/gabe/.local/share/qmd-codex/WIKI-STORAGE.md.

## Claude and Codex Roles

- The human brings the plan; Claude turns it into PLAN.md rows and briefs, delegates, verifies and owns PLAN.md
- New tasks start as proposed and are delegated only after the human approves them in chat
- Once a task is approved, Claude delegates it without waiting to be asked again, one task at a time in table order
- Codex executes one task brief at a time and never edits PLAN.md or docs/handoffs
- Every delegated task has a brief in docs/handoffs before it is sent
- Claude delegates by running ~/.claude/skills/codex-handoff/task.sh with a prompt file that points Codex at the brief file
- Codex runs on gpt-6.1-sol, passed as --model gpt-6.1-sol, unless the human names another model for a task, which goes in its Model column
- Claude fits a reasoning effort to every task when drafting it, records it in the Effort column and passes it as --effort on every handoff, never leaving it to the config default
- Effort fit: low for docs, renames, config tweaks and trivial scripts; medium for ordinary features and fixes; high for tricky logic, multi-file changes or hard bugs; xhigh for high-stakes or gnarly work where correctness beats speed and cost
- The human can change a task's effort when approving it; the plugin accepts low through xhigh, so max and ultra need Codex run directly
- Claude runs each Codex task as a background command, so it hears back when Codex finishes without the human polling
- /codex:status and /codex:result only run when the human types them, so Claude asks for them when needed
- Claude runs Codex reviews itself through the codex-review skill, because /codex:review and /codex:adversarial-review are user-only commands; the human can still type them
- Use the script's resume mode to fix up the same task and fresh for a new one
- The stop-time review gate stays off unless the human turns it on
- After each task Claude reads the full diff and runs the acceptance check itself, never trusting the report alone
- A failed check gets at most two resume rounds, then the task is marked blocked and the human is asked
- Once a task is done, merged or dropped by the human, Claude archives its Codex threads with task.sh archive <worktree> before removing the worktree, never between resume rounds
- Parallel tasks each run in their own git worktree under .worktrees and never share files
- Before merge Claude runs the codex-review skill's review without being asked, and its adversarial-review for auth, data, payments, migrations or deletes, returns Codex's output verbatim, then checks each finding against the code
- Codex never commits; Claude stages the work, shows the human the diff and commit message, and commits only after the human approves in chat
- Never let either agent push, force-push, merge to main or delete branches without human approval
- Keep briefs self-contained, because Codex does not see this Claude conversation
