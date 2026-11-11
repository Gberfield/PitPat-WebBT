import Darwin
import Foundation
import XCTest
@testable import PitPatMenuBar

// All sockets are private fakes; no app launch, services or hardware.
private final class FakeSafetySocket: Sendable {
    let runtime = "/tmp/pitpat-stop-" + UUID().uuidString
    let fd: Int32
    var path: String { runtime + "/safety.sock" }

    init() throws {
        try FileManager.default.createDirectory(atPath: runtime, withIntermediateDirectories: false)
        fd = socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else { throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno)) }
        var address = sockaddr_un()
        address.sun_family = sa_family_t(AF_UNIX)
        withUnsafeMutableBytes(of: &address.sun_path) { $0.copyBytes(from: Array(path.utf8)) }
        let bound = withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) }
        }
        guard bound == 0, listen(fd, 4) == 0 else {
            let error = errno
            close(fd)
            try? FileManager.default.removeItem(atPath: runtime)
            throw NSError(domain: NSPOSIXErrorDomain, code: Int(error))
        }
    }

    deinit { close(fd); try? FileManager.default.removeItem(atPath: runtime) }

    func acceptClient() -> Int32 {
        var p = pollfd(fd: fd, events: Int16(POLLIN), revents: 0)
        guard poll(&p, 1, 3000) > 0 else { return -1 }
        return accept(fd, nil, nil)
    }

    func line(_ client: Int32) -> String? {
        var bytes: [UInt8] = []
        while bytes.count < 4096 {
            var p = pollfd(fd: client, events: Int16(POLLIN), revents: 0)
            guard poll(&p, 1, 3000) > 0 else { return nil }
            var byte: UInt8 = 0
            guard read(client, &byte, 1) == 1 else { return nil }
            if byte == 10 { return String(decoding: bytes, as: UTF8.self) }
            bytes.append(byte)
        }
        return nil
    }
}

final class StopIntentTests: XCTestCase {
    @MainActor
    private func runStop(runtime: String) async -> SafetyStop.Outcome {
        await withCheckedContinuation { continuation in
            SafetyStop.run(runtime: runtime) { continuation.resume(returning: $0) }
        }
    }

    @MainActor
    func testIntentStopSendsStopEvenWhenSafetyReportsDisconnected() async throws {
        let fake = try FakeSafetySocket()
        let served = expectation(description: "disconnected hello still requires Stop")
        DispatchQueue.global().async {
            defer { served.fulfill() }
            let client = fake.acceptClient()
            XCTAssertGreaterThanOrEqual(client, 0)
            guard client >= 0 else { return }
            defer { close(client) }
            XCTAssertEqual(fake.line(client), #"{"v":1,"op":"hello","kind":"helper"}"#)
            XCTAssertTrue(writeAll(client, "{\"v\":1,\"event\":\"authorized\",\"snapshot\":{\"link_state\":\"disconnected\",\"connected\":false}}\n"))
            XCTAssertEqual(fake.line(client), #"{"v":1,"id":"stop","op":"stop","authority":null,"args":{}}"#)
            XCTAssertTrue(writeAll(client, "{\"id\":\"stop\",\"ok\":true,\"result\":{\"outcome\":\"stopped_confirmed\"}}\n"))
        }
        let outcome = await runStop(runtime: fake.runtime)
        XCTAssertEqual(outcome, .stopped)
        XCTAssertEqual(stopIntentDialog(outcome), "Stopped.")
        await fulfillment(of: [served], timeout: 5)
    }

    @MainActor
    func testStopRepliesFromRealSafetyStopAgainstFakeSocket() async throws {
        let cases: [(String?, String)] = [
            ("{\"id\":\"stop\",\"ok\":true,\"result\":{\"outcome\":\"stopped_confirmed\"}}", "Stopped."),
            ("{\"id\":\"stop\",\"ok\":false,\"error\":\"denied\",\"result\":{\"outcome\":\"stopped_confirmed\"}}", "Stop unconfirmed. Use the physical stop control."),
            ("{\"id\":\"stop\",\"ok\":true,\"result\":{\"outcome\":\"requested\"}}", "Stop unconfirmed. Use the physical stop control."),
            (nil, "Stop unconfirmed. Use the physical stop control. Stop timed out")
        ]
        for (response, expected) in cases {
            let fake = try FakeSafetySocket()
            let served = expectation(description: "fake safety exchange")
            DispatchQueue.global().async {
                defer { served.fulfill() }
                let client = fake.acceptClient()
                XCTAssertGreaterThanOrEqual(client, 0)
                guard client >= 0 else { return }
                defer { close(client) }
                XCTAssertEqual(fake.line(client), "{\"v\":1,\"op\":\"hello\",\"kind\":\"helper\"}")
                guard writeAll(client, "{\"event\":\"authorized\"}\n") else { return XCTFail("fake authorization write failed") }
                XCTAssertEqual(fake.line(client), "{\"v\":1,\"id\":\"stop\",\"op\":\"stop\",\"authority\":null,\"args\":{}}")
                if let response { XCTAssertTrue(writeAll(client, response + "\n")) }
                else {
                    // Keep open until the unchanged eight-second Stop deadline expires.
                    var p = pollfd(fd: client, events: Int16(POLLIN), revents: 0)
                    _ = poll(&p, 1, 10000)
                }
            }
            let reply = stopIntentDialog(await runStop(runtime: fake.runtime))
            if response == nil {
                // SafetyStop's millisecond poll can finish just before its Date deadline.
                // Preserve both existing failure classifications, with exact hotkey wording.
                XCTAssertTrue([expected, "Stop unconfirmed. Use the physical stop control. Safety unavailable; Stop unconfirmed. Use physical stop."].contains(reply), reply)
            } else { XCTAssertEqual(reply, expected) }
            await fulfillment(of: [served], timeout: 12)
        }
    }

    @MainActor
    func testMissingSocketReply() async throws {
        let fake = try FakeSafetySocket()
        let reply = stopIntentDialog(await runStop(runtime: fake.runtime + "/missing"))
        XCTAssertEqual(reply, "Stop unconfirmed. Use the physical stop control. No such file or directory")
    }
}
