// Port of bridge/desktop.py:safety_stop. One-shot authenticated Stop straight to
// <runtime>/safety.sock; it needs neither the bridge nor the motion lease.
import Foundation

enum SafetyStop {
    enum Outcome: Equatable { case stopped, notConnected, failed(String) }

    static let guidance = "Stop unconfirmed. Use the physical stop control."

    // Calls done on the main queue; only the intent opts out on explicit safety disconnection.
    static func run(runtime: String, skipIfDisconnected: Bool = false, done: @escaping (Outcome) -> Void) {
        DispatchQueue.global(qos: .userInitiated).async {
            let outcome = stop(path: runtime + "/safety.sock", skipIfDisconnected: skipIfDisconnected)
            DispatchQueue.main.async {
                if case .failed(let text) = outcome { done(.failed(text.isEmpty ? guidance : guidance + " " + text)) }
                else { done(outcome) }
            }
        }
    }

    static func stop(path: String, skipIfDisconnected: Bool = false) -> Outcome {
        let fd = connectUnix(path)
        guard fd >= 0 else { return .failed(String(cString: strerror(errno))) }
        defer { close(fd) }
        var buffer = Data()
        guard writeAll(fd, "{\"v\":1,\"op\":\"hello\",\"kind\":\"helper\"}\n") else { return .failed("Safety unavailable") }
        guard let hello = readLine(fd, &buffer, until: Date().addingTimeInterval(3)) else { return .failed("Safety authorization timed out") }
        guard let authorization = JSON.parse(hello), authorization["event"] == .string("authorized") else { return .failed("Safety authorization failed") }
        if skipIfDisconnected, case .object(let snapshot)? = authorization["snapshot"],
           snapshot["link_state"] == .string("disconnected"), snapshot["connected"] == .bool(false) {
            return .notConnected
        }
        guard writeAll(fd, "{\"v\":1,\"id\":\"stop\",\"op\":\"stop\",\"authority\":null,\"args\":{}}\n") else { return .failed("Safety unavailable") }
        let deadline = Date().addingTimeInterval(8)
        while true {
            guard let line = readLine(fd, &buffer, until: deadline) else {
                return .failed(Date() < deadline ? "Safety unavailable; Stop unconfirmed. Use physical stop." : "Stop timed out")
            }
            guard let message = JSON.parse(line), message["id"] == .string("stop") else { continue }
            return message["ok"] == .bool(true) && message["result"]?["outcome"] == .string("stopped_confirmed") ? .stopped : .failed("")
        }
    }

    // Next line before the deadline, or nil on end of stream, error, overlong line or timeout.
    private static func readLine(_ fd: Int32, _ buffer: inout Data, until deadline: Date) -> String? {
        while true {
            if let end = buffer.firstIndex(of: 10) {
                let line = String(decoding: buffer[buffer.startIndex..<end], as: UTF8.self)
                buffer.removeSubrange(buffer.startIndex...end)
                return line
            }
            if buffer.count > maxLine { return nil }
            let wait = Int32(max(0, deadline.timeIntervalSinceNow) * 1000)
            var p = pollfd(fd: fd, events: Int16(POLLIN), revents: 0)
            guard wait > 0, poll(&p, 1, wait) > 0 else { return nil }
            var chunk = [UInt8](repeating: 0, count: 4096)
            let n = read(fd, &chunk, chunk.count)
            if n < 0 && errno == EINTR { continue }
            guard n > 0 else { return nil }
            buffer.append(contentsOf: chunk[0..<n])
        }
    }
}
