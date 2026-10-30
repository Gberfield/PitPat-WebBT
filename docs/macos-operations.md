# macOS operations

How to run, update, repair and test the installed Mac setup. For first-time setup
and the safety limits, read the [macOS section of the README](../README.md#macos).
For what was tested and when, read the [acceptance checklist](macos-acceptance.md).

## What is installed

| Item | Location | Notes |
| --- | --- | --- |
| Safety app | `~/Applications/PitPat Safety.app` | Swift launcher plus `Contents/Resources/pitpat-safety` |
| Menu bar app | `~/Applications/PitPat.app` | A copy of the built app |
| Services | `~/Library/LaunchAgents/com.gberfield.pitpat.{safety,bridge}.plist` | Start on demand, never at login |
| Command | `~/.local/bin/pitpat` | |
| Install manifest | `~/.local/state/pitpat/install-macos.json` | Needed for rollback |
| Logs | `~/Library/Logs/PitPat/` | `safety.log` is normally empty |

The services and `pitpat` run the code in this repository folder through its
`.venv`. So:

- Keep the checkout on `main`. Switching branches changes what the installed
  services run the next time they start.
- Moving the repository folder breaks the install. Roll back first, move it, then
  install again.

## Daily use

1. Run `pitpat controls`. It starts both services and opens the menu bar app.
2. Press **Connect**, then **Start**.
3. Finish with **Stop & Disconnect**.

`pitpat services-stop` stops the services. It does not stop the belt, so use
**Stop & Disconnect** first.

After a crash or freeze, the next session may ask you to confirm Stop and
acknowledge recovery before Start works. That is intended. Nothing restarts motion
on its own.

## Updating

| What changed | What to do |
| --- | --- |
| Python or dashboard files | `uv sync --locked`, then `pitpat services-stop` and `pitpat controls` |
| Swift code, app bundles, launchd plists or the `pitpat` script | Reinstall, below |

## Reinstalling

Press **Stop & Disconnect**, quit the menu bar app, then:

```sh
pitpat services-stop
launchctl bootout gui/$(id -u)/com.gberfield.pitpat.bridge
launchctl bootout gui/$(id -u)/com.gberfield.pitpat.safety
uv run --frozen python scripts/install-macos.py rollback --manifest ~/.local/state/pitpat/install-macos.json
mv ~/.local/state/pitpat/install-macos.json ~/.local/state/pitpat/install-macos.rolled-back-$(date +%Y%m%d).json
scripts/build-menubar.sh
uv run --frozen python scripts/install-macos.py apply --manifest ~/.local/state/pitpat/install-macos.json
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.gberfield.pitpat.safety.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.gberfield.pitpat.bridge.plist
```

Rollback keeps the manifest file, and `apply` refuses to overwrite one, so it has
to be moved aside. Each install re-signs the apps ad hoc, so macOS may ask for
Bluetooth permission again.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| **Stop unconfirmed** | Use the physical stop control first. Then read the popover and the logs. |
| Fault or recovery after `pitpat stop` with nothing connected | Expected: a Stop with no treadmill cannot be confirmed. Run `pitpat services-stop`, then `pitpat controls`. |
| Bluetooth settings list Python or a terminal | The foreground commands run outside the app, so macOS credits whatever started them. For the installed services it should list **PitPat Safety**. If not, check that `Contents/MacOS/pitpat-safety` is a Mach-O binary with `file`, then reinstall. |
| Bluetooth was refused | Turn **PitPat Safety** on under System Settings → Privacy & Security → Bluetooth. |
| Rollback says a service is running or loaded | Follow its message. It checks the real launchd labels, even with `--home`. |
| `Socket path too long` | macOS limits socket paths to 104 bytes. Use a shorter `--runtime-dir`. |
| `open -b` or `pitpat://` fails for an install under `/private/tmp` | LaunchServices does not register apps there. Use `~/Applications`. |

## Why the Swift launcher exists

macOS credits Bluetooth use to a process's *responsible process*. The first
`PitPat Safety.app` used a shell script that `exec`'d Python, so the process macOS
saw was Python, and the permission went to `python3.14`. That grant covered
anything run with that interpreter.

The launcher starts the script as a child instead, so the signed app stays
responsible. It forwards SIGTERM and exits the way the child did. A launcher
started from a terminal inherits the terminal's responsibility; only launchd makes
it responsible for itself. So check attribution under launchd:

```sh
/usr/bin/python3 -c "import ctypes,sys;print(ctypes.CDLL(None).responsibility_get_pid_responsible_for_pid(int(sys.argv[1])))" PID
```

Pass the Python safety process's PID. The result should be the launcher's PID.

## Testing on a Mac

- Automated work uses `--simulate` only. Physical tests need the owner's go-ahead,
  and the crash and freeze tests need an empty belt.
- The launcher tests in `tests/test_macos_launcher.py` skip until
  `scripts/build-menubar.sh` has run.
- `SimulatorTests` are opt-in: set `PITPAT_SIMULATOR_RUNTIME` and
  `PITPAT_SIMULATOR_BRIDGE_PID`. `PITPAT_RUNTIME_DIR` points the app at a runtime
  folder, passed with `open --env`.
- With a throwaway install, copy the plists and add
  `--simulate --runtime-dir R --state-dir S`. Keep `R` short, and use a different
  label if the real services are loaded.
- The freeze and resume tests in `test_safety_processes` occasionally flake on
  Ubuntu runners. Rerun before investigating.

## Repository notes

- This is a fork. Pass `--repo Gberfield/PitPat-WebBT` to every `gh` command so
  nothing goes to upstream.
- `main` has no required checks, so GitHub's auto-merge may not wait for CI. Check
  CI before merging.
