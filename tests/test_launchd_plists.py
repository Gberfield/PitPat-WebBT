from pathlib import Path
import plistlib
import shutil
import subprocess
import unittest

LAUNCHD = Path(__file__).resolve().parents[1]/'integration/launchd'


class LaunchdTemplateTests(unittest.TestCase):
    def load(self, name):
        return plistlib.loads((LAUNCHD/f'com.gberfield.pitpat.{name}.plist').read_bytes())

    def test_agents_start_on_demand_only_with_private_umask(self):
        for name, timeout in (('safety', 10), ('bridge', 35)):
            agent = self.load(name)
            self.assertEqual(agent['Label'], f'com.gberfield.pitpat.{name}')
            self.assertIs(agent['RunAtLoad'], False)
            self.assertNotIn('KeepAlive', agent)
            self.assertEqual(agent['Umask'], 0o077)
            self.assertEqual(agent['ExitTimeOut'], timeout)
            self.assertEqual(agent['ProcessType'], 'Interactive')
            self.assertEqual(agent['StandardErrorPath'], f'@LOGS@/{name}.log')

    def test_program_arguments(self):
        self.assertEqual(self.load('safety')['ProgramArguments'], ['@SAFETY_APP_EXECUTABLE@'])
        self.assertEqual(self.load('bridge')['ProgramArguments'], ['@PYTHON@', '-u', '-m', 'bridge', '--port', '8766'])

    @unittest.skipUnless(shutil.which('plutil'), 'plutil unavailable')
    def test_templates_pass_plutil_lint(self):
        subprocess.run(['plutil', '-lint', *map(str, sorted(LAUNCHD.glob('*.plist')))], check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
