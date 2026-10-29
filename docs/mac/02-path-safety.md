# 02 — Private-path checks vs. macOS system symlinks; socket path length

**Depends on:** 01. **Size:** small. **Touches real hardware:** no.

## Why

Two helpers reject any path that has a symlink anywhere in its ancestry:

- `bridge/store.py:private_directory` (used for state and runtime directories);
- `scripts/install-omarchy.py:checked` (and plan 07's macOS installer).

On macOS, `/var`, `/tmp` and `/etc` are root-owned symlinks to `/private/var`,
`/private/tmp`, `/private/etc`. Every `tempfile` directory lives under
`/var/folders/...`, so 50+ tests fail with
`ValueError: Private path contains a symlink` / `Symlink destination refused: /var`.

The check is a deliberate defense (a user-writable symlink could redirect private
state). Keep it. Only exempt these three exact, root-owned, OS-provided links.

Separately, macOS limits `AF_UNIX` paths to 104 bytes. Long runtime paths should
fail early with a clear message rather than an `OSError` from `bind`.

## Steps

1. In `bridge/platform_paths.py` (from plan 01) add:

   ```python
   SYSTEM_LINKS={'/var':'private/var','/tmp':'private/tmp','/etc':'private/etc'} if DARWIN else {}

   def trusted_system_link(path):
       # macOS ships /var, /tmp and /etc as root-owned links into /private.
       target=SYSTEM_LINKS.get(str(path))
       if target is None:return False
       info=os.lstat(path)
       return info.st_uid==0 and os.readlink(path)==target
   ```

   Exact string match on the link text, `st_uid == 0`, top-level only. No
   `resolve()`-based shortcuts.

2. `bridge/store.py:private_directory`: change the loop to

   ```python
   for parent in reversed([path, *path.parents]):
       if parent.is_symlink() and not trusted_system_link(parent): raise ValueError('Private path contains a symlink')
   ```

   Everything else (mkdir 0700, owner check, chmod) unchanged.

3. `scripts/install-omarchy.py:checked`: same one-line change. The installer is a
   standalone script that imports only the standard library (it does not put the
   repo on `sys.path`), so duplicate `SYSTEM_LINKS` and `trusted_system_link`
   into it with a one-line comment pointing at `bridge/platform_paths.py`.
   Plan 07 later moves it into `scripts/install_common.py`.

4. Socket path length. In `platform_paths.py`:

   ```python
   def check_socket_path(path):
       if len(os.fsencode(str(path)))>=SUN_PATH_MAX:
           raise ValueError(f'Socket path too long for this OS ({SUN_PATH_MAX} bytes): {path}')
       return path
   ```

   Call it where sockets are created/connected: `NativeServer.serve`
   (`control.sock`), `SafetyServer.serve` (`safety.sock`), `SafetyClient`
   connect, and `desktop.safety_stop`. All raise `ValueError`, which the existing
   callers already handle.

## Tests

- `tests/test_platform_paths.py` additions:
  - `trusted_system_link(Path('/var'))` is `True` on macOS, `False` on Linux;
  - a symlink you create in a temp dir is never trusted;
  - `private_directory(tempfile.mkdtemp()/'x')` succeeds on macOS **without**
    the `TMPDIR` workaround;
  - `private_directory` still rejects a user-created symlinked ancestor
    (existing tests should already cover this; make sure they still run and pass);
  - `check_socket_path` rejects a 200-character path and accepts a short one.
- Full suite on macOS **without** the `TMPDIR` override.

## Acceptance

On macOS, plain `uv run --frozen python -m unittest discover -s tests -p 'test_*.py'`
passes except `test_omarchy_install` (needs `systemd-analyze`, fixed in plan 03).
Linux unchanged.

## Don't

- Don't call `.resolve()` on user-supplied paths to "remove" symlinks.
- Don't widen the allowlist (no `/Users`, `/Volumes`, `/opt/homebrew`).
