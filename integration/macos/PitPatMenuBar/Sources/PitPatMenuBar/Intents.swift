import AppIntents

// Only observe the existing service; the app lifecycle owns connecting and retries.
@MainActor
func waitForAuthorization(timeout: Duration, authorized: () -> Bool,
                          now: () -> ContinuousClock.Instant = { ContinuousClock.now },
                          sleep: (Duration) async throws -> Void = { try await Task.sleep(for: $0) }) async throws -> Bool {
    let deadline = now().advanced(by: timeout)
    while !authorized() {
        let remaining = deadline - now()
        if remaining <= .zero { return false }
        try await sleep(min(.milliseconds(100), remaining))
    }
    return true
}

// Use the same presentation fields as the popover, including unknown and simulator labels.
func statusDialog(authorized: Bool, model: ModelView, snapshot: JSON? = nil, warning: String = "") -> String {
    guard authorized else { return "PitPat couldn't reach its services. Open PitPat from the menu bar to check." }
    let simulator = model.label.hasPrefix("SIMULATOR · ") ? "SIMULATOR · " : ""
    var reply: String
    if snapshot?["stale"].truthy == true {
        reply = "\(model.label). The reading is stale."
    } else {
        switch model.state {
        case "Disconnected", "Application unavailable":
            reply = simulator + "PitPat is open but no treadmill is connected."
        case "Connecting":
            reply = simulator + "PitPat is connecting to the treadmill."
        case "Walking", "Paused", "Starting", "Stopped":
            reply = "\(model.label). \(model.speed), \(model.distance), \(model.duration), \(model.steps) steps."
        default:
            reply = "\(model.label)."
        }
    }
    if !warning.isEmpty {
        reply += " " + warning
        if ![".", "!", "?"].contains(String(warning.suffix(1))) { reply += "." }
    }
    if (snapshot?["fault_id"].truthy == true || !warning.isEmpty)
        && reply.range(of: "physical stop control", options: .caseInsensitive) == nil {
        reply += " Use the physical stop control if needed."
    }
    return reply
}

struct PitPatStatusIntent: AppIntent {
    static var title: LocalizedStringResource = "PitPat Status"
    static var openAppWhenRun: Bool = false

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let service = AppDelegate.intentService
        _ = try await waitForAuthorization(timeout: .seconds(5), authorized: { service.authorized })
        return .result(dialog: IntentDialog(stringLiteral: statusDialog(authorized: service.authorized, model: service.model,
                                                                       snapshot: service.snapshot, warning: service.warning)))
    }
}

func stopIntentDialog(_ outcome: SafetyStop.Outcome) -> String {
    switch outcome {
    case .stopped: return "Stopped."
    case .notConnected: return "No treadmill is connected, so nothing was stopped."
    case .failed(let text): return text
    }
}

struct PitPatStopIntent: AppIntent {
    static var title: LocalizedStringResource = "Stop PitPat"
    static var openAppWhenRun: Bool = false

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        return .result(dialog: IntentDialog(stringLiteral: await AppDelegate.intentStop()))
    }
}

struct PitPatShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: PitPatStatusIntent(), phrases: [
            "PitPat status in \(.applicationName)",
            "How's my walk in \(.applicationName)"
        ], shortTitle: "PitPat Status", systemImageName: "figure.walk")
        AppShortcut(intent: PitPatStopIntent(), phrases: [
            "Stop \(.applicationName)",
            "Stop the treadmill in \(.applicationName)"
        ], shortTitle: "Stop PitPat", systemImageName: "stop.fill")
    }
}
