// Port of integration/omarchy/gabe.pitpat/Service.qml: the tray's native controller
// on <runtime>/control.sock. Main-queue only.
import Foundation

struct Device: Identifiable, Equatable { let id: String; let name: String }

func runtimePath(_ env: [String: String] = ProcessInfo.processInfo.environment) -> String {
    if let dir = env["PITPAT_RUNTIME_DIR"], !dir.isEmpty { return dir }
    let root = env["PITPAT_RUNTIME_ROOT"].flatMap { $0.isEmpty ? nil : $0 }
        ?? FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Application Support/PitPat/run").path
    return root + "/pitpat"
}

final class Service: ObservableObject {
    struct Pending { let op: String; let generation: Int; let at: Date; let callback: ((JSON) -> Void)? }

    @Published private(set) var snapshot: JSON = .object(["available": .bool(false), "connected": .bool(false)])
    @Published private(set) var devices: [Device] = []
    @Published private(set) var authorized = false
    @Published var warning = ""
    @Published var errorText = ""
    private var views = Set<String>()
    private var pending: [String: Pending] = [:]
    private var serial = 0, generation = 0, sequence = 0
    private var releasing = false
    private var channel: LineSocket?
    private var socketConnected = false
    private var timer: Timer?
    private var released: (() -> Void)?
    let runtime: String

    init(runtime: String = runtimePath()) { self.runtime = runtime }

    var isOwner: Bool { authorized && snapshot["is_owner"] == .bool(true) }
    var model: ModelView { Model.view(snapshot, isOwner) }
    var viewCount: Int { views.count }

    func registerView(_ key: String) {
        views.insert(key)
        if timer == nil { timer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] _ in self?.tick() } }
        ensureSocket()
    }

    func unregisterView(_ key: String) {
        views.remove(key)
        if viewCount == 0 {
            if isOwner {
                releasing = true
                if !request("release", [:], { [weak self] _ in self?.finishRelease() }) { finishRelease() }
            } else { dropSocket() }
        }
    }

    // Releases motion ownership like closing the last Linux view, then calls done.
    func quit(_ done: @escaping () -> Void) {
        released = done
        unregisterView("menubar")
        notifyReleased()
    }

    private func notifyReleased() {
        guard !releasing, let done = released else { return }
        released = nil
        DispatchQueue.main.async(execute: done)
    }

    private func ensureSocket() {
        guard channel == nil else { return }
        let c = LineSocket()
        channel = c
        c.onLine = { [weak self, weak c] line in
            guard let self, let c, self.channel === c else { return }
            self.receive(line)
        }
        c.onClose = { [weak self, weak c] in
            guard let self, let c, self.channel === c else { return }
            self.channel = nil
            if self.socketConnected { self.socketConnected = false; self.lost() }
        }
        c.open(path: runtime + "/control.sock") { [weak self, weak c] in
            guard let self, let c, self.channel === c else { return }
            self.socketConnected = true
            self.send(["v": 1, "op": "hello", "kind": "tray"])
        }
    }

    private func dropSocket() {
        guard let c = channel else { return }
        channel = nil
        c.close()
        if socketConnected { socketConnected = false; lost() }
    }

    private func lost() {
        if authorized && snapshot["connected"].truthy {
            warning = "Controller connection lost; belt state is unconfirmed. Use the physical stop control."
        }
        authorized = false; pending = [:]; releasing = false
        var next: [String: JSON] = ["available": .bool(false), "connected": .bool(false)]
        next["simulator"] = snapshot["simulator"]
        snapshot = .object(next)
        notifyReleased()
    }

    private func finishRelease() {
        releasing = false
        if viewCount == 0 { dropSocket() }
        notifyReleased()
    }

    private func send(_ value: [String: Any]) {
        guard let data = try? JSONSerialization.data(withJSONObject: value), let text = String(data: data, encoding: .utf8) else { return }
        channel?.send(text + "\n")
    }

    @discardableResult
    func request(_ op: String, _ args: [String: Any] = [:], _ callback: ((JSON) -> Void)? = nil) -> Bool {
        if !authorized || channel == nil { errorText = "Local bridge unavailable. Open Controls to start it."; return false }
        if pending.count >= 8 { errorText = "Too many pending requests"; return false }
        serial += 1
        let id = String(serial)
        pending[id] = Pending(op: op, generation: generation, at: Date(), callback: callback)
        send(["v": 1, "id": id, "op": op, "generation": generation, "args": args])
        return true
    }

    private func acceptSnapshot(_ value: JSON?) {
        guard value.truthy else { return }
        var next = value?.object ?? [:]
        next["available"] = .bool(true)
        next["simulator"] = .bool(snapshot["simulator"] == .bool(true))
        snapshot = .object(next)
    }

    func receive(_ line: String) {
        if line.utf16.count > maxLine { dropSocket(); return }
        guard let msg = JSON.parse(line) else { dropSocket(); return }
        if !msg["v"].strictlyEquals(1) { dropSocket(); return }
        if msg["event"] == .string("authorized") {
            authorized = true; generation = Int(exactly: msg["generation"].jsNumber) ?? 0; sequence = 0
            var next = msg["snapshot"]?.object ?? [:]
            next["available"] = .bool(true)
            next["simulator"] = .bool(msg["simulator"] == .bool(true))
            snapshot = .object(next)
            return
        }
        if !authorized { dropSocket(); return }
        if msg["id"].truthy {
            guard let item = pending.removeValue(forKey: msg["id"].jsString) else { return }
            let changes = ["connect", "take_control", "release", "stop_disconnect", "observe", "acknowledge_recovery"]
            let g = msg["generation"]
            if g.jsNumber < Double(generation) || g.jsNumber < Double(item.generation) ||
                (!g.strictlyEquals(Double(item.generation)) && !changes.contains(item.op)) {
                errorText = "Obsolete response discarded"; return
            }
            if let n = Int(exactly: g.jsNumber) { generation = n }
            if !msg["ok"].truthy { errorText = msg["error"].truthy ? msg["error"].jsString : "Request failed" }
            else {
                errorText = ""
                if msg["result"]?["devices"].truthy == true, case .array(let list)? = msg["result"]?["devices"] {
                    devices = list.map { Device(id: $0["id"].jsString, name: $0["name"].jsString) }
                }
                if ["observe", "take_control", "resolve_session", "acknowledge_recovery"].contains(item.op) { acceptSnapshot(msg["result"]) }
            }
            item.callback?(msg)
            return
        }
        if msg["generation"].jsNumber < Double(generation) || msg["seq"].jsNumber <= Double(sequence) { return }
        if let n = Int(exactly: msg["generation"].jsNumber) { generation = n }
        if let n = Int(exactly: msg["seq"].jsNumber) { sequence = n }
        acceptSnapshot(msg["snapshot"])
        if msg["event"] == .string("safety") || msg["event"] == .string("lost") {
            let message = msg["data"]?["message"]
            warning = message.truthy ? message.jsString : "Motion unconfirmed"
        }
        if msg["event"] == .string("storage_fault") {
            let message = msg["data"]?["message"]
            errorText = message.truthy ? message.jsString : ""
        }
    }

    func discover() { request("discover") }
    func connectDevice(_ id: String) { request("connect", ["device_id": id]) }
    func recover() { request("connect", ["recover": true]) }
    func takeControl() { if model.canTakeControl { request("take_control") } }

    @discardableResult
    func startPause() -> Bool {
        if !model.canStartPause { errorText = "Take control of a healthy, stopped connection first."; return false }
        let speed = snapshot["target_speed"].truthy ? snapshot["target_speed"]!.any : 1000
        return request(model.startText == "Pause" ? "pause" : "start", ["speed": speed])
    }

    @discardableResult
    func stop() -> Bool {
        if !model.canStop { errorText = "No Bluetooth connection; use the physical stop control if needed."; return false }
        return request("stop")
    }

    func stopDisconnect() { request("stop_disconnect") }
    func release() { request("release") }

    func acknowledgeRecovery() {
        let fault = snapshot["fault_id"]
        request("stop") { [weak self] msg in
            guard let self, msg["ok"].truthy, self.snapshot["fault_id"] == fault else { return }
            self.request("acknowledge_recovery", ["fault_id": fault?.any ?? NSNull(),
                                                  "stop_confirmation_id": self.snapshot["stop_confirmation_id"]?.any ?? NSNull()])
        }
    }

    func setTargetMph(_ value: Double) {
        if model.canAdjust, let units = try? Model.targetUnits(value) { request("set_speed", ["speed": units]) }
    }

    func resolve(_ choice: String) {
        if snapshot["can_resolve_session"].truthy && snapshot["session"].truthy {
            request("resolve_session", ["session_id": snapshot["session"]?["sessionId"]?.any ?? NSNull(), "choice": choice])
        }
    }

    private func tick() {
        guard viewCount > 0 || releasing else { return }
        if channel == nil && viewCount > 0 { ensureSocket() }
        if (isOwner || snapshot["is_recovery_claimant"].truthy) && !releasing { request("renew") }
        let now = Date()
        for item in pending.values where now.timeIntervalSince(item.at) > (item.op == "connect" ? 26 : 8) {
            errorText = "Request timed out; motion unconfirmed. Use the physical stop control."
            dropSocket(); finishRelease()
            break
        }
    }
}
