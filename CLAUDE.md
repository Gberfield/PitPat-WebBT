@AGENTS.md

## Claude Code notes (macOS checkout)

- This checkout lives at `/Users/gabe/Projects/PitPat-WebBT` on macOS. `AGENTS.md`
  was written for the Linux/Omarchy host; its `/home/gabe/...` wiki paths do not
  exist here. By the owner's decision (October 30, 2026), this project has no wiki:
  the repository is the complete record. Do not enroll it. Keep documentation in
  the repo, starting from `docs/README.md`. Current state and optional
  work are in `docs/STATUS.md`; keep it up to date.
- macOS support is merged into `main` (via `mac-compat` → `codex/dedicated-safety`
  → `main`, October 2026). Branch new work from `main`. Plans are in `docs/mac/`;
  results are in `docs/macos-acceptance.md`; upkeep is in `docs/macos-operations.md`.
- Safety boundary: never arm, run or simulate physical treadmill tests without
  the user's explicit go-ahead in chat. Use `--simulate` for all automated work.
- Checks:
  - `node --test --test-isolation=none`
  - `uv sync --locked && uv run --frozen python -m unittest discover -s tests -p 'test_*.py'`
- No automatic commits or pushes; authentication stays with the user.
