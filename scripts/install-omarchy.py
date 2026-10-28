#!/usr/bin/env python3
"""Stage, apply or roll back only the reviewed PitPat per-user integration.

Planning never mutates the home. Applying/rollback preflight every byte before
any write, then recheck each target immediately before its atomic replacement.
No service management, login enablement, desktop reload or data deletion here.
"""
import argparse
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import stat
import sys
import tempfile
from zoneinfo import ZoneInfo

PLUGIN_FILES=('manifest.json','Service.qml','Widget.qml','Model.js')
STATIC_PATHS=('.config/omarchy/shell.json','.config/hypr/bindings.lua',
              '.config/systemd/user/pitpat-bridge.service','.local/bin/pitpat',
              '.local/share/applications/pitpat.desktop')


# Copy of bridge/platform_paths.py; this script imports only the standard library.
SYSTEM_LINKS={'/var':'private/var','/tmp':'private/tmp','/etc':'private/etc'} if sys.platform=='darwin' else {}

def trusted_system_link(path):
    # macOS ships /var, /tmp and /etc as root-owned links into /private.
    target=SYSTEM_LINKS.get(str(path))
    if target is None:return False
    info=os.lstat(path)
    return info.st_uid==0 and os.readlink(path)==target


def checked(path):
    path=Path(path).absolute()
    for parent in [path,*path.parents]:
        if parent.is_symlink() and not trusted_system_link(parent):raise ValueError('Symlink destination refused: '+str(parent))
    if path.exists() and (not path.is_file() or path.stat().st_uid!=os.getuid()):
        raise ValueError('Target must be a regular user-owned file: '+str(path))
    return path


def read(path):
    path=checked(path)
    return path.read_bytes() if path.exists() else None


def digest(value):return hashlib.sha256(value).hexdigest() if value is not None else None

def packed(value):return base64.b64encode(value).decode() if value is not None else None

def unpacked(value):return base64.b64decode(value,validate=True) if value is not None else None


def allowed(home,version=2):
    paths={str(home/p) for p in STATIC_PATHS}|{str(home/'.config/omarchy/plugins/gabe.pitpat'/p) for p in PLUGIN_FILES}
    if version==2:paths.add(str(home/'.config/systemd/user/pitpat-safety.service'))
    return paths


def unit_quote(text):return '"'+str(text).replace('%','%%').replace('\\','\\\\').replace('"','\\"')+'"'


def plan(home,repo,runtime_dir=None):
    home,repo=Path(home).absolute(),Path(repo).absolute()
    shell=home/STATIC_PATHS[0];bindings=home/STATIC_PATHS[1]
    raw=read(shell);config=json.loads(raw) if raw else {}
    layout=config.setdefault('bar',{}).setdefault('layout',{})
    right=layout.setdefault('right',[])
    if not any(isinstance(r,dict) and r.get('id')=='gabe.pitpat' for r in right):
        index=next((i+1 for i,r in enumerate(right) if isinstance(r,dict) and r.get('id')=='gabe.tray'),0)
        right.insert(index,{'id':'gabe.pitpat'})
    binding_bytes=read(bindings) or b''
    binding_text=binding_bytes.decode()
    # Strip only our exactly delimited integration before checking user conflicts.
    start='-- BEGIN PITPAT CONTROLS\n';end='-- END PITPAT CONTROLS\n'
    pattern=re.compile(re.escape(start)+'.*?'+re.escape(end),re.S)
    without=pattern.sub('',binding_text)
    for combination in re.findall(r'(?:o\.bind|hl\.bind)\s*\(\s*["\']([^"\']+)',without):
        parts={p.strip().upper() for p in combination.split('+')}
        if parts in ({'SUPER','F9'},{'SUPER','F10'},{'SUPER','F11'}):raise ValueError('Shortcut already bound: '+combination)
    helper=home/'.local/bin/pitpat'
    lines=[start.rstrip('\n')]
    for key,label,op in [('F9','PitPat controls','controls'),('F10','PitPat Start/Pause','start-pause'),('F11','PitPat Stop','stop')]:
        command=shlex.quote(str(helper))+' '+op
        lines.append('o.bind('+json.dumps('SUPER + '+key)+', '+json.dumps(label)+', '+json.dumps(command)+')')
    lines.append(end.rstrip('\n'))
    block='\n'.join(lines)+'\n'
    if start in binding_text:
        binding_post=pattern.sub(lambda _:block,binding_text)
    else:binding_post=binding_text+('' if not binding_text or binding_text.endswith('\n') else '\n')+block
    python=repo/'.venv/bin/python'
    wrapper=(repo/'integration/bin/pitpat').read_text().replace('@REPO_SHELL@',shlex.quote(str(repo))).replace('@PYTHON_SHELL@',shlex.quote(str(python)))
    service=(repo/'integration/systemd/pitpat-bridge.service').read_text().replace('@REPO_UNIT@',str(repo).replace('%','%%').replace('\\','\\\\').replace(' ','\\x20')).replace('@PYTHON_UNIT@',unit_quote(python))
    desktop=(repo/'integration/applications/pitpat.desktop').read_text().replace('@HELPER_DESKTOP@',unit_quote(helper))
    outputs={shell:(json.dumps(config,indent=2,ensure_ascii=False)+'\n').encode(),bindings:binding_post.encode(),
             home/STATIC_PATHS[2]:service.encode(),helper:wrapper.encode(),home/STATIC_PATHS[4]:desktop.encode()}
    safety=(repo/'integration/systemd/pitpat-safety.service').read_text().replace('@REPO_UNIT@',str(repo).replace('%','%%').replace('\\','\\\\').replace(' ','\\x20')).replace('@PYTHON_UNIT@',unit_quote(python))
    outputs[home/'.config/systemd/user/pitpat-safety.service']=safety.encode()
    for name in PLUGIN_FILES:outputs[home/'.config/omarchy/plugins/gabe.pitpat'/name]=(repo/'integration/omarchy/gabe.pitpat'/name).read_bytes()
    operations=[]
    for path,post in outputs.items():
        before=read(path)
        mode=(path.stat().st_mode&0o777) if before is not None else (0o755 if path==helper else 0o644)
        operations.append(dict(path=str(path),before=packed(before),before_sha256=digest(before),
                               after=packed(post),after_sha256=digest(post),mode=mode))
    return dict(version=2,home=str(home),repo=str(repo),
                id=datetime.now(ZoneInfo('America/New_York')).strftime('%Y%m%dT%H%M%S%z')+'-'+secrets.token_hex(4),
                operations=operations)


def validate(plan,home):
    home=Path(home).absolute()
    if plan.get('version') not in (1,2) or plan.get('home')!=str(home):raise ValueError('Install plan home/version mismatch')
    if not re.fullmatch(r'\d{8}T\d{6}[+-]\d{4}-[0-9a-f]{8}',plan.get('id','')):raise ValueError('Invalid backup identity')
    operations=plan.get('operations',[])
    paths=[item['path'] for item in operations]
    if len(paths)!=len(set(paths)) or set(paths)!=allowed(home,plan['version']):raise ValueError('Install plan contains unexpected targets')
    for item in operations:
        checked(item['path'])
        for key in ('before','after'):
            if digest(unpacked(item[key]))!=item[key+'_sha256']:raise ValueError('Corrupt install payload')
        if item['after'] is None or type(item['mode']) is not int or not 0<=item['mode']<=0o777:raise ValueError('Invalid install mode/payload')


def atomic(path,data,mode):
    path=checked(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    if data is None:
        if path.exists():path.unlink()
        return
    fd,tmp=tempfile.mkstemp(prefix='.pitpat-',dir=path.parent)
    try:
        os.fchmod(fd,mode)
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.replace(tmp,path)
        directory_fd=os.open(path.parent,os.O_DIRECTORY)
        try:os.fsync(directory_fd)
        finally:os.close(directory_fd)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)


def preflight(plan,rollback=False):
    for item in plan['operations']:
        current=digest(read(item['path']))
        acceptable=(item['before_sha256'],item['after_sha256'])
        if current not in acceptable:raise ValueError('File drift; no files changed: '+item['path'])
        # Restoring untouched preimages is idempotent; edited postimages hold all restoration.


def apply(plan,home):
    validate(plan,home);preflight(plan)
    backup=Path(home)/'.local/state/pitpat/install-backups'/plan['id']/'manifest.json'
    # Only the backup subtree is private; do not chmod unrelated user config.
    for path in [backup.parent.parent.parent,backup.parent.parent,backup.parent]:
        for ancestor in [path,*path.parents]:
            if ancestor.is_symlink() and not trusted_system_link(ancestor):raise ValueError('Symlink backup directory refused')
        path.mkdir(parents=True,exist_ok=True,mode=0o700);path.chmod(0o700)
    data=(json.dumps(plan,indent=2)+'\n').encode()
    prior=read(backup)
    if prior is not None and prior!=data:raise ValueError('Backup identity collision')
    if prior is None:atomic(backup,data,0o600)
    for item in plan['operations']:
        path=Path(item['path']);current=digest(read(path))
        if current==item['after_sha256']:continue
        if current!=item['before_sha256']:raise ValueError('File changed during installation: '+str(path))
        atomic(path,unpacked(item['after']),item['mode'])


def rollback(plan,home):
    validate(plan,home);preflight(plan,True)
    for item in reversed(plan['operations']):
        path=Path(item['path']);current=digest(read(path))
        if current==item['before_sha256']:continue
        if current!=item['after_sha256']:raise ValueError('File changed during rollback: '+str(path))
        atomic(path,unpacked(item['before']),item['mode'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--plan',type=Path);group.add_argument('--apply',type=Path);group.add_argument('--rollback',type=Path)
    parser.add_argument('--home',type=Path,default=Path.home());parser.add_argument('--runtime-dir',type=Path)
    args=parser.parse_args()
    try:
        if args.plan:
            result=plan(args.home,Path(__file__).resolve().parent.parent,args.runtime_dir)
            atomic(args.plan,(json.dumps(result,indent=2)+'\n').encode(),0o600)
            print('Staged '+str(len(result['operations']))+' file operations: '+str(args.plan))
        else:
            path=args.apply or args.rollback;result=json.loads(path.read_text())
            (apply if args.apply else rollback)(result,args.home)
            print('Applied' if args.apply else 'Rolled back')
    except (ValueError,OSError,KeyError,TypeError) as exc:parser.exit(1,str(exc)+'\n')


if __name__=='__main__':main()
