import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from bridge import platform_paths as pp
from bridge.store import private_directory


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

    @unittest.skipUnless(pp.DARWIN,'macOS system links')
    def test_macos_system_links_are_trusted(self):
        for name in ('/var','/tmp','/etc'):self.assertTrue(pp.trusted_system_link(Path(name)))

    def test_linux_trusts_no_links(self):
        with patch.object(pp,'SYSTEM_LINKS',{}):self.assertFalse(pp.trusted_system_link(Path('/var')))

    def test_user_symlink_is_never_trusted(self):
        with tempfile.TemporaryDirectory() as root:
            link=Path(root)/'var';link.symlink_to('private/var')
            self.assertFalse(pp.trusted_system_link(link))
            with self.assertRaisesRegex(ValueError,'symlink'):private_directory(link/'x')

    def test_private_directory_under_default_tempdir(self):
        with tempfile.TemporaryDirectory() as root:
            path=private_directory(Path(root)/'x')
            self.assertTrue(path.is_dir());self.assertEqual(path.stat().st_mode&0o777,0o700)

    def test_check_socket_path_length(self):
        short=Path('/tmp/s.sock');self.assertEqual(pp.check_socket_path(short),short)
        with self.assertRaisesRegex(ValueError,'too long'):pp.check_socket_path(Path('/'+'a'*200))


if __name__=='__main__':
    unittest.main()
