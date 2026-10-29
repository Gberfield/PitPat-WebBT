// Port of bridge/desktop.py:safety_stop. One-shot authenticated Stop straight to
// <runtime>/safety.sock; it needs neither the bridge nor the motion lease.
import Foundation

enum SafetyStop {
    static let guidance = "Stop unconfirmed. Use the physical stop control."

    // Calls done on the main queue with nil once Stop is confirmed, else the failure text.
    static func run(runtime: String, done: @escaping (String?) -> Void) {
        DispatchQueue.global(qos: .userInitiated).async {
            let failure = stop(path: runtime + "/safety.sock")
            DispatchQueue.main.async { done(failure.map { $0.isEmpty ? guidance : guidance + " " + $0 }) }
        }
    }

    static func stop(path: String) -> String? {
        let fd = connectUnix(path)
        guard fd >= 0 else { return String(cString: strerror(errno)) }
        defer { close(fd) }
        var buffer = Data()
        guard writeAll(fd, "{\"v\":1,\"op\":\"hello\",\"kind\":\"helper\"}\n") else { return "Safety unavailable" }
        guard let hello = readLine(fd, &buffer, until: Date().addingTimeInterval(3)) else { return "Safety authorization timed out" }
        guard JSON.parse(hello)?["event"] == .string("authorized") else { return "Safety authorization failed" }
        guard writeAll(fd, "{\"v\":1,\"id\":\"stop\",\"op\":\"stop\",\"authority\":null,\"args\":{}}\n") else { return "Safety unavailable" }
        let deadline = Date().addingTimeInterval(8)
        while true {
            guard let line = readLine(fd, &buffer, until: deadline) else {
                return Date() < deadline ? "Safety unavailable; Stop unconfirmed. Use physical stop." : "Stop timed out"
            }
            guard let message = JSON.parse(line), message["id"] == .string("stop") else { continue }
            return message["ok"] == .bool(true) && message["result"]?["outcome"] == .string("stopped_confirmed") ? nil : ""
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
