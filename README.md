# PitPat Treadmill Web Dashboard

A web-based dashboard to control and monitor a PitPat treadmill via Bluetooth. This checkout's `main` branch is the original static browser dashboard.

## Prerequisites

- A Bluetooth-capable computer and a compatible PitPat treadmill. Compatibility with every model is not established.
- A browser exposing `navigator.bluetooth`, such as Chromium with Web Bluetooth available on the host. This static implementation calls Web Bluetooth directly; it does not include a Firefox Bluetooth bridge.
- A secure browser context (HTTPS or a local loopback origin) and permission to access the Bluetooth adapter.
- Internet access for the third-party CSS, fonts and scripts loaded by `index.html`.

## Run locally

From the repository root, serve the static files using Python 3:

```sh
python3 -m http.server 8765 --bind 127.0.0.1
```

Open <http://127.0.0.1:8765/>. No package installation or build step is required. Stop this local file server with Ctrl+C when finished. Merely serving or opening the page does not validate treadmill behavior.

The dashboard can send motion commands. Keep the treadmill's physical stop control available; browser controls and a Bluetooth connection are not a hardware safety interlock. No physical acceptance was performed for this documentation update.

History is stored in this browser's localStorage. Export it before clearing browser data or changing browser/origin; a different port or browser has separate storage. Treat imported history as private data.

## Branch status

The local bridge, independent safety process and Omarchy integration are proposed separately in [draft PR #1](https://github.com/Gberfield/PitPat-WebBT/pull/1), on `codex/dedicated-safety`. They are not included in `main`. Read that branch's README, `docs/dedicated-safety-acceptance.md` and `docs/closeout-handoff.md` for its setup, dated results and remaining acceptance boundaries. Its reported application-crash/freeze checks do not certify safety-process failure, Bluetooth/BlueZ loss, host sleep/power loss or manufacturer safeguards. Do not infer release readiness from this static dashboard's setup instructions.

## Upstream demo

The [original upstream demo](https://keirany.github.io/PitPat-WebBT/) is hosted by keirany. It is separate from this fork and its draft bridge implementation.

## Static check

```sh
node --check treadmill.js
```

This checks JavaScript syntax only. This `main` snapshot has no automated hardware acceptance suite.

## License

See [LICENSE](LICENSE).
