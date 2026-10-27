# 08 — Docs and acceptance checklist

**Depends on:** all previous packages. **Size:** small. **Touches real hardware:**
no (the checklist is filled in by the owner).

## Steps

1. `README.md`: add a **macOS** section after "Firefox and the local Bluetooth
   bridge". Keep it short and factual:
   - Static route: Chrome/Edge on macOS have Web Bluetooth; Safari and Firefox
     do not → use the bridge.
   - Foreground bridge: same `uv` commands as Linux; first run asks for Bluetooth
     permission for the terminal app.
   - Paths: runtime `~/Library/Application Support/PitPat/run/pitpat`, state
     `~/Library/Application Support/PitPat/state`, logs `~/Library/Logs/PitPat/`.
   - Installed route: `scripts/install-macos.py`, then the printed
     `launchctl bootstrap` lines; services start on demand only.
   - Menu bar app and its hotkeys; `pitpat stop` goes straight to the safety
     process.
   - The same safety limits paragraph as Linux, plus: macOS sleep, lid close and
     App Nap are **not** verified; keep the physical stop control available.
   - Rollback steps.

2. `docs/macos-acceptance.md`: a dated checklist modeled on
   `docs/dedicated-safety-acceptance.md`, with two sections:
   - **Software (implementer fills in):** test counts per OS, CI run link,
     simulator walk via browser, via menu bar, via hotkeys, recovery after
     `kill -STOP` of the bridge, installer plan/apply/rollback.
   - **Physical (owner only, leave unchecked):** Bluetooth permission prompt via
     `PitPat Safety.app`; connect/telemetry without Start; Start at minimum speed
     and Stop via menu bar; Stop via hotkey; application-crash stop
     (`kill -9` the bridge mid-walk) on an empty belt; application-freeze stop
     (`kill -STOP`); behavior when the Mac sleeps (expected: not guaranteed —
     record what happens, do not claim support).

3. `CLAUDE.md` / `AGENTS.md`: update the "Active branch" note when `mac-compat`
   merges. Do not rewrite the Linux wiki paths in `AGENTS.md`; the owner manages
   wiki enrollment.

## Acceptance

Docs build nothing; review is by reading. Every command in the README section
was copy-pasted and run on a Mac by the implementer (simulator variants only),
and the PR says so.
