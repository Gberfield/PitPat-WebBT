# 03 — Portable test suite + GitHub Actions (Linux and macOS)

**Depends on:** 01, 02. **Size:** small. **Touches real hardware:** no.

## Why

The repository has no CI. The suite was only ever run on the Linux host. After
01–02 the remaining macOS failure is `tests/test_omarchy_install.py`, which shells
out to `systemd-analyze`. Lock both platforms in with CI so later Mac work cannot
silently break Linux, and vice versa.

## Steps

1. `tests/test_omarchy_install.py`: find the test that runs `systemd-analyze`
   (it validates generated unit files). Decorate just that test:

   ```python
   @unittest.skipUnless(shutil.which('systemd-analyze'), 'systemd-analyze unavailable')
   ```

   Do not skip the whole module; the other install tests are pure Python and
   must run on macOS too.

2. Check other Linux-only tools the same way (`git grep -n "subprocess\|which(" tests`).
   `tests/check_qml_service.py` needs Quickshell; it is not collected by
   `unittest discover` (`test_*.py` pattern) so leave it.

3. Add `.github/workflows/tests.yml`:

   ```yaml
   name: tests
   on:
     push:
       branches: [mac-compat, 'mac/**']
     pull_request:
   permissions:
     contents: read
   jobs:
     test:
       strategy:
         fail-fast: false
         matrix:
           os: [ubuntu-latest, macos-latest]
       runs-on: ${{ matrix.os }}
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-node@v4
           with: { node-version: '22' }
         - uses: astral-sh/setup-uv@v6
         - run: uv sync --locked
         - run: node --test --test-isolation=none
         - run: node --check treadmill.js
         - run: uv run --frozen python -m unittest discover -s tests -p 'test_*.py' -v
         - run: uv lock --check
         - run: git diff --check HEAD~1 || true
   ```

   Pin action major versions as above. If `node --test --test-isolation=none` is
   rejected by Node 22, use the Node version the README targets; check
   `node --test --help`.

4. Tests must never touch Bluetooth in CI. They don't today (synthetic plant /
   `SimulatorBackend`). Add a guard test in `tests/test_platform_paths.py` or a
   new `tests/test_no_bluetooth_imports.py`: import every `bridge` module except
   `backends` and assert `'bleak' not in sys.modules`.

## Acceptance

- Both matrix jobs green on a PR into `mac-compat`.
- Local macOS run: all Python modules OK, 90+ JS tests OK.
- PR description includes the per-OS test counts.

## Don't

- Don't add `@skip` to make a failure go away unless the test genuinely needs a
  Linux-only binary. Explain each skip in the PR.
- Don't enable workflows that deploy or publish anything.
