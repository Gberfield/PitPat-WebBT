
## Local project LLM wiki

Exception (October 30, 2026): on macOS this project has no wiki. The repository is the complete record; start from `docs/README.md`. The rules below apply only where the Linux wiki exists.

- Read `wiki/index.md` and the relevant linked pages before material work in this project. The wiki is a derived synthesis; current governing instructions, specifications, source code and evidence retain authority.
- During authorized project work, maintain `wiki/architecture.md`, `wiki/decisions.md`, `wiki/open-questions.md`, `wiki/sources.md` and `wiki/log.md` when material findings change. Record reasons, source links, dated verification, contradictions and explicit unknowns; preserve historical decisions with supersession rather than silently replacing them. Do not produce a session transcript or copy raw/private payloads.
- Update `wiki/sources-json.md` hashes only for sources actually reviewed and incorporated. A changed hash is not proof of understanding or acceptance. Keep notes specific and useful; do not change knowledge merely to clear a health warning.
- QMD indexes the maintained wiki by default and source documentation separately. Use the matching `*-wiki` collection first, then the source collection and actual files. The hourly job refreshes registry coverage, search and source/link health; it does not synthesize or authorize actions.
- Preserve existing holds, user notes, source custody, tests and deployment/desktop/authentication gates. Coordinate with an existing source writer before cross-task edits. If writing is outside this task's permission or sole-writer scope, report the pending wiki delta instead of claiming it was maintained.

- `wiki/` is a local shortcut to this project's canonical Obsidian vault wiki. Human and Codex edits share the same files. Use the guarded wiki_storage.py writer with the reviewed page SHA256 before replacing shared content; preserve and reconcile concurrent edits. See /home/gabe/.local/share/qmd-codex/WIKI-STORAGE.md.
