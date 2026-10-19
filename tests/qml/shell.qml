import QtQuick
import Quickshell
ShellRoot {
    id:root
    Service {id:svc}
    Component.onCompleted: {svc.registerView("first");svc.registerView("second")}
    property int phase:0
    Timer {
        interval:100;repeat:true;running:true
        onTriggered: {
            if(root.phase===0 && svc.authorized) {svc.discover();root.phase=1}
            else if(root.phase===1 && svc.devices.length) {svc.connectDevice(svc.devices[0].id);root.phase=2}
            else if(root.phase===2 && svc.model.canStartPause) {svc.startPause();root.phase=3}
            else if(root.phase===3 && svc.model.state==="Walking") {
                // Test-only loss of owner renewals: keep IPC connected, stop its timer.
                svc.views=({});root.phase=4
            }
            else if(root.phase===4 && svc.snapshot.fault_id && svc.snapshot.metrics?.speed_raw===0) {
                svc.registerView("first");svc.registerView("second");svc.recover();root.phase=5
            }
            else if(root.phase===5 && svc.snapshot.is_recovery_claimant) {
                if(svc.snapshot.session?.status==="interrupted") svc.resolve("new")
                root.phase=6
            }
            else if(root.phase===6 && svc.snapshot.is_recovery_claimant && svc.snapshot.session?.status!=="interrupted") {
                svc.acknowledgeRecovery();root.phase=7
            }
            else if(root.phase===7 && svc.model.canStartPause && !svc.snapshot.fault_id) {
                if(svc.snapshot.metrics?.speed_raw!==0) {console.error("RECOVERY STARTED MOTION");Qt.quit();return}
                console.log("RECOVERY ACK WITHOUT START");svc.startPause();root.phase=8
            }
            else if(root.phase===8 && svc.model.state==="Walking") {
                svc.unregisterView("first")
                if(!svc.isOwner||svc.viewCount!==1) {console.error("OWNER LOST EARLY");Qt.quit();return}
                console.log("TWO VIEWS SHARE OWNER")
                svc.unregisterView("second");root.phase=9
            }
            else if(root.phase===9 && !svc.authorized) {console.log("LAST VIEW RELEASED");Qt.quit()}
        }
    }
    Timer {interval:30000;running:true;onTriggered:{console.error("TEST TIMEOUT phase="+root.phase+" "+svc.errorText);Qt.quit()}}
}
