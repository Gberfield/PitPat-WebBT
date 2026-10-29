@AGENTS.md

## Claude Code notes (macOS checkout)

- This checkout lives at `/Users/gabe/Projects/PitPat-WebBT` on macOS. `AGENTS.md`
  was written for the Linux/Omarchy host; its `/home/gabe/...` wiki paths do not
  exist here. This project is not yet enrolled in
  `~/Library/Application Support/CodexKnowledge/mapping.json` (enrollment is done
  in the Codex app), so work from the repository sources.
- macOS support is merged into `main` (via `mac-compat` → `codex/dedicated-safety`
  → `main`, October 2026). Branch new work from `main`. Plans are in `docs/mac/`;
  results are in `docs/macos-acceptance.md`.
- Safety boundary: never arm, run or simulate physical treadmill tests without
  the user's explicit go-ahead in chat. Use `--simulate` for all automated work.
- Checks:
  - `node --test --test-isolation=none`
  - `uv sync --locked && uv run --frozen python -m unittest discover -s tests -p 'test_*.py'`
- No automatic commits or pushes; authentication stays with the user.
