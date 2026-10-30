# 07 — macOS installer with plan/apply/rollback

**Depends on:** 05, 06 (and the safety bundle from 04). **Size:** medium.
**Touches real hardware:** no.

## Why

`scripts/install-omarchy.py` is the reviewed model: it plans without mutating
`$HOME`, preflights every byte, re-checks each target immediately before an
atomic replace, keeps exact per-file backups in a manifest, detects drift, and
rolls back. It never manages services, enables login items or deletes data.
Build `scripts/install-macos.py` with the **same guarantees**.

## Steps

1. Read `scripts/install-omarchy.py` and `tests/test_omarchy_install.py`
   end to end. Reuse its helpers by moving the platform-neutral ones
   (`checked`, `read`, `digest`, `packed`/`unpacked`, manifest write/read,
   atomic replace, rollback) into `scripts/install_common.py`, and import them
   from both installers. The Omarchy installer's behavior and tests must not
   change; run its tests before and after the move.

2. macOS targets (all under the user's home; nothing system-wide, no sudo):

   | Target | Source |
   |---|---|
   | `~/Library/LaunchAgents/com.gberfield.pitpat.safety.plist` | plan 05 template |
   | `~/Library/LaunchAgents/com.gberfield.pitpat.bridge.plist` | plan 05 template |
   | `~/Applications/PitPat Safety.app/...` | plan 04 bundle, placeholders filled |
   | `~/Applications/PitPat.app/...` | plan 06 build output |
   | `~/.local/bin/pitpat` | `integration/bin/pitpat`, placeholders filled |
   | `~/Library/Logs/PitPat/` | created 0700, never deleted on rollback |

   App bundles are directories; record every file inside them in the manifest
   with its hash, and roll back per file. Refuse to overwrite a bundle that has
   files not in the previous manifest (drift).

3. Commands:

   ```sh
   uv run --frozen python scripts/install-macos.py plan     # prints planned changes, writes nothing
   uv run --frozen python scripts/install-macos.py apply --manifest <path>
   uv run --frozen python scripts/install-macos.py rollback --manifest <path>
   ```

   Mirror the Omarchy CLI flags exactly where they exist.

4. After `apply`, print — do not run — the next steps:

   ```
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.gberfield.pitpat.safety.plist
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.gberfield.pitpat.bridge.plist
   open ~/Applications/PitPat.app
   ```

   and before `rollback`, require that `launchctl print gui/$UID/<label>` shows
   neither service running (or `--force-while-loaded` is absent → refuse).

5. Ad-hoc sign both bundles after writing them: `codesign --force --deep --sign - <app>`.
   Record the post-sign hashes in the manifest (signing changes bytes).

## Tests

`tests/test_macos_install.py` against a temp `$HOME` (pass `--home`): plan writes
nothing; apply creates every target with expected modes (plists 0644, scripts and
executables 0755, log dir 0700); drift detection refuses; rollback restores
previous bytes and removes created files; placeholders contain no `@`. Skip the
`codesign` step in tests unless `shutil.which('codesign')`; when present, assert
`codesign --verify` succeeds.

## Acceptance

`plan` → `apply` → bootstrap → simulator walk via menu bar → bootout →
`rollback` leaves `~/Library/LaunchAgents`, `~/Applications` and
`~/.local/bin` byte-identical to before (compare a pre-install listing + hashes).
Record that in the PR.

## Don't

- No `sudo`, no `/Library`, no login items, no `launchctl` calls from the installer.
- Never delete walk databases, logs or state on rollback.
