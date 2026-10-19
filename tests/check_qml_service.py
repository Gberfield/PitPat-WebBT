"""Installed Quickshell integration check; offscreen, synthetic, disposable home.

Run explicitly with the project interpreter. Tests service startup before the
backend, two views/one lease, then last-view confirmed Stop & Release.
"""
import os
import hashlib
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

REPO=Path(__file__).resolve().parents[1]


def main():
    with tempfile.TemporaryDirectory(prefix='pitpat-qml-') as directory:
        root=Path(directory);runtime=root/'runtime';runtime.mkdir(mode=0o700)
        qml=root/'qml';qml.mkdir()
        source=REPO/'integration/omarchy/gabe.pitpat/Service.qml'
        service_type='ServiceH'+hashlib.sha256(source.read_bytes()).hexdigest()[:12].upper()
        (qml/(service_type+'.qml')).symlink_to(source)
        (qml/'Model.js').symlink_to(REPO/'integration/omarchy/gabe.pitpat/Model.js')
        (qml/'shell.qml').write_text((REPO/'tests/qml/shell.qml').read_text().replace('Service {id:svc}',service_type+' {id:svc}'))
        env=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_QPA_PLATFORMTHEME='basic',QT_QUICK_CONTROLS_STYLE='Basic',
                 QT_QUICK_BACKEND='software',XDG_RUNTIME_DIR=str(runtime),XDG_STATE_HOME=str(root/'state'),
                 XDG_CONFIG_HOME=str(root/'config'),HOME=str(root),PITPAT_RUNTIME_DIR=str(runtime/'sim'))
        for key in ('DISPLAY','WAYLAND_DISPLAY','HYPRLAND_INSTANCE_SIGNATURE','DBUS_SESSION_BUS_ADDRESS'):env.pop(key,None)
        qt=subprocess.Popen(['quickshell','--no-color','-p',str(qml)],env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        bridge=None
        try:
            time.sleep(.8)  # The initial socket attempt must fail before service starts.
            bridge=subprocess.Popen([sys.executable,'-u','-m','bridge','--simulate','--port','18768','--state-dir',str(root/'state/sim'),
                                     '--runtime-dir',str(runtime/'sim')],cwd=REPO,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,env=env)
            output=qt.communicate(timeout=15)[0]
            print(output)
            if any(word in output for word in ('TypeError:','ReferenceError:','Unable to assign')) or qt.returncode or 'TEST TIMEOUT' in output or 'LAST VIEW RELEASED' not in output or 'TWO VIEWS SHARE OWNER' not in output:return 1
            return 0
        finally:
            if qt.poll() is None:qt.terminate();qt.communicate(timeout=5)
            if bridge:
                if bridge.poll() is None:bridge.send_signal(signal.SIGTERM)
                bridge.communicate(timeout=10)


if __name__=='__main__':raise SystemExit(main())
