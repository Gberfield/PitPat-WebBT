# 01 — Platform shim: clock, peer credentials, paths, opener

**Depends on:** nothing. **Size:** small. **Touches real hardware:** no.

## Why

Four Linux-only calls are scattered through `bridge/`. Centralize them in one new
module so every other package has one place to branch on `sys.platform`.

| Linux call today | Where | macOS equivalent |
|---|---|---|
| `time.clock_gettime(time.CLOCK_BOOTTIME)` | `bridge/safety_health.py:boot_seconds` | `time.clock_gettime(time.CLOCK_MONOTONIC)` (counts through sleep on macOS) |
| `sock.getsockopt(SOL_SOCKET, SO_PEERCRED, 12)` | `bridge/native.py:peer_uid` (also imported by `safety_ipc.py`) | `sock.getsockopt(0, socket.LOCAL_PEERCRED, 76)`, unpack `'IIh16I'`, index 1 |
| `XDG_RUNTIME_DIR` or `/run/user/<uid>` | `bridge/__main__.py`, `bridge/safety_main.py`, `bridge/desktop.py` | `~/Library/Application Support/PitPat/run` |
| `XDG_STATE_HOME` or `~/.local/state` | `bridge/__main__.py` | `~/Library/Application Support/PitPat/state` |
| `xdg-open URL` | `bridge/desktop.py` | `open URL` |

All three macOS facts were verified on the owner's Mac on 2026-10-27:
`LOCAL_PEERCRED` returned 76 bytes and uid 501 == `os.getuid()`;
`CLOCK_MONOTONIC` exceeded `time.monotonic()` by the accumulated sleep time.

## Steps

1. Create `bridge/platform_paths.py` (do **not** name it `platform.py`; that
   shadows the standard library inside the package). Contents, in the terse
   style of the rest of `bridge/`:

   ```python
   """The only module that knows which operating system it runs on."""
   import os,socket,struct,sys,time
   from pathlib import Path

   DARWIN=sys.platform=='darwin'
   SUN_PATH_MAX=104 if DARWIN else 108

   def boot_seconds():
       # Both clocks keep counting while the host sleeps.
       return time.clock_gettime(time.CLOCK_MONOTONIC if DARWIN else time.CLOCK_BOOTTIME)

   def peer_uid(sock):
       if DARWIN:
           raw=sock.getsockopt(0,socket.LOCAL_PEERCRED,struct.calcsize('IIh16I'))
           version,uid=struct.unpack('IIh16I',raw)[:2]
           if version!=0:raise ValueError('Unsupported peer credentials')
           return uid
       return struct.unpack('3i',sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))[1]

   def app_support():
       return Path.home()/'Library'/'Application Support'/'PitPat'

   def runtime_root():
       override=os.environ.get('PITPAT_RUNTIME_ROOT')
       if override:return Path(override)
       if DARWIN:return app_support()/'run'
       return Path(os.environ.get('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}'))

   def runtime_dir(simulate=False):
       name='pitpat-simulator' if simulate else 'pitpat'
       return runtime_root()/name

   def state_dir():
       if DARWIN:return app_support()/'state'
       return Path(os.environ.get('XDG_STATE_HOME',str(Path.home()/'.local/state')))/'pitpat'

   def open_url_command(url):
       return ['open',url] if DARWIN else ['xdg-open',url]
   ```

   Notes:
   - `PITPAT_RUNTIME_ROOT` is new; it lets the menu bar app (plan 06) and tests
     agree on one path. On Linux, unset means the old behavior exactly.
   - Keep the existing Linux runtime layout `$XDG_RUNTIME_DIR/pitpat` and
     `$XDG_RUNTIME_DIR/pitpat-simulator` byte-for-byte.
   - Keep the existing Linux state layout: `<state root>/pitpat`, and
     `/simulator` appended in `__main__.py` when `--simulate`.

2. `bridge/safety_health.py`: replace the body of `boot_seconds` with an import:
   `from .platform_paths import boot_seconds`. Keep the name exported from
   `safety_health` because `controller.py`, `safety_client.py`, `safety_main.py`
   and tests import it from there.

3. `bridge/native.py`: delete the local `peer_uid` and import it from
   `platform_paths`. Keep `peer_uid` importable from `bridge.native`
   (`safety_ipc.py` does `from .native import RuntimeLock,peer_uid`).
   `fcntl.flock` works on macOS unchanged.

4. `bridge/__main__.py` and `bridge/safety_main.py`: replace the inline
   `XDG_*` expressions with `runtime_dir(args.simulate)` and `state_dir()`.
   Explicit `--runtime-dir` / `--state-dir` still win.

5. `bridge/desktop.py`: replace the inline runtime path with `runtime_dir()` and
   `['xdg-open', ...]` with `open_url_command(...)`. Leave `systemctl` and
   `omarchy-shell` alone here; plan 05 handles those.

6. Grep for leftovers; this must print nothing outside `platform_paths.py`:

   ```sh
   git grep -nE "CLOCK_BOOTTIME|SO_PEERCRED|XDG_RUNTIME_DIR|XDG_STATE_HOME|/run/user|xdg-open" -- bridge
   ```

   (`integration/omarchy/.../Service.qml` still reads `XDG_RUNTIME_DIR`; that is
   Linux-only and fine.)

## Tests

Add `tests/test_platform_paths.py`:

- `peer_uid` on both ends of `socket.socketpair(socket.AF_UNIX)` equals `os.getuid()`.
- `boot_seconds()` is a float and non-decreasing across two calls.
- With `sys.platform` patched (patch `platform_paths.DARWIN`, not `sys.platform`):
  - Darwin `runtime_dir(False)` == `~/Library/Application Support/PitPat/run/pitpat`;
  - Linux with `XDG_RUNTIME_DIR=/run/user/1000` == `/run/user/1000/pitpat`;
  - `PITPAT_RUNTIME_ROOT` overrides both;
  - `runtime_dir(True)` ends with `pitpat-simulator`;
  - `open_url_command('http://127.0.0.1:8766/')` gives `open` vs `xdg-open`.
- Existing `tests/test_bridge_desktop.py` must keep passing; update only the
  expected opener if it asserts `xdg-open` and is run on macOS (patch `DARWIN`).

## Acceptance

- On macOS, with `TMPDIR` set to the resolved path as a workaround until plan 02
  (`export TMPDIR=$(python3 -c 'import os,tempfile;print(os.path.realpath(tempfile.gettempdir()))')`),
  these modules pass: `test_safety_client`, `test_safety_facade`,
  `test_safety_ipc`, `test_safety_native_frames`, `test_safety_processes`,
  `test_bridge_native`, `test_platform_paths`.
- Linux behavior unchanged (CI from plan 03, or a Linux box).

## Don't

- Don't switch `control_core.py`'s `time.monotonic` default. It is a separate
  clock choice already present on Linux; changing it is a safety-semantics change.
- Don't add a fallback to `time.monotonic()` for `boot_seconds` "just in case".
  Unknown platforms should fail loudly.
