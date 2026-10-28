"""Disposable homes only: catch destructive config overwrites and stale rollbacks."""
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('installer',Path(__file__).parents[1]/'scripts/install-omarchy.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
REPO=Path(__file__).parents[1]


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.home=Path(self.temp.name)
        self.shell=self.home/'.config/omarchy/shell.json';self.shell.parent.mkdir(parents=True)
        self.shell.write_text('{"bar":{"layout":{"right":[{"id":"gabe.tray"},{"id":"keep","x":7}]}},"untouched":true}\n')
        self.bindings=self.home/'.config/hypr/bindings.lua';self.bindings.parent.mkdir(parents=True)
        self.bindings.write_text('-- custom stays\no.bind("SUPER + SHIFT + F12", "Emergency", "stop")\n')
        self.before=(self.shell.read_bytes(),self.bindings.read_bytes())

    def tearDown(self):self.temp.cleanup()

    def test_apply_reapply_and_exact_rollback_preserve_records(self):
        plan=installer.plan(self.home,REPO)
        self.assertEqual((self.shell.read_bytes(),self.bindings.read_bytes()),self.before)
        installer.apply(plan,self.home)
        after=json.loads(self.shell.read_text())
        self.assertEqual(after['bar']['layout']['right'],[{'id':'gabe.tray'},{'id':'gabe.pitpat'},{'id':'keep','x':7}])
        self.assertTrue(after['untouched'])
        self.assertIn('SUPER + SHIFT + F12',self.bindings.read_text())
        installer.apply(plan,self.home)
        self.assertEqual(self.bindings.read_text().count('SUPER + F9'),1)
        database=self.home/'.local/state/pitpat/walks.sqlite3';database.write_bytes(b'keep records')
        installer.rollback(plan,self.home)
        self.assertEqual((self.shell.read_bytes(),self.bindings.read_bytes()),self.before)
        self.assertEqual(database.read_bytes(),b'keep records')
        self.assertFalse((self.home/'.local/bin/pitpat').exists())
        backup=self.home/'.local/state/pitpat/install-backups'/plan['id']/'manifest.json'
        self.assertEqual(backup.stat().st_mode&0o777,0o600)

    def test_drift_preflight_prevents_any_install_or_rollback(self):
        plan=installer.plan(self.home,REPO);self.bindings.write_text('-- changed')
        with self.assertRaises(ValueError):installer.apply(plan,self.home)
        self.assertEqual(self.shell.read_bytes(),self.before[0])
        self.bindings.write_bytes(self.before[1]);installer.apply(plan,self.home)
        self.shell.write_text('{"new":"edit"}')
        with self.assertRaises(ValueError):installer.rollback(plan,self.home)
        self.assertTrue((self.home/'.local/bin/pitpat').exists())
        self.assertEqual(self.shell.read_text(),'{"new":"edit"}')

    def test_symlinks_and_shortcut_conflicts_refuse(self):
        for key in ('F9','F10','F11'):
            self.bindings.write_text('o.bind("SUPER + '+key+'", "Existing", "keep")')
            with self.assertRaises(ValueError):installer.plan(self.home,REPO)
        self.bindings.write_bytes(self.before[1])
        target=self.home/'elsewhere';target.mkdir()
        (self.home/'.local').symlink_to(target,target_is_directory=True)
        with self.assertRaises(ValueError):installer.plan(self.home,REPO)

    def test_forged_target_and_corrupt_payload_refuse(self):
        plan=installer.plan(self.home,REPO)
        plan['operations'][0]['path']=str(self.home/'unrelated')
        with self.assertRaises(ValueError):installer.apply(plan,self.home)

    @unittest.skipUnless(shutil.which('systemd-analyze'),'systemd-analyze unavailable')
    def test_generated_unit_is_accepted_by_actual_systemd_parser(self):
        import subprocess
        plan=installer.plan(self.home,REPO)
        unit=next(o for o in plan['operations'] if o['path'].endswith('pitpat-bridge.service'))
        path=self.home/'candidate.service';path.write_bytes(installer.unpacked(unit['after']))
        check=subprocess.run(['systemd-analyze','--user','verify',str(path)],capture_output=True,text=True)
        self.assertEqual(check.returncode,0,check.stderr)
