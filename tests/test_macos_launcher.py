"""The built PitPat Safety launcher, in a throwaway bundle with a stand-in script; no Python safety process or Bluetooth."""
import ctypes
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

LAUNCHER=Path(__file__).resolve().parents[1]/'integration/macos/PitPatMenuBar/.build/PitPatSafety'


@unittest.skipUnless(sys.platform=='darwin' and LAUNCHER.is_file(),'needs macOS and scripts/build-menubar.sh')
class SafetyLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name).resolve()
        contents=self.root/'PitPat Safety.app/Contents'
        for name in ('MacOS','Resources'):(contents/name).mkdir(parents=True)
        shutil.copy(Path(__file__).resolve().parents[1]/'integration/macos/PitPat Safety.app/Contents/Info.plist',contents/'Info.plist')
        self.launcher=contents/'MacOS/pitpat-safety';shutil.copy(LAUNCHER,self.launcher)
        self.script=contents/'Resources/pitpat-safety';self.out=self.root/'out'

    def tearDown(self):self.temp.cleanup()

    def stand_in(self,body):
        self.script.write_text('#!/bin/sh\n'+body);self.script.chmod(0o755)

    def start(self,*args):
        process=subprocess.Popen([str(self.launcher),*args])
        for _ in range(100):
            if self.out.exists() and self.out.read_text().endswith('\n'):return process
            time.sleep(0.05)
        process.kill();self.fail('stand-in script did not start')

    def test_arguments_and_exit_status_pass_through(self):
        self.stand_in(f'echo "$*" > {self.out}\nexit 7\n')
        result=subprocess.run([str(self.launcher),'--a','b c'],timeout=10)
        self.assertEqual(result.returncode,7)
        self.assertEqual(self.out.read_text(),'--a b c\n')

    def test_child_is_credited_to_the_launcher(self):
        # A spawned child, not an exec, inherits the launcher's responsible process; under
        # launchd that is the launcher itself, so macOS credits the signed bundle.
        self.stand_in(f'echo $$ > {self.out}\nexec sleep 30\n')
        process=self.start()
        try:
            responsible=ctypes.CDLL(None).responsibility_get_pid_responsible_for_pid
            self.assertNotEqual(int(self.out.read_text()),process.pid)
            self.assertEqual(responsible(int(self.out.read_text())),responsible(process.pid))
        finally:process.kill();process.wait()

    def test_sigterm_reaches_the_child_and_its_exit_is_returned(self):
        self.stand_in(f'trap "exit 3" TERM\necho $$ > {self.out}\nwhile :; do sleep 0.05; done\n')
        process=self.start();process.send_signal(signal.SIGTERM)
        self.assertEqual(process.wait(timeout=10),3)

    def test_child_killed_by_a_signal_kills_the_launcher_the_same_way(self):
        self.stand_in(f'echo $$ > {self.out}\nexec sleep 30\n')
        process=self.start();os.kill(int(self.out.read_text()),signal.SIGKILL)
        self.assertEqual(process.wait(timeout=10),-signal.SIGKILL)

    def test_opened_as_an_app_opens_the_menu_bar_app_instead(self):
        # LaunchServices names app launches application.<bundle id>.…; launchd jobs get their label.
        self.stand_in(f'echo ran > {self.out}\n')
        bin_dir=self.root/'bin';bin_dir.mkdir();opened=self.root/'opened'
        (bin_dir/'open').write_text(f'#!/bin/sh\necho "$*" > {opened}\n');(bin_dir/'open').chmod(0o755)
        env=dict(os.environ,PATH=f'{bin_dir}:/usr/bin:/bin',XPC_SERVICE_NAME='application.com.gberfield.pitpat.safety.1.2')
        result=subprocess.run([str(self.launcher)],env=env,timeout=10)
        self.assertEqual(result.returncode,0)
        self.assertEqual(opened.read_text(),'-b com.gberfield.pitpat.menubar\n')
        self.assertFalse(self.out.exists())

    def test_launchd_job_still_runs_the_script(self):
        self.stand_in(f'echo ran > {self.out}\n')
        env=dict(os.environ,XPC_SERVICE_NAME='com.gberfield.pitpat.safety')
        self.assertEqual(subprocess.run([str(self.launcher)],env=env,timeout=10).returncode,0)
        self.assertEqual(self.out.read_text(),'ran\n')

    def test_missing_script_fails(self):
        result=subprocess.run([str(self.launcher)],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,1);self.assertIn('cannot start',result.stderr)


if __name__=='__main__':
    unittest.main()
