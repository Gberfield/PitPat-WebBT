import os
from pathlib import Path
import plistlib
import unittest

APP = Path(__file__).resolve().parents[1]/'integration/macos/PitPat Safety.app/Contents'


class SafetyBundleTests(unittest.TestCase):
    def test_info_plist_attributes_bluetooth_to_hidden_safety_app(self):
        info = plistlib.loads((APP/'Info.plist').read_bytes())
        self.assertEqual({k: info[k] for k in ('CFBundleIdentifier', 'CFBundleExecutable', 'CFBundlePackageType', 'LSUIElement', 'LSMinimumSystemVersion')},
                         dict(CFBundleIdentifier='com.gberfield.pitpat.safety', CFBundleExecutable='pitpat-safety',
                              CFBundlePackageType='APPL', LSUIElement=True, LSMinimumSystemVersion='13.0'))
        self.assertIn('Stop', info['NSBluetoothAlwaysUsageDescription'])

    def test_launched_script_is_placeholder_template_for_safety_process_only(self):
        script = APP/'Resources/pitpat-safety'
        self.assertTrue(os.access(script, os.X_OK))
        text = script.read_text()
        self.assertIn('cd @REPO_SHELL@ || exit 1', text)
        self.assertIn('exec @PYTHON_SHELL@ -m bridge.safety_main "$@"', text)
        self.assertNotIn('--simulate', text)


if __name__ == '__main__':
    unittest.main()
