from pathlib import Path
import subprocess
import sys
import unittest

REPO=Path(__file__).resolve().parents[1]
PROBE='''
import importlib,pkgutil,sys,bridge
for m in pkgutil.iter_modules(bridge.__path__):
    if m.name!='backends':importlib.import_module('bridge.'+m.name)
print('bleak' in sys.modules)
'''


class NoBluetoothImportTests(unittest.TestCase):
    def test_bridge_modules_do_not_import_bleak(self):
        # Fresh interpreter: other tests in this process may load the backend.
        result=subprocess.run([sys.executable,'-c',PROBE],cwd=REPO,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),'False')


if __name__=='__main__':
    unittest.main()
