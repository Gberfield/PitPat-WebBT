import QtQuick
import Quickshell
import Quickshell.Io
import "Model.js" as Model

Item {
    id: root
    property var shell: null
    property var snapshot: ({available:false, connected:false})
    property var views: ({})
    property var pending: ({})
    property var devices: []
    readonly property var channel: channelLoader.item
    property int serial: 0
    property int generation: 0
    property int sequence: 0
    property bool authorized: false
    property bool releasing: false
    property string warning: ""
    property string errorText: ""
    readonly property bool isOwner: authorized && snapshot.is_owner === true
    readonly property var model: Model.view(snapshot,isOwner)
    readonly property string runtimePath: Quickshell.env("PITPAT_RUNTIME_DIR") || (Quickshell.env("XDG_RUNTIME_DIR") + "/pitpat")
    readonly property int viewCount: Object.keys(views).length

    function registerView(key) {
        var next=Object.assign({},views); next[key]=true; views=next
        ensureSocket()
    }
    function unregisterView(key) {
        var next=Object.assign({},views); delete next[key]; views=next
        if (viewCount===0) {
            if (isOwner) { releasing=true; request("release",{},function(){root.finishRelease()}) }
            else if(channel) channel.connected=false
        }
    }
    function ensureSocket() {
        if (!channel) channelLoader.active=true
        else if (!channel.connected) channel.connected=true
    }
    function finishRelease() {
        releasing=false
        if (viewCount===0 && channel) channel.connected=false
    }
    function send(value) { channel.write(JSON.stringify(value)+"\n"); channel.flush() }
    function request(op,args,callback) {
        if (!authorized || !channel) { errorText="Local bridge unavailable. Open Controls to start it."; return false }
        if (Object.keys(pending).length>=8) { errorText="Too many pending requests"; return false }
        var id=String(++serial), next=Object.assign({},pending)
        next[id]={op:op, generation:generation, at:Date.now(), callback:callback}
        pending=next
        send({v:1,id:id,op:op,generation:generation,args:args||{}})
        return true
    }
    function acceptSnapshot(value) {
        if (value) snapshot=Object.assign({},value,{available:true,simulator:snapshot.simulator===true})
    }
    function receive(line) {
        if (line.length>65536) { channel.connected=false; return }
        var msg
        try { msg=JSON.parse(line) } catch(e) { channel.connected=false; return }
        if (msg.v!==1) { channel.connected=false; return }
        if (msg.event==="authorized") {
            authorized=true; generation=msg.generation; sequence=0
            snapshot=Object.assign({},msg.snapshot,{available:true,simulator:msg.simulator===true}); return
        }
        if (!authorized) { channel.connected=false; return }
        if (msg.id) {
            var item=pending[msg.id]; if (!item) return
            var next=Object.assign({},pending); delete next[msg.id]; pending=next
            var changes=["connect","take_control","release","stop_disconnect","observe"]
            if (msg.generation<generation || msg.generation<item.generation ||
                (msg.generation!==item.generation && changes.indexOf(item.op)<0)) {
                errorText="Obsolete response discarded"; return
            }
            generation=msg.generation
            if (!msg.ok) errorText=msg.error||"Request failed"
            else {
                errorText=""
                if (msg.result?.devices) devices=msg.result.devices
                if (["observe","take_control","resolve_session"].indexOf(item.op)>=0) acceptSnapshot(msg.result)
            }
            if (item.callback) item.callback(msg)
            return
        }
        if (msg.generation<generation || msg.seq<=sequence) return
        generation=msg.generation; sequence=msg.seq
        acceptSnapshot(msg.snapshot)
        if (msg.event==="safety" || msg.event==="lost") warning=msg.data.message||"Motion unconfirmed"
        if (msg.event==="storage_fault") errorText=msg.data.message
    }
    function discover() { request("discover",{}) }
    function connectDevice(id) { request("connect",{device_id:id}) }
    function recover() { request("connect",{recover:true}) }
    function takeControl() { if(model.canTakeControl) request("take_control",{}) }
    function startPause() {
        if (!model.canStartPause) { errorText="Take control of a healthy, stopped connection first."; return false }
        return request(model.startText==="Pause"?"pause":"start",{speed:snapshot.target_speed||1000})
    }
    function stop() { if (!model.canStop) {errorText="No Bluetooth connection; use the physical stop control if needed."; return false} return request("stop",{}) }
    function stopDisconnect() { return request("stop_disconnect",{}) }
    function release() { return request("release",{}) }
    function setTargetMph(value) { if(model.canAdjust) request("set_speed",{speed:Model.targetUnits(value)}) }
    function resolve(choice) { if(isOwner&&snapshot.session) request("resolve_session",{session_id:snapshot.session.sessionId,choice:choice}) }
    Loader {id:channelLoader;active:false;sourceComponent:socketComponent}
    Component {
      id:socketComponent
      Socket {
        path: root.runtimePath+"/control.sock"
        Component.onCompleted: Qt.callLater(function(){if(root.viewCount>0 && root.channel) root.channel.connected=true})
        onError: error => {
            // Quickshell 0.3.1 retains the failed QLocalSocket and cannot retry
            // setConnected(true). Recreate this socket after its callback returns.
            if (!connected) Qt.callLater(function(){channelLoader.active=false})
            else connected=false
        }
        parser: SplitParser { onRead: data => root.receive(data) }
        onConnectionStateChanged: {
            if (connected) root.send({v:1,op:"hello",kind:"tray"})
            else {
                if (root.authorized && root.snapshot.connected) root.warning="Controller connection lost; belt state is unconfirmed. Use the physical stop control."
                root.authorized=false; root.pending=({}); root.releasing=false
                root.snapshot=({available:false,connected:false,simulator:root.snapshot.simulator})
            }
        }
    }
    }
    Timer {
        interval:1000; repeat:true; running:root.viewCount>0 || root.releasing
        onTriggered: {
            if ((!channel || !channel.connected) && root.viewCount>0) root.ensureSocket()
            if (root.isOwner && !root.releasing) root.request("renew",{})
            var now=Date.now()
            for (var id in root.pending) {
                var item=root.pending[id]
                if(now-item.at>(item.op==="connect"?26000:8000)) {
                    root.errorText="Request timed out; motion unconfirmed. Use the physical stop control."
                    channel.connected=false; root.finishRelease(); break
                }
            }
        }
    }
    IpcHandler {
        target:"gabe.pitpat"
        function startPause(): string { if(!root.startPause()) return "ERROR: "+root.errorText; return "Requested" }
        function stop(): string { if(!root.stop()) return "ERROR: "+root.errorText; return "Requested" }
        function status(): string { return JSON.stringify({snapshot:root.snapshot,views:root.viewCount,authorized:root.authorized,socketConnected:root.channel?.connected===true,runtimePath:root.runtimePath,error:root.errorText,warning:root.warning}) }
    }
}
