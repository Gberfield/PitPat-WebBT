import Foundation

let maxLine = 65536

// Connected AF_UNIX stream fd, or -1 with errno set. macOS sun_path holds 104 bytes.
func connectUnix(_ path: String) -> Int32 {
    var address = sockaddr_un()
    let bytes = Array(path.utf8)
    guard bytes.count < MemoryLayout.size(ofValue: address.sun_path) else { errno = ENAMETOOLONG; return -1 }
    address.sun_family = sa_family_t(AF_UNIX)
    withUnsafeMutableBytes(of: &address.sun_path) { raw in raw.copyBytes(from: bytes) }
    let fd = socket(AF_UNIX, SOCK_STREAM, 0)
    guard fd >= 0 else { return -1 }
    var on: Int32 = 1
    setsockopt(fd, SOL_SOCKET, SO_NOSIGPIPE, &on, socklen_t(MemoryLayout<Int32>.size))
    let result = withUnsafePointer(to: &address) {
        $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.connect(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) }
    }
    if result != 0 { let saved = errno; close(fd); errno = saved; return -1 }
    return fd
}

// Writes every byte, waiting up to two seconds for a full socket buffer.
func writeAll(_ fd: Int32, _ text: String) -> Bool {
    var data = Array(text.utf8)[...]
    while !data.isEmpty {
        let n = data.withUnsafeBytes { write(fd, $0.baseAddress, $0.count) }
        if n > 0 { data = data.dropFirst(n); continue }
        if n < 0 && (errno == EAGAIN || errno == EINTR) {
            var p = pollfd(fd: fd, events: Int16(POLLOUT), revents: 0)
            if poll(&p, 1, 2000) > 0 { continue }
        }
        return false
    }
    return true
}

/// Newline-delimited JSON over one AF_UNIX stream. Socket work stays on one serial
/// queue; every callback arrives on the main queue.
final class LineSocket {
    private let queue = DispatchQueue(label: "com.gberfield.pitpat.socket")
    private var fd: Int32 = -1
    private var source: DispatchSourceRead?
    private var buffer = Data()
    private var closed = false
    var onLine: (String) -> Void = { _ in }
    var onClose: () -> Void = {}

    func open(path: String, onOpen: @escaping () -> Void) {
        queue.async {
            let fd = connectUnix(path)
            guard fd >= 0 else { self.closeNow(); return }
            _ = fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK)
            self.fd = fd
            let source = DispatchSource.makeReadSource(fileDescriptor: fd, queue: self.queue)
            source.setEventHandler { self.readAvailable() }  // Cancel releases the handler.
            source.setCancelHandler { Darwin.close(fd) }
            self.source = source
            source.resume()
            DispatchQueue.main.async(execute: onOpen)
        }
    }

    func send(_ line: String) {
        queue.async { if !self.closed && !writeAll(self.fd, line) { self.closeNow() } }
    }

    func close() { queue.async { self.closeNow() } }

    private func readAvailable() {
        var chunk = [UInt8](repeating: 0, count: 16384)
        let n = read(fd, &chunk, chunk.count)
        if n < 0 && (errno == EAGAIN || errno == EINTR) { return }
        if n <= 0 { closeNow(); return }
        buffer.append(contentsOf: chunk[0..<n])
        var lines: [String] = []
        while let end = buffer.firstIndex(of: 10) {
            lines.append(String(decoding: buffer[buffer.startIndex..<end], as: UTF8.self))
            buffer.removeSubrange(buffer.startIndex...end)
        }
        // A line longer than the limit can never become valid; UTF-8 needs at most 4 bytes per code unit here.
        if buffer.count > maxLine * 4 { closeNow() }
        if !lines.isEmpty { DispatchQueue.main.async { for line in lines { self.onLine(line) } } }
    }

    private func closeNow() {
        guard !closed else { return }
        closed = true
        if let source { source.cancel() } else if fd >= 0 { Darwin.close(fd) }
        source = nil
        DispatchQueue.main.async { self.onClose() }
    }
}
