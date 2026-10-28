"""Fixed-argument desktop routing. Helpers never claim motion ownership."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
from .platform_paths import open_url_command, runtime_dir


async def safety_stop(runtime):
    reader,writer=await asyncio.wait_for(asyncio.open_unix_connection(str(runtime/'safety.sock')),2)
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


def main(argv=None):
    parser=argparse.ArgumentParser(description='PitPat Omarchy controls')
    parser.add_argument('operation',choices=['controls','start-pause','stop','dashboard','history'])
    args=parser.parse_args(argv)
    try:
        if args.operation=='controls':
            run(['systemctl','--user','start','pitpat-bridge.service'])
            run(['omarchy-shell','shell','toggle','gabe.pitpat'])
        elif args.operation=='start-pause':run(['omarchy-shell','gabe.pitpat','startPause'])
        elif args.operation=='stop':
            # One-shot authenticated Stop does not require the widget or its lease.
            runtime=runtime_dir()
            asyncio.run(safety_stop(runtime))
        else:run(open_url_command('http://127.0.0.1:8766/'+('#history-panel' if args.operation=='history' else '')))
        return 0
    except (OSError,ValueError,TimeoutError,subprocess.SubprocessError) as exc:
        guidance='Stop unconfirmed. Use the physical stop control. ' if args.operation=='stop' else ''
        print('PitPat: '+guidance+str(exc),file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
