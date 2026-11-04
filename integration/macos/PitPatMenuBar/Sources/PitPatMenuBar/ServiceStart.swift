// The tray owns the installed services' lifetime: opening it starts them, like `pitpat controls`
// (bridge/desktop.py start_services), and quitting it stops them, like `pitpat services-stop`.
// Starting the bridge never scans or connects; that still waits for Connect. Nothing runs at login.
import Foundation

enum ServiceStart {
    static let labels = ["com.gberfield.pitpat.safety", "com.gberfield.pitpat.bridge"]

    // A custom runtime means a test or simulator install; leave the real services alone.
    static func shouldStart(_ env: [String: String] = ProcessInfo.processInfo.environment) -> Bool {
        !["PITPAT_RUNTIME_DIR", "PITPAT_RUNTIME_ROOT", "PITPAT_NO_SERVICE_START"].contains { !(env[$0] ?? "").isEmpty }
    }

    // Without -k, kickstart leaves a running service alone.
    static func commands(uid: uid_t = getuid()) -> [[String]] {
        labels.map { ["kickstart", "gui/\(uid)/\($0)"] }
    }

    // Bridge first, then safety, like stop_services. Safety stops a still-connected belt on SIGTERM.
    static func stopCommands(uid: uid_t = getuid()) -> [[String]] {
        labels.reversed().map { ["kill", "SIGTERM", "gui/\(uid)/\($0)"] }
    }

    // Best effort: a service that is not running counts as stopped. Calls done on the main queue.
    static func stop(_ done: @escaping () -> Void) {
        DispatchQueue.global(qos: .userInitiated).async {
            for args in stopCommands() { _ = launchctl(args) }
            DispatchQueue.main.async(execute: done)
        }
    }

    private static func launchctl(_ args: [String]) -> Int32? {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/launchctl")
        p.arguments = args
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        do { try p.run(); p.waitUntilExit() } catch { return nil }
        return p.terminationStatus
    }

    // Calls done on the main queue with nil, or a message for the popover.
    static func run(_ done: @escaping (String?) -> Void) {
        DispatchQueue.global(qos: .userInitiated).async {
            var failure: String? = nil
            for args in commands() {
                guard let status = launchctl(args) else { failure = "Could not run launchctl to start PitPat services."; break }
                if status != 0 {
                    failure = "Could not start \(args[1].split(separator: "/").last ?? "PitPat service") (launchctl \(status)). Is PitPat installed?"
                    break
                }
            }
            DispatchQueue.main.async { done(failure) }
        }
    }
}
