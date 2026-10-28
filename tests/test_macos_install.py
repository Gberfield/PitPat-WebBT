"""Disposable homes only: the macOS installer never touches the real home or launchd here."""
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shutil
import subprocess
import tempfile
import unittest

spec=importlib.util.spec_from_file_location('macos_installer',Path(__file__).parents[1]/'scripts/install-macos.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
REPO=Path(__file__).parents[1]
# Real signing on macOS; elsewhere there is no codesign and bundles stay unsigned.
SIGNER=None if shutil.which('codesign') else (lambda app:None)


def snapshot(root):
    return {str(p.relative_to(root)):(p.read_bytes(),p.stat().st_mode&0o777) if p.is_file() else None for p in sorted(root.rglob('*'))}


class MacInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        self.home=self.root/'home';self.home.mkdir()
        self.menubar=self.root/'build/PitPat.app'
        executable=self.menubar/'Contents/MacOS/PitPatMenuBar';executable.parent.mkdir(parents=True)
        shutil.copy(REPO/'integration/macos/PitPatMenuBar/Info.plist',self.menubar/'Contents/Info.plist')
        executable.write_text('#!/bin/sh\nexit 0\n');executable.chmod(0o755)
        (self.home/'Library/Logs').mkdir(parents=True)
        self.bin=self.home/'.local/bin';self.bin.mkdir(parents=True);(self.bin/'other').write_text('keep')
        self.manifest=self.root/'manifest.json'
        self.before=snapshot(self.home)

    def tearDown(self):self.temp.cleanup()

    def plan(self):return installer.plan(self.home,REPO,self.menubar)

    def apply(self):
        plan=self.plan();installer.apply(plan,self.home,self.manifest,SIGNER);return plan

    def rollback(self,**kwargs):
        return installer.rollback(json.loads(self.manifest.read_text()),self.home,services=kwargs.pop('services',dict),**kwargs)

    def test_plan_writes_nothing_and_fills_every_placeholder(self):
        plan=self.plan()
        self.assertEqual(snapshot(self.home),self.before)
        for item in plan['operations']:
            if not item['path'].endswith('PitPatMenuBar'):self.assertIsNone(installer.PLACEHOLDER.search(installer.unpacked(item['after'])),item['path'])
        bridge=plistlib.loads(installer.unpacked(plan['operations'][1]['after']))
        self.assertEqual(bridge['ProgramArguments'][0],str(REPO/'.venv/bin/python'))
        self.assertEqual(bridge['StandardOutPath'],str(self.home/'Library/Logs/PitPat/bridge.log'))
        safety=plistlib.loads(installer.unpacked(plan['operations'][0]['after']))
        self.assertEqual(safety['ProgramArguments'],[str(self.home/'Applications/PitPat Safety.app/Contents/MacOS/pitpat-safety')])
        self.assertIn('Next steps (not run):',installer.next_steps(self.home))

    def test_apply_creates_targets_with_modes_and_rollback_restores_exactly(self):
        self.apply()
        modes={'Library/LaunchAgents/com.gberfield.pitpat.safety.plist':0o644,'Library/LaunchAgents/com.gberfield.pitpat.bridge.plist':0o644,
               '.local/bin/pitpat':0o755,'Applications/PitPat Safety.app/Contents/Info.plist':0o644,
               'Applications/PitPat Safety.app/Contents/MacOS/pitpat-safety':0o755,
               'Applications/PitPat.app/Contents/Info.plist':0o644,'Applications/PitPat.app/Contents/MacOS/PitPatMenuBar':0o755}
        for path,mode in modes.items():self.assertEqual((self.home/path).stat().st_mode&0o777,mode,path)
        self.assertEqual((self.home/'Library/Logs/PitPat').stat().st_mode&0o777,0o700)
        self.assertEqual(self.manifest.stat().st_mode&0o777,0o600)
        self.assertIn('cd '+str(REPO)+' ',(self.home/'.local/bin/pitpat').read_text().replace("'",''))
        if SIGNER is None:
            for app in ('PitPat Safety.app','PitPat.app'):
                check=subprocess.run(['codesign','--verify','--deep','--strict',str(self.home/'Applications'/app)],capture_output=True,text=True)
                self.assertEqual(check.returncode,0,check.stderr)
            self.assertTrue((self.home/'Applications/PitPat.app/Contents/_CodeSignature/CodeResources').exists())
        state=self.home/'Library/Logs/PitPat/bridge.log';state.write_text('kept')
        walks=self.home/'.local/state/pitpat/walks.sqlite3';walks.parent.mkdir(parents=True);walks.write_bytes(b'keep records')
        self.assertEqual(self.rollback(),[])
        self.assertEqual(state.read_text(),'kept');self.assertEqual(walks.read_bytes(),b'keep records')
        for name in ('Library/LaunchAgents','Applications'):self.assertFalse((self.home/name).exists(),name)
        after=snapshot(self.home)
        for name in ('Library/Logs/PitPat','Library/Logs/PitPat/bridge.log','.local/state','.local/state/pitpat','.local/state/pitpat/walks.sqlite3'):after.pop(name)
        self.assertEqual(after,self.before)

    def test_reapply_over_previous_install_and_rollback_restores_previous_bytes(self):
        self.apply();first=snapshot(self.home)
        (self.home/'.local/bin/pitpat').write_text('#!/bin/sh\n# older helper\n')
        self.manifest,older=self.root/'second.json',(self.home/'.local/bin/pitpat').read_bytes()
        self.apply();self.rollback()
        self.assertEqual((self.home/'.local/bin/pitpat').read_bytes(),older)
        restored=snapshot(self.home);first['.local/bin/pitpat']=(older,0o755)
        self.assertEqual(restored,first)

    def test_drift_refuses_without_changing_files(self):
        stray=self.home/'Applications/PitPat.app/Contents/Resources/extra.png';stray.parent.mkdir(parents=True);stray.write_bytes(b'x')
        with self.assertRaises(ValueError):self.plan()
        stray.unlink();plan=self.plan()
        (self.home/'.local/bin/pitpat').write_text('appeared after planning')
        with self.assertRaises(ValueError):installer.apply(plan,self.home,self.manifest,SIGNER)
        self.assertFalse(self.manifest.exists());self.assertFalse((self.home/'Library/LaunchAgents').exists())
        (self.home/'.local/bin/pitpat').unlink();self.apply()
        with self.assertRaises(ValueError):installer.apply(self.plan(),self.home,self.manifest,SIGNER)
        helper=self.home/'.local/bin/pitpat';helper.write_text('user edit')
        with self.assertRaises(ValueError):self.rollback()
        self.assertEqual(helper.read_text(),'user edit')
        self.assertTrue((self.home/'Applications/PitPat.app/Contents/Info.plist').exists())

    def test_symlinks_and_forged_manifests_refuse(self):
        target=self.root/'elsewhere';target.mkdir()
        (self.home/'Applications').symlink_to(target,target_is_directory=True)
        with self.assertRaises(ValueError):self.plan()
        (self.home/'Applications').unlink();self.apply()
        manifest=json.loads(self.manifest.read_text())
        forged=json.loads(json.dumps(manifest));forged['operations'][0]['path']=str(self.home/'.zshrc')
        with self.assertRaises(ValueError):installer.rollback(forged,self.home,services=dict)
        forged=json.loads(json.dumps(manifest));forged['directories'].append(str(self.root))
        with self.assertRaises(ValueError):installer.rollback(forged,self.home,services=dict)
        forged=json.loads(json.dumps(manifest));forged['operations'][0]['after_sha256']='0'*64
        with self.assertRaises(ValueError):installer.rollback(forged,self.home,services=dict)

    def test_rollback_refuses_loaded_or_running_services(self):
        self.apply();installed=snapshot(self.home)
        with self.assertRaises(ValueError):self.rollback(services=lambda:{'com.gberfield.pitpat.bridge':'running'})
        with self.assertRaises(ValueError):self.rollback(services=lambda:{'com.gberfield.pitpat.safety':'not'})
        with self.assertRaises(ValueError):self.rollback(services=lambda:{'com.gberfield.pitpat.bridge':'running'},force_while_loaded=True)
        self.assertEqual(snapshot(self.home),installed)
        self.rollback(services=lambda:{'com.gberfield.pitpat.safety':'not'},force_while_loaded=True)
        self.assertFalse((self.home/'Applications').exists())

    def test_unbuilt_menu_bar_app_refuses(self):
        with self.assertRaises(ValueError):installer.plan(self.home,REPO,self.root/'missing.app')
