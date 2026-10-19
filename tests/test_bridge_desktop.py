import unittest
from unittest.mock import patch
from bridge.desktop import main


class DesktopTests(unittest.TestCase):
    def test_start_pause_only_calls_existing_shell_and_never_starts_bridge(self):
        with patch('bridge.desktop.subprocess.run') as run:
            run.return_value.returncode=0
            self.assertEqual(main(['start-pause']),0)
            self.assertEqual(run.call_args.args[0],['omarchy-shell','gabe.pitpat','startPause'])
            self.assertEqual(run.call_count,1)

    def test_missing_shell_is_visible_failure_not_bluetooth_fallback(self):
        with patch('bridge.desktop.subprocess.run',side_effect=FileNotFoundError),patch('sys.stderr') as stderr:
            self.assertEqual(main(['start-pause']),1)
            self.assertTrue(stderr.write.called)

    def test_controls_starts_service_and_opens_plugin_only(self):
        with patch('bridge.desktop.subprocess.run') as run:
            run.return_value.returncode=0
            self.assertEqual(main(['controls']),0)
            self.assertEqual([c.args[0] for c in run.call_args_list],[
                ['systemctl','--user','start','pitpat-bridge.service'],['omarchy-shell','shell','toggle','gabe.pitpat']])

class SafetyHelperRoutingTests(unittest.TestCase):
    def test_stop_uses_safety_socket_not_application(self):
        import bridge.desktop as desktop
        self.assertTrue(hasattr(desktop,'safety_stop'),'independent emergency Stop missing')
        with patch('bridge.desktop.safety_stop') as stop,patch('bridge.desktop.subprocess.run') as run:
            stop.return_value=None
            self.assertEqual(desktop.main(['stop']),0)
            self.assertTrue(stop.called);run.assert_not_called()
    def test_unavailable_safety_reports_physical_stop_guidance(self):
        import io,contextlib
        from unittest.mock import AsyncMock
        import bridge.desktop as desktop
        err=io.StringIO()
        with patch('bridge.desktop.asyncio.open_unix_connection',new=AsyncMock(side_effect=FileNotFoundError('synthetic missing safety'))),contextlib.redirect_stderr(err):
            self.assertEqual(desktop.main(['stop']),1)
        self.assertIn('Stop unconfirmed',err.getvalue())
        self.assertIn('physical stop',err.getvalue())
