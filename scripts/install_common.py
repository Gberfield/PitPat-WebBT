"""Platform-neutral installer primitives shared by install-omarchy.py and install-macos.py.

Standard library only. Every target is a regular user-owned file reached without
untrusted symlinks; every write is an fsynced atomic replace.
"""
import base64
import hashlib
import os
from pathlib import Path
import sys
import tempfile


# Copy of bridge/platform_paths.py; the installers import only the standard library.
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
