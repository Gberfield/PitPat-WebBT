"""On-demand sole BLE owner; startup never scans or connects."""
import argparse,asyncio,os,signal
from pathlib import Path
from .native import RuntimeLock
from .platform_paths import runtime_dir
from .safety_core import SafetyCore
from .safety_ipc import SafetyServer
from .safety_health import boot_seconds

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--simulate',action='store_true');p.add_argument('--runtime-dir',type=Path);p.add_argument('--state-dir',type=Path)
    args=p.parse_args(argv)
    runtime=args.runtime_dir or runtime_dir(args.simulate)
    boot_seconds()
    try:guard=RuntimeLock(runtime)
    except ValueError as exc:p.error(str(exc))
    async def run():
        from .backends import SimulatorBackend,BleakBackend
        core=SafetyCore(SimulatorBackend() if args.simulate else BleakBackend());server=SafetyServer(core,runtime,guard)
        end=asyncio.Event();loop=asyncio.get_running_loop()
        for sig in (signal.SIGINT,signal.SIGTERM):loop.add_signal_handler(sig,end.set)
        try:await server.serve();await end.wait()
        finally:await server.close()
    try:asyncio.run(run())
    finally:guard.close()
    return 0
if __name__=='__main__':raise SystemExit(main())
