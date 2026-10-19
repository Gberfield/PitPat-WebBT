import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bridge.native import NativeServer, RuntimeLock
from bridge.controller import Controller
from tests.test_bridge_controller import FakeBackend


class NativeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.runtime=Path(self.temp.name)/'pitpat'
        self.ctrl=Controller(FakeBackend())
        self.native=NativeServer(self.ctrl,self.runtime)
        await self.native.serve()
        self.writers=[]

    async def asyncTearDown(self):
        for w in self.writers: w.close(); await w.wait_closed()
        await self.native.close()
        await self.ctrl.shutdown()
        self.temp.cleanup()

    async def connect(self,kind='helper'):
        r,w=await asyncio.open_unix_connection(str(self.runtime/'control.sock'))
        self.writers.append(w)
        w.write((json.dumps(dict(v=1,op='hello',kind=kind))+'\n').encode());await w.drain()
        return r,w,json.loads(await asyncio.wait_for(r.readline(),1))

    async def request(self,r,w,op,args=None,generation=0):
        w.write((json.dumps(dict(v=1,id='test',op=op,generation=generation,args=args or {}))+'\n').encode());await w.drain()
        while True:
            m=json.loads(await asyncio.wait_for(r.readline(),1))
            if m.get('id')=='test':return m

    async def test_permissions_exclusivity_and_helper_has_no_motion(self):
        self.assertEqual(self.runtime.stat().st_mode&0o777,0o700)
        self.assertEqual((self.runtime/'control.sock').stat().st_mode&0o777,0o600)
        self.assertEqual((self.runtime/'service.lock').stat().st_mode&0o777,0o600)
        with self.assertRaises(ValueError):RuntimeLock(self.runtime)
        r,w,hello=await self.connect()
        self.assertFalse(hello['snapshot']['is_owner'])
        denied=await self.request(r,w,'discover')
        self.assertFalse(denied['ok'])
        self.assertEqual(self.ctrl.backend.writes,[])
        self.assertIsNone(self.ctrl.owner)

    async def test_peer_uid_rejection_and_bad_hello(self):
        with patch('bridge.native.peer_uid',return_value=os.getuid()+1):
            r,w=await asyncio.open_unix_connection(str(self.runtime/'control.sock'));self.writers.append(w)
            self.assertEqual(await asyncio.wait_for(r.readline(),1),b'')
        r,w=await asyncio.open_unix_connection(str(self.runtime/'control.sock'));self.writers.append(w)
        w.write(b'{"v":1,"op":"hello","kind":"browser"}\n');await w.drain()
        self.assertEqual(await asyncio.wait_for(r.readline(),1),b'')

    async def test_strict_frames_and_tray_discovery_without_connect(self):
        r,w,_=await self.connect('tray')
        for raw in (b'{"v":1,"v":1}\n',b'{"v":1,"op":"raw_write"}\n'):
            w.write(raw);await w.drain()
            self.assertFalse(json.loads(await r.readline())['ok'])
        result=await self.request(r,w,'discover')
        self.assertEqual(result['result']['devices'][0]['id'],'synthetic')
        self.assertFalse(self.ctrl.connected)
        w.write(b'x'*17000+b'\n');await w.drain()
        self.assertEqual(await asyncio.wait_for(r.readline(),1),b'')

    async def test_symlink_runtime_refused(self):
        alias=Path(self.temp.name)/'alias';alias.symlink_to(self.runtime,target_is_directory=True)
        with self.assertRaises(ValueError):RuntimeLock(alias)

class StartupTests(unittest.TestCase):
    def test_second_process_refuses_before_opening_state(self):
        import subprocess
        import sys
        import urllib.request
        import time
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory); runtime=base/'runtime'; state=base/'state'
            guard=RuntimeLock(runtime)
            try:
                run=subprocess.run([sys.executable,'-m','bridge','--simulate','--state-dir',str(state),
                                    '--runtime-dir',str(runtime),'--port','18769'],capture_output=True,timeout=5)
                self.assertNotEqual(run.returncode,0)
                self.assertIn(b'already running',run.stderr)
                self.assertFalse(state.exists())
            finally:guard.close()
