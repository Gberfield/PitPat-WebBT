"""Private peer-authenticated Unix IPC. Never owns a second BLE connection."""
import asyncio
import contextlib
import fcntl
import json
import os
from pathlib import Path
import secrets
import socket
import stat
import struct

from .messages import load_json, validate_request
from .store import private_directory


def peer_uid(sock):
    return struct.unpack('3i', sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]


class RuntimeLock:
    def __init__(self, runtime_dir, name='service.lock'):
        self.path = private_directory(runtime_dir)
        if name not in ('service.lock','bridge.lock'):raise ValueError('Invalid lock name')
        lock = self.path / name
        if lock.is_symlink(): raise ValueError('Runtime lock must not be a symlink')
        self.fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        info = os.fstat(self.fd)
        if info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            os.close(self.fd)
            raise ValueError('Invalid runtime lock')
        try: fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(self.fd)
            raise ValueError('Another PitPat bridge is already running') from None
        os.fchmod(self.fd, 0o600)

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


class NativeServer:
    def __init__(self, controller, runtime_dir, guard=None, simulator=False):
        self.controller, self.runtime = controller, Path(runtime_dir)
        self.guard = guard
        self.owns_guard = guard is None
        self.simulator = simulator
        self.server = None
        self.writers = set()
        self.tasks = set()
        self.path = self.runtime / 'control.sock'
        self.inode = None

    async def serve(self):
        if self.guard is None: self.guard = RuntimeLock(self.runtime)
        try:
            if self.path.is_symlink(): raise ValueError('Native socket must not be a symlink')
            if self.path.exists():
                info = self.path.stat()
                if info.st_uid != os.getuid() or not stat.S_ISSOCK(info.st_mode):
                    raise ValueError('Invalid existing socket')
                probe = socket.socket(socket.AF_UNIX)
                try:
                    probe.connect(str(self.path))
                except ConnectionRefusedError:
                    self.path.unlink()  # Our exclusive lock + refused listener prove stale state.
                else: raise ValueError('Native socket already has a listener')
                finally: probe.close()
            self.server = await asyncio.start_unix_server(self.accept, path=str(self.path), limit=16384)
            self.path.chmod(0o600)
            self.inode = self.path.stat().st_ino
        except BaseException:
            if self.owns_guard: self.guard.close(); self.guard = None
            raise

    async def accept(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        ctrl = self.controller
        cid = secrets.token_hex(16)
        queue = asyncio.Queue(maxsize=64)
        pending = set()
        unsubscribe = lambda: None
        sender = None
        overflow = False
        self.writers.add(writer)

        def send(message):
            nonlocal overflow
            if overflow or writer.is_closing(): return
            try: queue.put_nowait(message)
            except asyncio.QueueFull:
                overflow = True
                writer.close()
                ctrl.spawn(ctrl.client_lost(cid))

        def relay(message): send(dict(message, snapshot=ctrl.snapshot_for(cid)))

        async def output():
            try:
                while True:
                    message = await queue.get()
                    writer.write((json.dumps(message, allow_nan=False) + '\n').encode())
                    await asyncio.wait_for(writer.drain(), 2)
            except (OSError, TimeoutError, ValueError):
                writer.close()
                ctrl.spawn(ctrl.client_lost(cid))

        async def command(data):
            try:
                result = await ctrl.dispatch(cid, data)
                send(dict(v=1, id=data['id'], generation=ctrl.generation, ok=True, result=result))
            except Exception as exc:
                send(dict(v=1, id=data['id'], generation=ctrl.generation, ok=False,
                          error=str(exc) if isinstance(exc, ValueError) else 'Local operation failed'))

        try:
            if len(self.writers) > 16 or peer_uid(writer.get_extra_info('socket')) != os.getuid(): return
            first = await asyncio.wait_for(reader.readline(), 3)
            data = load_json(first)
            if (not isinstance(data, dict) or set(data) != {'v', 'op', 'kind'}
                    or type(data['v']) is not int or data['v'] != 1 or data['op'] != 'hello'
                    or data['kind'] not in ('tray', 'helper')): return
            ctrl.register_client(cid, data['kind'])
            send(dict(v=1, event='authorized', generation=ctrl.generation, simulator=self.simulator,
                      snapshot=ctrl.snapshot_for(cid)))
            sender = asyncio.create_task(output())
            unsubscribe = ctrl.subscribe(relay)
            while True:
                line = await reader.readline()
                if not line: break
                try:
                    data = load_json(line)
                    validate_request(data)
                    if len(pending) >= 8: raise ValueError('Too many pending requests')
                except (ValueError, TypeError, RecursionError):
                    send(dict(v=1, ok=False, error='Invalid or excessive request'))
                    continue
                command_task = asyncio.create_task(command(data))
                pending.add(command_task)
                command_task.add_done_callback(pending.discard)
        except (ValueError, TypeError, RecursionError, TimeoutError, OSError): pass
        finally:
            unsubscribe()
            await ctrl.unregister_client(cid)
            if pending: await asyncio.gather(*pending, return_exceptions=True)
            if sender:
                sender.cancel()
                await asyncio.gather(sender, return_exceptions=True)
            writer.close()
            with contextlib.suppress(OSError): await writer.wait_closed()
            self.writers.discard(writer)
            self.tasks.discard(task)

    async def close(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        for writer in tuple(self.writers): writer.close()
        await asyncio.gather(*tuple(self.tasks), return_exceptions=True)
        if self.inode is not None and self.path.exists() and self.path.stat().st_ino == self.inode:
            self.path.unlink()
        if self.owns_guard and self.guard: self.guard.close()
