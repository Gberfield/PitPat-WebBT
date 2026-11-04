// Opening the tray starts the installed services, like `pitpat controls` (bridge/desktop.py
// start_services). Starting the bridge never scans or connects; that still waits for Connect.
// Services stay on demand: nothing here runs at login, and quitting the tray leaves them as they are.
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

    // Calls done on the main queue with nil, or a message for the popover.
    static func run(_ done: @escaping (String?) -> Void) {
        DispatchQueue.global(qos: .userInitiated).async {
            var failure: String? = nil
            for args in commands() {
                let p = Process()
                p.executableURL = URL(fileURLWithPath: "/bin/launchctl")
                p.arguments = args
                p.standardOutput = FileHandle.nullDevice
                p.standardError = FileHandle.nullDevice
                do { try p.run(); p.waitUntilExit() } catch { failure = "Could not start PitPat services: \(error.localizedDescription)"; break }
                if p.terminationStatus != 0 {
                    failure = "Could not start \(args[1].split(separator: "/").last ?? "PitPat service") (launchctl \(p.terminationStatus)). Is PitPat installed?"
                    break
                }
            }
            DispatchQueue.main.async { done(failure) }
        }
    }
}
