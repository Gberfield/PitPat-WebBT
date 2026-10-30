// Menu bar controller replacing the Omarchy tray (Widget.qml). The status item is the
// registered view, so closing the popover keeps tray control; quitting releases it.
// AppKit owns the status item and popover so the hotkey and pitpat://controls can open it.
import AppKit
import Carbon.HIToolbox
import Combine
import SwiftUI
import UserNotifications

let dashboardURL = "http://127.0.0.1:8766/"

struct ControlsView: View {
    @ObservedObject var service: Service
    let openPage: (String) -> Void
    let quit: () -> Void

    var body: some View {
        let m = service.model, s = service.snapshot
        let interrupted = s["session"]?["status"] == .string("interrupted")
        VStack(alignment: .leading, spacing: 10) {
            Text("PitPat · " + m.label).font(.headline)
            Text(m.owner)
            if !service.warning.isEmpty { Text(service.warning).foregroundColor(.red).fixedSize(horizontal: false, vertical: true) }
            if !service.errorText.isEmpty { Text(service.errorText).foregroundColor(.red).fixedSize(horizontal: false, vertical: true) }
            Text(m.speed + " · " + m.distance + " · " + m.calories)
            Text(m.steps + " steps · " + m.duration)
            HStack {
                Button(m.startText) { service.startPause() }.disabled(!m.canStartPause)
                Button("Stop") { service.stop() }.buttonStyle(.borderedProminent).tint(.red).disabled(!m.canStop)
                Button("Stop & Disconnect") { service.stopDisconnect() }.disabled(!m.canStop)
            }
            HStack {
                Button("−0.1 MPH") { service.setTargetMph((Double(m.target) ?? .nan) - 0.1) }.disabled(!m.canAdjust)
                Text("Target: " + m.target + " MPH")
                Button("+0.1 MPH") { service.setTargetMph((Double(m.target) ?? .nan) + 0.1) }.disabled(!m.canAdjust)
            }
            if !service.isOwner {
                Button("Take control while stopped") { service.takeControl() }.disabled(!m.canTakeControl)
            }
            Button("Find treadmill") { service.discover() }
                .disabled(!(service.authorized && !s["connected"].truthy && !s["connecting"].truthy))
            ForEach(service.devices) { device in
                Button("Connect: " + device.name) { service.connectDevice(device.id) }.disabled(s["connected"].truthy)
            }
            if s["recovery"].truthy && !s["is_recovery_claimant"].truthy {
                Button("Claim recovery control") { service.recover() }
            }
            if s["fault_id"].truthy {
                Button("Confirm Stop and acknowledge recovery") { service.acknowledgeRecovery() }
                    .disabled(!(s["is_recovery_claimant"].truthy && !interrupted))
            }
            if interrupted {
                HStack {
                    Button("Continue record") { service.resolve("continue") }.disabled(!s["can_resolve_session"].truthy)
                    Button("New record") { service.resolve("new") }.disabled(!s["can_resolve_session"].truthy)
                }
            }
            Button("Stop & Release") { service.release() }.disabled(!service.isOwner)
            HStack {
                Button("Dashboard") { openPage("dashboard") }
                Button("History / export") { openPage("history") }
            }
            Text("Closing this popup retains tray control. Losing the controller requests Stop. Bluetooth loss cannot guarantee stopping. Keep the physical stop control available.")
                .font(.caption).fixedSize(horizontal: false, vertical: true)
            Divider()
            Button("Quit PitPat menu bar") { quit() }
        }
        .padding(14)
        .frame(width: 400)
    }
}

@main
final class AppDelegate: NSObject, NSApplicationDelegate {
    private static let shared = AppDelegate()
    let service = Service()
    private var item: NSStatusItem!
    private let popover = NSPopover()
    private var hotkeys: Hotkeys?
    private var observer: AnyCancellable?
    private var launchedByURL = false
    private var terminating = false

    static func main() {
        let app = NSApplication.shared
        app.delegate = shared
        app.setActivationPolicy(.accessory)
        app.run()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        item.button?.target = self
        item.button?.action = #selector(togglePopover)
        item.button?.imagePosition = .imageLeading
        popover.behavior = .transient
        let host = NSHostingController(rootView: ControlsView(service: service, openPage: { [weak self] in self?.openPage($0) },
                                                              quit: { NSApp.terminate(nil) }))
        host.sizingOptions = .preferredContentSize
        popover.contentViewController = host
        observer = service.objectWillChange.sink { [weak self] _ in DispatchQueue.main.async { self?.updateButton() } }
        service.registerView("menubar")
        updateButton()
        hotkeys = Hotkeys([(kVK_ANSI_P, { [weak self] in self?.showControls() }),
                           (kVK_Space, { [weak self] in self?.startPause() }),
                           (kVK_ANSI_Period, { [weak self] in self?.safetyStop() })])
        DispatchQueue.main.async { if !self.launchedByURL { self.showControls() } }
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        for url in urls where url.scheme == "pitpat" {
            launchedByURL = true
            switch url.host {
            case "start-pause": startPause()
            case "controls": showControls()
            default: break
            }
        }
    }

    func applicationShouldHandleReopen(_ sender: NSApplication, hasVisibleWindows flag: Bool) -> Bool {
        showControls()
        return false
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if terminating { return .terminateNow }
        terminating = true
        service.quit { NSApp.reply(toApplicationShouldTerminate: true) }
        return .terminateLater
    }

    private func updateButton() {
        guard let button = item?.button else { return }
        let m = service.model, walking = m.state == "Walking"
        let symbol = !service.warning.isEmpty ? "exclamationmark.triangle.fill" : walking ? "figure.walk.motion" : "figure.walk"
        button.image = NSImage(systemSymbolName: symbol, accessibilityDescription: "PitPat")
        button.image?.isTemplate = true
        button.contentTintColor = walking ? .systemGreen : nil
        button.title = (service.snapshot["simulator"] == .bool(true) ? " SIM" : "") + (walking ? " " + m.speed : "")
        button.toolTip = m.label + "\n" + m.owner
    }

    @objc private func togglePopover() {
        if popover.isShown { popover.performClose(nil) } else { showControls() }
    }

    private func showControls() {
        guard let button = item?.button else { return }
        NSApp.activate(ignoringOtherApps: true)
        if !popover.isShown { popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY) }
    }

    // Start/Pause comes from this lease-holding controller, like the Linux tray IPC.
    private func startPause() {
        if !service.startPause() { showControls() }
    }

    // Same path as `pitpat stop`: straight to safety.sock, never the control socket.
    private func safetyStop() {
        SafetyStop.run(runtime: service.runtime) { [weak self] failure in
            guard let self, let failure else { return }
            self.service.warning = failure
            self.notify(failure)
            self.showControls()
        }
    }

    private func openPage(_ which: String) {
        if let url = URL(string: dashboardURL + (which == "history" ? "#history-panel" : "")) { NSWorkspace.shared.open(url) }
    }

    private func notify(_ text: String) {
        guard Bundle.main.bundleIdentifier != nil else { return }
        let center = UNUserNotificationCenter.current()
        center.requestAuthorization(options: [.alert, .sound]) { granted, _ in
            guard granted else { return }
            let content = UNMutableNotificationContent()
            content.title = "PitPat"
            content.body = text
            center.add(UNNotificationRequest(identifier: UUID().uuidString, content: content, trigger: nil))
        }
    }
}
