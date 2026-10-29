import contextlib
import io
import unittest
from unittest.mock import patch
from bridge.desktop import main


@patch('bridge.desktop.DARWIN',False)
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

class PlatformRoutingTests(unittest.TestCase):
    def commands(self,darwin,operation):
        with patch('bridge.desktop.DARWIN',darwin),patch('bridge.platform_paths.DARWIN',darwin),patch('bridge.desktop.UID',501),\
             patch('bridge.desktop.subprocess.run') as run,contextlib.redirect_stdout(io.StringIO()):
            run.return_value.returncode=0;run.return_value.stdout=''
            self.assertEqual(main([operation]),0)
            return [c.args[0] for c in run.call_args_list]
    def test_linux_commands_are_unchanged(self):
        self.assertEqual(self.commands(False,'controls'),[['systemctl','--user','start','pitpat-bridge.service'],['omarchy-shell','shell','toggle','gabe.pitpat']])
        self.assertEqual(self.commands(False,'start-pause'),[['omarchy-shell','gabe.pitpat','startPause']])
        self.assertEqual(self.commands(False,'dashboard'),[['xdg-open','http://127.0.0.1:8766/']])
        self.assertEqual(self.commands(False,'history'),[['xdg-open','http://127.0.0.1:8766/#history-panel']])
        self.assertEqual(self.commands(False,'services-stop'),[['systemctl','--user','stop','pitpat-bridge.service'],['systemctl','--user','stop','pitpat-safety.service']])
    def test_macos_commands_use_launchd_and_menu_bar_app(self):
        self.assertEqual(self.commands(True,'controls'),[
            ['launchctl','kickstart','gui/501/com.gberfield.pitpat.safety'],['launchctl','kickstart','gui/501/com.gberfield.pitpat.bridge'],
            ['open','-b','com.gberfield.pitpat.menubar']])
        self.assertEqual(self.commands(True,'start-pause'),[['open','-g','pitpat://start-pause']])
        self.assertEqual(self.commands(True,'dashboard'),[['open','http://127.0.0.1:8766/']])
        self.assertEqual(self.commands(True,'history'),[['open','http://127.0.0.1:8766/#history-panel']])
        self.assertEqual(self.commands(True,'services-stop'),[
            ['launchctl','kill','SIGTERM','gui/501/com.gberfield.pitpat.bridge'],['launchctl','kill','SIGTERM','gui/501/com.gberfield.pitpat.safety']])
    def test_macos_services_stop_treats_not_running_as_stopped(self):
        from subprocess import CompletedProcess
        idle=CompletedProcess([],3,'','No process to signal.')
        with patch('bridge.desktop.DARWIN',True),patch('bridge.desktop.subprocess.run',return_value=idle) as run,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(['services-stop']),0)
            self.assertEqual(run.call_count,2)
        failed=CompletedProcess([],113,'','Could not find service')
        with patch('bridge.desktop.DARWIN',True),patch('bridge.desktop.subprocess.run',return_value=failed),contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(main(['services-stop']),1)
        self.assertIn('Could not find service',err.getvalue())
    def test_stop_failure_prints_the_guidance_once(self):
        for error,expected in ((ValueError('Stop unconfirmed. Use the physical stop control.'),'PitPat: Stop unconfirmed. Use the physical stop control.\n'),
                               (FileNotFoundError('no socket'),'PitPat: Stop unconfirmed. Use the physical stop control. no socket\n')):
            with patch('bridge.desktop.safety_stop',side_effect=error),patch('sys.stderr',new_callable=io.StringIO) as err:
                self.assertEqual(main(['stop']),1)
            self.assertEqual(err.getvalue(),expected)

    def test_macos_stop_still_goes_straight_to_safety_socket(self):
        with patch('bridge.desktop.DARWIN',True),patch('bridge.desktop.safety_stop') as stop,patch('bridge.desktop.subprocess.run') as run:
            stop.return_value=None
            self.assertEqual(main(['stop']),0)
            self.assertTrue(stop.called);run.assert_not_called()

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
