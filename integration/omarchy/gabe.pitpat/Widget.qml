import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as Controls
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
    id: root
    moduleName:"gabe.pitpat"
    manageIpc:false
    property var service: bar?.shell?.serviceFor("gabe.pitpat") ?? null
    property string instanceKey: String(Date.now())+"-"+Math.random()
    readonly property var state: service?.model ?? ({label:"Service unavailable",owner:"No motion controller",speed:"—",distance:"—",calories:"—",steps:"—",duration:"—",target:"0.62"})
    property var registeredService:null
    implicitWidth:button.implicitWidth
    implicitHeight:button.implicitHeight
    function register() {
        if (registeredService===service) return
        if (registeredService) registeredService.unregisterView(instanceKey)
        registeredService=service
        if (service) service.registerView(instanceKey)
    }
    onServiceChanged: register()
    Component.onCompleted: register()
    Component.onDestruction: if(registeredService) registeredService.unregisterView(instanceKey)
    Process { id: launch }
    function openPage(which) { if(!launch.running) {launch.command=["pitpat",which];launch.running=true} }
    WidgetButton {
        id:button;anchors.fill:parent;bar:root.bar
        text:"󰿎 " + (root.service?.snapshot.simulator ? "SIM " : "") + (root.state.state==="Walking"?root.state.speed:"Walk")
        active:root.state.state==="Walking"
        tooltipText:root.state.label+"\n"+root.state.owner
        onPressed: root.toggle()
    }
    KeyboardPanel {
        anchorItem:button;owner:root;bar:root.bar;open:root.opened
        focusTarget:catcher
        contentWidth:fittedContentWidth(Style.space(430))
        contentHeight:fittedContentHeight(column.implicitHeight,Style.space(760))
        PanelKeyCatcher {
            id:catcher;anchors.fill:parent
            Keys.onEscapePressed:root.close()
            onCloseRequested:root.close()
            onTabRequested:direction=>root.switchPanel(direction)
            Controls.ScrollView {
                id:scroll
                anchors.fill:parent;contentWidth:availableWidth;clip:true
                ColumnLayout {
                    id:column;width:scroll.availableWidth;spacing:Style.space(12)
                    RowLayout {
                        Label {text:"PitPat · "+root.state.label;Layout.fillWidth:true;font.bold:true}
                        Action {text:"×";Accessible.name:"Close controls";onClicked:root.close()}
                    }
                    Label {text:root.state.owner;Layout.fillWidth:true;wrapMode:Text.Wrap}
                    Label {text:root.service?.warning||"";visible:text!=="";color:Color.urgent;Layout.fillWidth:true;wrapMode:Text.Wrap}
                    Label {text:root.service?.errorText||"";visible:text!=="";color:Color.urgent;Layout.fillWidth:true;wrapMode:Text.Wrap}
                    Label {text:root.state.speed+" · "+root.state.distance+" · "+root.state.calories}
                    Label {text:root.state.steps+" steps · "+root.state.duration}
                    RowLayout {
                        Action {text:root.state.startText||"Start";enabled:root.state.canStartPause===true;onClicked:root.service.startPause()}
                        Action {text:"Stop";enabled:root.state.canStop===true;onClicked:root.service.stop()}
                        Action {text:"Stop & Disconnect";enabled:root.state.canStop===true;onClicked:root.service.stopDisconnect()}
                    }
                    RowLayout {
                        Action {text:"−0.1 MPH";enabled:root.state.canAdjust===true;onClicked:root.service.setTargetMph(Number(root.state.target)-0.1)}
                        Label {text:"Target: "+root.state.target+" MPH"}
                        Action {text:"+0.1 MPH";enabled:root.state.canAdjust===true;onClicked:root.service.setTargetMph(Number(root.state.target)+0.1)}
                    }
                    Action {text:"Take control while stopped";visible:!root.service?.isOwner;enabled:root.state.canTakeControl===true;onClicked:root.service.takeControl()}
                    Action {text:"Find treadmill";enabled:root.service?.authorized&&!root.service?.snapshot.connected&&!root.service?.snapshot.connecting;onClicked:root.service.discover()}
                    Repeater {
                        model:root.service?.devices||[]
                        delegate:Action {required property var modelData;text:"Connect: "+modelData.name;enabled:!root.service?.snapshot.connected;onClicked:root.service.connectDevice(modelData.id)}
                    }
                    Action {text:"Recover Stop control";visible:root.service?.snapshot.recovery&&!root.service?.snapshot.owner_present;onClicked:root.service.recover()}
                    RowLayout {
                        visible:root.service?.snapshot.session?.status==="interrupted"
                        Action {text:"Continue record";enabled:root.service?.isOwner;onClicked:root.service.resolve("continue")}
                        Action {text:"New record";enabled:root.service?.isOwner;onClicked:root.service.resolve("new")}
                    }
                    Action {text:"Stop & Release";enabled:root.service?.isOwner;onClicked:root.service.release()}
                    RowLayout {
                        Action {text:"Dashboard";onClicked:root.openPage("dashboard")}
                        Action {text:"History / export";onClicked:root.openPage("history")}
                    }
                    Label {Layout.fillWidth:true;wrapMode:Text.Wrap;font.pixelSize:Style.font.caption;text:"Closing this popup retains tray control. Losing the controller requests Stop. Bluetooth loss cannot guarantee stopping. Keep the physical stop control available."}
                }
            }
        }
    }
    component Action: Controls.Button {
        font.family:Style.font.family
        font.pixelSize:Style.font.body
        contentItem:Text {text:parent.text;color:Color.popups.text;opacity:parent.enabled?1:0.45;font:parent.font;horizontalAlignment:Text.AlignHCenter;verticalAlignment:Text.AlignVCenter}
        background:Rectangle {radius:Style.cornerRadius;color:parent.down?Color.accent:Qt.rgba(Color.foreground.r,Color.foreground.g,Color.foreground.b,parent.hovered?0.16:0.08)}
    }
    component Label:Text {textFormat:Text.PlainText;color:Color.popups.text;font.family:Style.font.family;font.pixelSize:Style.font.body}
}
