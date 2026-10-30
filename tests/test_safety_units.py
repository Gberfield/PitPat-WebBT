import unittest
from pathlib import Path
class UnitTests(unittest.TestCase):
    def test_independent_safety_unit_exists_without_stop_coupling(self):
        p=Path('integration/systemd/pitpat-safety.service')
        self.assertTrue(p.is_file(),'dedicated service missing')
        s=p.read_text();self.assertIn('Restart=no',s)
        for forbidden in ('PartOf=','BindsTo=','StopWhenUnneeded=yes','[Install]'):self.assertNotIn(forbidden,s)
        app=Path('integration/systemd/pitpat-bridge.service').read_text()
        self.assertIn('Wants=pitpat-safety.service',app)
    def test_install_plan_includes_safety_and_retains_v1_rollback(self):
        import importlib.util,tempfile,json
        spec=importlib.util.spec_from_file_location('installer',Path('scripts/install-omarchy.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
        with tempfile.TemporaryDirectory() as d:
            home=Path(d);plan=m.plan(home,Path.cwd())
            self.assertEqual(plan['version'],2)
            self.assertTrue(any(x['path'].endswith('/pitpat-safety.service') for x in plan['operations']))
            m.apply(plan,home);m.rollback(plan,home)
            old=dict(plan,version=1,operations=[x for x in plan['operations'] if not x['path'].endswith('/pitpat-safety.service')])
            old['id']=old['id'][:-1]+('a' if old['id'][-1]!='a' else 'b')
            m.validate(old,home)
    def test_missing_safety_refuses_before_touching_walk_database(self):
        import tempfile,subprocess,sys
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);state=root/'state'
            result=subprocess.run([sys.executable,'-m','bridge','--simulate','--runtime-dir',str(root/'runtime'),'--state-dir',str(state),'--port','18769'],capture_output=True,timeout=7)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(state.exists(),'failed startup touched existing walk state before safety authentication')
