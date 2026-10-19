import QtQuick
import Quickshell
ShellRoot {
    id:root
    Service {id:svc}
    Component.onCompleted: {
        svc.registerView("first");svc.registerView("second")
    }
    property int phase:0
    Timer {
        interval:100;repeat:true;running:true
        onTriggered: {
            if(root.phase===0 && svc.authorized) {svc.discover();root.phase=1}
            else if(root.phase===1 && svc.devices.length) {svc.connectDevice(svc.devices[0].id);root.phase=2}
            else if(root.phase===2 && svc.model.canStartPause) {svc.startPause();root.phase=3}
            else if(root.phase===3 && svc.model.state==="Walking") {
                svc.unregisterView("first")
                if(!svc.isOwner||svc.viewCount!==1) {console.error("OWNER LOST EARLY");Qt.quit();return}
                console.log("TWO VIEWS SHARE OWNER")
                svc.unregisterView("second");root.phase=4
            }
            else if(root.phase===4 && !svc.authorized) {console.log("LAST VIEW RELEASED");Qt.quit()}
        }
    }
    Timer {interval:10000;running:true;onTriggered:{console.error("TEST TIMEOUT phase="+root.phase+" "+svc.errorText);Qt.quit()}}
}
