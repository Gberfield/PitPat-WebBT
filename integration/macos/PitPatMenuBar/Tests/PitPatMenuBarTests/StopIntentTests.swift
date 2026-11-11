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
    private func runStop(runtime: String, skipIfDisconnected: Bool? = true) async -> SafetyStop.Outcome {
        await withCheckedContinuation { continuation in
            if let skipIfDisconnected {
                SafetyStop.run(runtime: runtime, skipIfDisconnected: skipIfDisconnected) { continuation.resume(returning: $0) }
            } else {
                SafetyStop.run(runtime: runtime) { continuation.resume(returning: $0) }
            }
        }
    }

    @MainActor
    func testOnlyExplicitSafetyDisconnectionSkipsIntentStop() async throws {
        let snapshots: [(String?, Bool)] = [
            (#"{"link_state":"disconnected","connected":false}"#, false),
            (#"{"link_state":"connecting","connected":false}"#, true),
            (#"{"link_state":"connected","connected":true}"#, true),
            (#"{"link_state":"lost","connected":false}"#, true),
            (#"{"connected":false}"#, true),
            (#"{"link_state":"disconnected","connected":true}"#, true),
            (#"{"link_state":"disconnected","connected":0}"#, true),
            (#"{"link_state":"disconnected","connected":"false"}"#, true),
            (#"{"link_state":"disconnected","connected":null}"#, true),
            (#"{"link_state":"disconnected"}"#, true),
            (#"{"link_state":false,"connected":false}"#, true),
            (#"{"link_state":"unknown","connected":false}"#, true),
            (nil, true), ("null", true), ("[]", true), ("false", true), (#""disconnected""#, true)
        ]
        for (snapshot, sendsStop) in snapshots {
            try await checkHello(snapshot: snapshot, skipIfDisconnected: true, sendsStop: sendsStop)
        }
    }

    @MainActor
    func testDefaultHotkeyModeSendsStopEvenWhenSafetyReportsDisconnected() async throws {
        try await checkHello(snapshot: #"{"link_state":"disconnected","connected":false}"#,
                             skipIfDisconnected: nil, sendsStop: true)
    }

    @MainActor
    private func checkHello(snapshot: String?, skipIfDisconnected: Bool?, sendsStop: Bool) async throws {
        let fake = try FakeSafetySocket()
        let served = expectation(description: "hello snapshot: " + (snapshot ?? "missing"))
        DispatchQueue.global().async {
            defer { served.fulfill() }
            let client = fake.acceptClient()
            XCTAssertGreaterThanOrEqual(client, 0)
            guard client >= 0 else { return }
            defer { close(client) }
            XCTAssertEqual(fake.line(client), #"{"v":1,"op":"hello","kind":"helper"}"#)
            let field = snapshot.map { ",\"snapshot\":" + $0 } ?? ""
            XCTAssertTrue(writeAll(client, "{\"v\":1,\"event\":\"authorized\"" + field + "}\n"))
            if sendsStop {
                XCTAssertEqual(fake.line(client), #"{"v":1,"id":"stop","op":"stop","authority":null,"args":{}}"#)
                XCTAssertTrue(writeAll(client, "{\"id\":\"stop\",\"ok\":true,\"result\":{\"outcome\":\"stopped_confirmed\"}}\n"))
            } else {
                var p = pollfd(fd: client, events: Int16(POLLIN), revents: 0)
                XCTAssertGreaterThan(poll(&p, 1, 3000), 0)
                var byte: UInt8 = 0
                XCTAssertEqual(read(client, &byte, 1), 0, "must close without sending Stop")
            }
        }
        let outcome = await runStop(runtime: fake.runtime, skipIfDisconnected: skipIfDisconnected)
        XCTAssertEqual(outcome, sendsStop ? .stopped : .notConnected)
        XCTAssertEqual(stopIntentDialog(outcome), sendsStop ? "Stopped." : "No treadmill is connected, so nothing was stopped.")
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
