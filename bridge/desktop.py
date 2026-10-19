"""Fixed-argument desktop routing. Helpers never claim motion ownership."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys


async def native_stop(runtime):
    reader,writer=await asyncio.wait_for(asyncio.open_unix_connection(str(runtime/'control.sock')),2)
    try:
        writer.write(b'{"v":1,"op":"hello","kind":"helper"}\n');await writer.drain()
        hello=json.loads(await asyncio.wait_for(reader.readline(),3))
        generation=hello['generation']
        writer.write((json.dumps(dict(v=1,id='stop',op='stop',generation=generation,args={}))+'\n').encode());await writer.drain()
        async def result():
            while True:
                line=await reader.readline()
                if not line:raise ValueError('Bridge connection lost; Stop unconfirmed')
                message=json.loads(line)
                if message.get('id')=='stop':return message
        message=await asyncio.wait_for(result(),7)
        if not message.get('ok') or not message.get('result',{}).get('confirmed'):
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
            runtime=Path(os.environ.get('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}'))/'pitpat'
            asyncio.run(native_stop(runtime))
        else:run(['xdg-open','http://127.0.0.1:8766/'+('#history-panel' if args.operation=='history' else '')])
        return 0
    except (OSError,ValueError,TimeoutError,subprocess.SubprocessError) as exc:
        print('PitPat: '+str(exc),file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
