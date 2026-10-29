#!/usr/bin/env python3
"""Plan, apply or roll back only the reviewed PitPat per-user macOS integration.

Planning never writes. Apply and rollback preflight every byte before any write,
then recheck each target immediately before its atomic replacement. Everything
lives under the home: no sudo, no /Library, no login items, no service
management. The one launchctl call is a read-only `print` that keeps rollback
away from loaded services. Rollback never deletes walk databases, logs or state.
"""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

sys.path.insert(0,str(Path(__file__).resolve().parent))
from install_common import atomic,checked,digest,packed,preflight,read,trusted_system_link,unpacked

LABELS=('com.gberfield.pitpat.safety','com.gberfield.pitpat.bridge')
STATIC=tuple(f'Library/LaunchAgents/{label}.plist' for label in LABELS)+('.local/bin/pitpat',)
SAFETY_APP='Applications/PitPat Safety.app'
MENUBAR_APP='Applications/PitPat.app'
BUNDLES={SAFETY_APP:('Contents/Info.plist','Contents/MacOS/pitpat-safety','Contents/Resources/pitpat-safety'),
         MENUBAR_APP:('Contents/Info.plist','Contents/MacOS/PitPatMenuBar')}
SIGNATURE='Contents/_CodeSignature'
MENUBAR_BUILD='integration/macos/PitPatMenuBar/.build/PitPat.app'
LAUNCHER_BUILD='integration/macos/PitPatMenuBar/.build/PitPatSafety'
LOGS='Library/Logs/PitPat'
PLACEHOLDER=re.compile(rb'@[A-Z_]+@')


def managed(home,path):
    # Signing writes its own files into _CodeSignature; nothing else in a bundle is ours.
    path=Path(path)
    if path in {home/p for p in STATIC}:return True
    for bundle,files in BUNDLES.items():
        if path in {home/bundle/f for f in files}:return True
        if path.parent==home/bundle/SIGNATURE and re.fullmatch(r'[A-Za-z0-9-]+',path.name):return True
    return False


def unlinked(path):
    for parent in [path,*path.parents]:
        if parent.is_symlink() and not trusted_system_link(parent):raise ValueError('Symlink destination refused: '+str(parent))
    return path


def directory(path):
    unlinked(path)
    if path.is_symlink() or not path.is_dir() or path.stat().st_uid!=os.getuid():raise ValueError('Must be a user-owned directory: '+str(path))
    return path


def tree(root):
    # Every regular file under root, refusing symlinks anywhere inside it.
    if not os.path.lexists(root):return []
    directory(root);files=[]
    for parent,dirs,names in os.walk(root):
        for name in dirs+names:
            if (Path(parent)/name).is_symlink():raise ValueError('Symlink in app bundle refused: '+str(Path(parent)/name))
        files+=[Path(parent)/name for name in names]
    return sorted(files)


def bundle_files(home,bundle):
    files=tree(home/bundle)
    for path in files:
        if not managed(home,path):raise ValueError('App bundle has files this installer does not manage; no files changed: '+str(path))
    return files


def plan(home,repo,menubar=None,launcher=None):
    home,repo=Path(home).absolute(),Path(repo).absolute()
    menubar=Path(menubar or repo/MENUBAR_BUILD).absolute();launcher=Path(launcher or repo/LAUNCHER_BUILD).absolute()
    for built in (menubar/'Contents/MacOS/PitPatMenuBar',launcher):
        if not built.is_file():raise ValueError('Menu bar app or safety launcher not built; run scripts/build-menubar.sh first: '+str(built))
    for path in tree(menubar):
        relative=path.relative_to(menubar)
        if str(relative) not in BUNDLES[MENUBAR_APP] and relative.parent!=Path(SIGNATURE):
            raise ValueError('Unexpected file in menu bar build: '+str(path))
    python=repo/'.venv/bin/python';logs=home/LOGS
    safety=repo/'integration/macos/PitPat Safety.app/Contents'
    def shell(path):
        return path.read_text().replace('@REPO_SHELL@',shlex.quote(str(repo))).replace('@PYTHON_SHELL@',shlex.quote(str(python))).encode()
    def plist(label):
        text=(repo/'integration/launchd'/(label+'.plist')).read_text()
        for key,value in (('@REPO@',repo),('@PYTHON@',python),('@LOGS@',logs),('@SAFETY_APP_EXECUTABLE@',home/SAFETY_APP/BUNDLES[SAFETY_APP][1])):
            text=text.replace(key,escape(str(value)))
        return text.encode()
    outputs={home/STATIC[0]:(plist(LABELS[0]),0o644),home/STATIC[1]:(plist(LABELS[1]),0o644),
             home/STATIC[2]:(shell(repo/'integration/bin/pitpat'),0o755),
             home/SAFETY_APP/'Contents/Info.plist':((safety/'Info.plist').read_bytes(),0o644),
             home/SAFETY_APP/'Contents/MacOS/pitpat-safety':(launcher.read_bytes(),0o755),
             home/SAFETY_APP/'Contents/Resources/pitpat-safety':(shell(safety/'Resources/pitpat-safety'),0o755),
             home/MENUBAR_APP/'Contents/Info.plist':((menubar/'Contents/Info.plist').read_bytes(),0o644),
             home/MENUBAR_APP/'Contents/MacOS/PitPatMenuBar':((menubar/'Contents/MacOS/PitPatMenuBar').read_bytes(),0o755)}
    binaries={home/MENUBAR_APP/'Contents/MacOS/PitPatMenuBar',home/SAFETY_APP/'Contents/MacOS/pitpat-safety'}
    for path,(data,_) in outputs.items():
        if path not in binaries and PLACEHOLDER.search(data):raise ValueError('Unfilled placeholder in '+str(path))
    # A previous signature is replaced when apply signs again.
    for bundle in BUNDLES:
        for path in bundle_files(home,bundle):outputs.setdefault(path,(None,0o644))
    operations=[];directories=[]
    for path,(post,mode) in outputs.items():
        before=read(path)
        operations.append(dict(path=str(path),before=packed(before),before_sha256=digest(before),
                               before_mode=(path.stat().st_mode&0o777) if before is not None else None,
                               after=packed(post),after_sha256=digest(post),mode=mode))
        for parent in reversed(path.parents):
            if home in parent.parents and not os.path.lexists(parent) and str(parent) not in directories:directories.append(str(parent))
    return dict(version=1,platform='macos',home=str(home),repo=str(repo),logs=str(logs),
                id=datetime.now(ZoneInfo('America/New_York')).strftime('%Y%m%dT%H%M%S%z')+'-'+secrets.token_hex(4),
                operations=operations,directories=directories)


def validate(plan,home):
    home=Path(home).absolute()
    if plan.get('version')!=1 or plan.get('platform')!='macos' or plan.get('home')!=str(home) or plan.get('logs')!=str(home/LOGS):raise ValueError('Install manifest home/version mismatch')
    if not re.fullmatch(r'\d{8}T\d{6}[+-]\d{4}-[0-9a-f]{8}',plan.get('id','')):raise ValueError('Invalid manifest identity')
    paths=[item['path'] for item in plan['operations']]
    if len(paths)!=len(set(paths)) or not {str(home/p) for p in STATIC}<=set(paths):raise ValueError('Install manifest contains unexpected targets')
    for item in plan['operations']:
        if os.path.normpath(item['path'])!=item['path'] or not managed(home,item['path']):raise ValueError('Install manifest contains unexpected targets')
        checked(item['path'])
        for key in ('before','after'):
            if digest(unpacked(item[key]))!=item[key+'_sha256']:raise ValueError('Corrupt install payload')
        for key in ('mode','before_mode'):
            if item[key] is not None and (type(item[key]) is not int or not 0<=item[key]<=0o777):raise ValueError('Invalid install mode')
    for path in plan['directories']:
        if os.path.normpath(path)!=path or path==plan['logs'] or not any(Path(path) in Path(p).parents for p in paths) or home not in Path(path).parents:
            raise ValueError('Install manifest contains unexpected directories')


def sign(app):subprocess.run(['codesign','--force','--deep','--sign','-',str(app)],check=True,capture_output=True,timeout=60)


def apply(plan,home,manifest,signer=None):
    home=Path(home).absolute();manifest=checked(manifest)
    if signer is None:
        if not shutil.which('codesign'):raise ValueError('codesign unavailable; install the Xcode command line tools')
        signer=sign
    if manifest.exists():raise ValueError('Manifest already exists; roll it back or choose a new path: '+str(manifest))
    preflight(plan)
    for bundle in BUNDLES:bundle_files(home,bundle)
    logs=Path(plan['logs'])
    if os.path.lexists(logs):directory(logs)
    else:
        unlinked(logs.parent).mkdir(parents=True,exist_ok=True);logs.mkdir(mode=0o700);logs.chmod(0o700)
    atomic(manifest,(json.dumps(plan,indent=2)+'\n').encode(),0o600)
    unsigned=[str(home/bundle/SIGNATURE) for bundle in BUNDLES if not os.path.lexists(home/bundle/SIGNATURE)]
    for item in plan['operations']:
        path=Path(item['path']);current=digest(read(path))
        if current==item['after_sha256']:continue
        if current!=item['before_sha256']:raise ValueError('File changed during installation: '+str(path))
        atomic(path,unpacked(item['after']),item['mode'])
    # Signing changes bytes; record what is actually installed so rollback can recognize it.
    known={item['path']:item for item in plan['operations']}
    for bundle in BUNDLES:
        try:signer(home/bundle)
        except (OSError,subprocess.SubprocessError) as exc:
            raise ValueError('Signing failed after files were installed; run rollback with '+str(manifest)+': '+str(exc)) from exc
        for path in bundle_files(home,bundle):
            data=read(path);item=known.get(str(path))
            if item is None:
                item=known[str(path)]=dict(path=str(path),before=None,before_sha256=None,before_mode=None,mode=0o644)
                plan['operations'].append(item)
            item.update(after=packed(data),after_sha256=digest(data),mode=path.stat().st_mode&0o777)
    plan['directories']+=[path for path in unsigned if os.path.lexists(path)]
    atomic(manifest,(json.dumps(plan,indent=2)+'\n').encode(),0o600)


def service_states():
    states={}
    for label in LABELS:
        result=subprocess.run(['launchctl','print',f'gui/{os.getuid()}/{label}'],capture_output=True,text=True,timeout=10)
        state=re.search(r'^\s*state = (\S+)',result.stdout,re.M)
        states[label]=None if result.returncode else (state.group(1) if state else 'unknown')
    return states


def rollback(plan,home,force_while_loaded=False,services=None):
    validate(plan,home)
    if services is None:services=service_states if sys.platform=='darwin' else dict
    for label,state in services().items():
        if state=='running':raise ValueError(label+' is running; use Stop & Disconnect, then `pitpat services-stop`. No files changed.')
        if state is not None and not force_while_loaded:
            raise ValueError(label+' is still loaded; run `launchctl bootout gui/$(id -u)/'+label+'` or pass --force-while-loaded. No files changed.')
    preflight(plan)
    for item in reversed(plan['operations']):
        path=Path(item['path']);current=digest(read(path))
        if current==item['before_sha256']:continue
        if current!=item['after_sha256']:raise ValueError('File changed during rollback: '+str(path))
        atomic(path,unpacked(item['before']),item['before_mode'] if item['before_mode'] is not None else item['mode'])
    kept=[]
    for path in reversed(plan['directories']):
        path=Path(path)
        if not os.path.lexists(path):continue
        try:directory(path).rmdir()
        except OSError:kept.append(str(path))
    return kept


def describe(plan):
    lines=[]
    for item in plan['operations']:
        action='remove' if item['after'] is None else 'create' if item['before'] is None else 'unchanged' if item['before_sha256']==item['after_sha256'] else 'replace'
        lines.append(f'{action:9} {item["path"]}')
    lines+=['mkdir     '+path for path in plan['directories']]
    lines.append(('keep      ' if os.path.lexists(plan['logs']) else 'mkdir 700 ')+plan['logs'])
    lines+=['sign      '+str(Path(plan['home'])/bundle) for bundle in BUNDLES]
    return '\n'.join(lines)


def next_steps(home):
    agents=Path(home)/'Library/LaunchAgents'
    return '\n'.join(['Next steps (not run):']+[f'  launchctl bootstrap gui/$(id -u) {shlex.quote(str(agents/(label+".plist")))}' for label in LABELS]+
                     ['  open '+shlex.quote(str(Path(home)/MENUBAR_APP))])


def main():
    common=argparse.ArgumentParser(add_help=False)
    common.add_argument('--home',type=Path,default=Path.home())
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest='command',required=True)
    for name in ('plan','apply'):
        command=commands.add_parser(name,parents=[common])
        command.add_argument('--menubar-app',type=Path,help='Built PitPat.app (default: scripts/build-menubar.sh output)')
        command.add_argument('--safety-launcher',type=Path,help='Built PitPatSafety launcher (default: scripts/build-menubar.sh output)')
        if name=='apply':command.add_argument('--manifest',type=Path,required=True)
    command=commands.add_parser('rollback',parents=[common])
    command.add_argument('--manifest',type=Path,required=True);command.add_argument('--force-while-loaded',action='store_true')
    args=parser.parse_args()
    repo=Path(__file__).resolve().parent.parent
    try:
        if args.command=='plan':print(describe(plan(args.home,repo,args.menubar_app,args.safety_launcher)))
        elif args.command=='apply':
            result=plan(args.home,repo,args.menubar_app,args.safety_launcher);apply(result,args.home,args.manifest)
            print('Applied '+str(len(result['operations']))+' file operations. Manifest: '+str(args.manifest)+'\n'+next_steps(result['home']))
        else:
            kept=rollback(json.loads(checked(args.manifest).read_text()),args.home,args.force_while_loaded)
            print('Rolled back. Logs, walk history and state were kept.'+''.join('\nLeft non-empty directory: '+path for path in kept))
    except (ValueError,OSError,KeyError,TypeError,subprocess.SubprocessError) as exc:parser.exit(1,str(exc)+'\n')


if __name__=='__main__':main()
