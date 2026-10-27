import argparse
import os
from pathlib import Path
from aiohttp import web
from .safety_client import SafetyClient
import secrets
from .controller import Controller
from .server import create_app
from .native import RuntimeLock, NativeServer
from .store import WalkStore
from .recorder import Recorder
from .platform_paths import runtime_dir, state_dir


def main():
    parser = argparse.ArgumentParser(description='Loopback-only PitPat Bluetooth bridge')
    parser.add_argument('--simulate', action='store_true', help='Synthetic treadmill, no Bluetooth access')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--state-dir', type=Path, help='Explicit private state directory (isolated tests)')
    parser.add_argument('--runtime-dir', type=Path, help='Explicit private IPC directory (isolated tests)')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('port must be 1–65535')
    state = args.state_dir or state_dir()
    if args.state_dir is None and args.simulate: state /= 'simulator'
    runtime = args.runtime_dir or runtime_dir(args.simulate)
    # Lock before touching the database or HTTP/native listeners.
    try: guard = RuntimeLock(runtime, name='bridge.lock')
    except ValueError as exc: parser.error(str(exc))
    try:
        client = SafetyClient(runtime, secrets.token_hex(16))
        controller = Controller(client, recorder_factory=lambda: Recorder(WalkStore(state / 'walks.sqlite3')))
        native = NativeServer(controller, runtime, guard=guard, simulator=args.simulate)
        print('SIMULATOR — no physical treadmill' if args.simulate else 'Real Bluetooth mode — no scan until Connect')
        web.run_app(create_app(controller, port=args.port, simulator=args.simulate, native=native),
                    host='127.0.0.1', port=args.port, access_log=None, shutdown_timeout=25)
    finally: guard.close()


if __name__ == '__main__':
    main()
