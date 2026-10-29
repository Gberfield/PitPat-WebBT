"""Fixed-argument desktop routing. Helpers never claim motion ownership."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from .platform_paths import DARWIN, check_socket_path, open_url_command, runtime_dir

UID=os.getuid()
LABELS=('com.gberfield.pitpat.safety','com.gberfield.pitpat.bridge')


async def safety_stop(runtime):
    reader,writer=await asyncio.wait_for(asyncio.open_unix_connection(str(check_socket_path(runtime/'safety.sock'))),2)
    try:
        writer.write(b'{"v":1,"op":"hello","kind":"helper"}\n');await writer.drain()
        hello=json.loads(await asyncio.wait_for(reader.readline(),3))
        if hello.get('event')!='authorized':raise ValueError('Safety authorization failed')
        writer.write(b'{"v":1,"id":"stop","op":"stop","authority":null,"args":{}}\n');await writer.drain()
        async def result():
            while True:
                line=await reader.readline()
                if not line:raise ValueError('Safety unavailable; Stop unconfirmed. Use physical stop.')
                message=json.loads(line)
                if message.get('id')=='stop':return message
        message=await asyncio.wait_for(result(),8)
        if not message.get('ok') or message.get('result',{}).get('outcome')!='stopped_confirmed':
            raise ValueError('Stop unconfirmed. Use the physical stop control.')
    finally:writer.close();await writer.wait_closed()


def run(args):
    result=subprocess.run(args,capture_output=True,text=True,timeout=10)
    if result.returncode or 'ERROR:' in (result.stdout or ''):
        raise ValueError((result.stderr or result.stdout or 'Desktop command failed').strip())


def start_services():
    # Without -k, kickstart leaves a running service alone, like systemctl start.
    if DARWIN:
        for label in LABELS:run(['launchctl','kickstart',f'gui/{UID}/{label}'])
    else:run(['systemctl','--user','start','pitpat-bridge.service'])


def stop_services():
    # Bridge first, then safety. A service that is not running counts as stopped, like systemctl stop.
    if DARWIN:
        for label in reversed(LABELS):
            try:run(['launchctl','kill','SIGTERM',f'gui/{UID}/{label}'])
            except ValueError as exc:
                if 'No process to signal' not in str(exc):raise
    else:
        for unit in ('pitpat-bridge.service','pitpat-safety.service'):run(['systemctl','--user','stop',unit])


def main(argv=None):
    parser=argparse.ArgumentParser(description='PitPat Omarchy controls')
    parser.add_argument('operation',choices=['controls','start-pause','stop','services-stop','dashboard','history'])
    args=parser.parse_args(argv)
    try:
        if args.operation=='controls':
            start_services()
            run(['open','-b','com.gberfield.pitpat.menubar'] if DARWIN else ['omarchy-shell','shell','toggle','gabe.pitpat'])
        elif args.operation=='start-pause':
            # Start/Pause must come from the lease-holding motion owner.
            run(['open','-g','pitpat://start-pause'] if DARWIN else ['omarchy-shell','gabe.pitpat','startPause'])
        elif args.operation=='stop':
            # One-shot authenticated Stop does not require the widget or its lease.
            runtime=runtime_dir()
            asyncio.run(safety_stop(runtime))
        elif args.operation=='services-stop':
            stop_services()
            print('PitPat services stopped. This does not stop the belt; use Stop & Disconnect first.')
        else:run(open_url_command('http://127.0.0.1:8766/'+('#history-panel' if args.operation=='history' else '')))
        return 0
    except (OSError,ValueError,TimeoutError,subprocess.SubprocessError) as exc:
        # Safety's own unconfirmed-Stop messages already carry the guidance.
        guidance='Stop unconfirmed. Use the physical stop control. ' if args.operation=='stop' and 'Stop unconfirmed' not in str(exc) else ''
        print('PitPat: '+guidance+str(exc),file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
