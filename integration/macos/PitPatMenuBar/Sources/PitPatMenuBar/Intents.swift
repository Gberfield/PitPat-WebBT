import AppIntents

// Use the same presentation fields as the popover, including unknown and simulator labels.
func statusDialog(authorized: Bool, model: ModelView) -> String {
    guard authorized else { return "PitPat isn't connected to its services." }
    return "\(model.label). \(model.speed), \(model.distance), \(model.duration)."
}

struct PitPatStatusIntent: AppIntent {
    static var title: LocalizedStringResource = "PitPat Status"
    static var openAppWhenRun: Bool = false

    @MainActor
    func perform() async throws -> some IntentResult & ProvidesDialog {
        let service = AppDelegate.intentService
        return .result(dialog: IntentDialog(stringLiteral: statusDialog(authorized: service.authorized, model: service.model)))
    }
}

struct PitPatShortcuts: AppShortcutsProvider {
    static var appShortcuts: [AppShortcut] {
        AppShortcut(intent: PitPatStatusIntent(), phrases: [
            "PitPat status in \(.applicationName)",
            "How's my walk in \(.applicationName)"
        ], shortTitle: "PitPat Status", systemImageName: "figure.walk")
    }
}
