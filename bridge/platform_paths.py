"""The only module that knows which operating system it runs on."""
import os,socket,struct,sys,time
from pathlib import Path

DARWIN=sys.platform=='darwin'
SUN_PATH_MAX=104 if DARWIN else 108

def boot_seconds():
    # Both clocks keep counting while the host sleeps.
    return time.clock_gettime(time.CLOCK_MONOTONIC if DARWIN else time.CLOCK_BOOTTIME)

def peer_uid(sock):
    if DARWIN:
        raw=sock.getsockopt(0,socket.LOCAL_PEERCRED,struct.calcsize('IIh16I'))
        version,uid=struct.unpack('IIh16I',raw)[:2]
        if version!=0:raise ValueError('Unsupported peer credentials')
        return uid
    return struct.unpack('3i',sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))[1]

def app_support():
    return Path.home()/'Library'/'Application Support'/'PitPat'

def runtime_root():
    override=os.environ.get('PITPAT_RUNTIME_ROOT')
    if override:return Path(override)
    if DARWIN:return app_support()/'run'
    return Path(os.environ.get('XDG_RUNTIME_DIR',f'/run/user/{os.getuid()}'))

def runtime_dir(simulate=False):
    name='pitpat-simulator' if simulate else 'pitpat'
    return runtime_root()/name

def state_dir():
    if DARWIN:return app_support()/'state'
    return Path(os.environ.get('XDG_STATE_HOME',str(Path.home()/'.local/state')))/'pitpat'

def open_url_command(url):
    return ['open',url] if DARWIN else ['xdg-open',url]
