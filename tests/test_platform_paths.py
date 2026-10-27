import os
from pathlib import Path
import socket
import unittest
from unittest.mock import patch
from bridge import platform_paths as pp


class PlatformPathTests(unittest.TestCase):
    def test_peer_uid_is_current_user_on_both_ends(self):
        a,b=socket.socketpair(socket.AF_UNIX)
        with a,b:
            self.assertEqual(pp.peer_uid(a),os.getuid());self.assertEqual(pp.peer_uid(b),os.getuid())

    def test_boot_seconds_is_float_and_non_decreasing(self):
        first=pp.boot_seconds();second=pp.boot_seconds()
        self.assertIsInstance(first,float);self.assertLessEqual(first,second)

    def test_darwin_runtime_dir(self):
        with patch.object(pp,'DARWIN',True),patch.dict(os.environ,{},clear=False):
            os.environ.pop('PITPAT_RUNTIME_ROOT',None)
            self.assertEqual(pp.runtime_dir(False),Path.home()/'Library/Application Support/PitPat/run/pitpat')
            self.assertEqual(pp.state_dir(),Path.home()/'Library/Application Support/PitPat/state')

    def test_linux_runtime_and_state_dirs(self):
        with patch.object(pp,'DARWIN',False),patch.dict(os.environ,{'XDG_RUNTIME_DIR':'/run/user/1000','XDG_STATE_HOME':'/s'}):
            os.environ.pop('PITPAT_RUNTIME_ROOT',None)
            self.assertEqual(pp.runtime_dir(False),Path('/run/user/1000/pitpat'))
            self.assertEqual(pp.state_dir(),Path('/s/pitpat'))

    def test_override_wins_on_both_platforms(self):
        for darwin in (True,False):
            with patch.object(pp,'DARWIN',darwin),patch.dict(os.environ,{'PITPAT_RUNTIME_ROOT':'/x','XDG_RUNTIME_DIR':'/run/user/1000'}):
                self.assertEqual(pp.runtime_dir(False),Path('/x/pitpat'))

    def test_simulator_runtime_name(self):
        for darwin in (True,False):
            with patch.object(pp,'DARWIN',darwin):
                self.assertEqual(pp.runtime_dir(True).name,'pitpat-simulator')

    def test_open_url_command(self):
        url='http://127.0.0.1:8766/'
        with patch.object(pp,'DARWIN',True):self.assertEqual(pp.open_url_command(url),['open',url])
        with patch.object(pp,'DARWIN',False):self.assertEqual(pp.open_url_command(url),['xdg-open',url])


if __name__=='__main__':
    unittest.main()
