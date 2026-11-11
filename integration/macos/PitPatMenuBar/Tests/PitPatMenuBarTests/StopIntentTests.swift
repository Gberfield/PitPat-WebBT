import Darwin
import Foundation
import XCTest
@testable import PitPatMenuBar

// All sockets are private fakes; no app launch, services or hardware.
private final class FakeSafetySocket {
    let runtime = "/tmp/pitpat-stop-" + UUID().uuidString
    let fd: Int32
    var path: String { runtime + "/safety.sock" }

    init(listening: Bool = true) throws {
        try FileManager.default.createDirectory(atPath: runtime, withIntermediateDirectories: false)
        fd = socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else { throw NSError(domain: NSPOSIXErrorDomain, code: Int(errno)) }
        var address = sockaddr_un()
        address.sun_family = sa_family_t(AF_UNIX)
        withUnsafeMutableBytes(of: &address.sun_path) { $0.copyBytes(from: Array(path.utf8)) }
        let bound = withUnsafePointer(to: &address) {
            $0.withMemoryRebound(to: sockaddr.self, capacity: 1) { Darwin.bind(fd, $0, socklen_t(MemoryLayout<sockaddr_un>.size)) }
        }
        guard bound == 0, !listening || listen(fd, 4) == 0 else {
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
    func testProbeRequiresListenerAndSendsNothing() throws {
        let fake = try FakeSafetySocket()
        XCTAssertTrue(safetyIsRunning(path: fake.path))
        let client = fake.acceptClient()
        XCTAssertGreaterThanOrEqual(client, 0)
        guard client >= 0 else { return }
        defer { close(client) }
        var p = pollfd(fd: client, events: Int16(POLLIN), revents: 0)
        XCTAssertGreaterThan(poll(&p, 1, 1000), 0)
        var byte: UInt8 = 0
        XCTAssertEqual(read(client, &byte, 1), 0, "probe must close without sending even hello")
        XCTAssertFalse(safetyIsRunning(path: fake.runtime + "/missing.sock"))
        let stale = try FakeSafetySocket(listening: false)
        XCTAssertFalse(safetyIsRunning(path: stale.path))
    }

    func testSessionFlagLatchesOnlyAcceptedConnectedOrConnectingSnapshots() {
        for field in ["connected", "connecting"] {
            let service = Service(runtime: "/unused-test-runtime")
            XCTAssertFalse(service.hasSeenTreadmillConnection)
            service.receive("{\"v\":1,\"event\":\"snapshot\",\"generation\":1,\"seq\":1,\"snapshot\":{\"\(field)\":true}}")
            XCTAssertFalse(service.hasSeenTreadmillConnection, "unauthorized snapshot")
            service.receive("{\"v\":1,\"event\":\"authorized\",\"generation\":1,\"snapshot\":{\"connected\":false}}")
            service.receive("{\"v\":1,\"event\":\"snapshot\",\"generation\":0,\"seq\":1,\"snapshot\":{\"\(field)\":true}}")
            XCTAssertFalse(service.hasSeenTreadmillConnection, "obsolete snapshot")
            service.receive("{\"v\":1,\"event\":\"snapshot\",\"generation\":1,\"seq\":1,\"snapshot\":{\"\(field)\":true}}")
            XCTAssertTrue(service.hasSeenTreadmillConnection)
            service.receive("{\"v\":1,\"event\":\"snapshot\",\"generation\":1,\"seq\":2,\"snapshot\":{\"connected\":false,\"connecting\":false}}")
            service.receive("{\"v\":1,\"event\":\"authorized\",\"generation\":2,\"snapshot\":{}}")
            XCTAssertTrue(service.hasSeenTreadmillConnection, "must survive disconnect and reauthorization")
            let initiallyConnected = Service(runtime: "/unused-test-runtime")
            initiallyConnected.receive("{\"v\":1,\"event\":\"authorized\",\"generation\":1,\"snapshot\":{\"\(field)\":true}}")
            XCTAssertTrue(initiallyConnected.hasSeenTreadmillConnection, "authorized snapshot also counts")
        }
    }

    @MainActor
    func testRefusalRuleAllFourCombinations() async {
        for (probe, seen, sendsStop) in [(false, false, false), (false, true, true), (true, false, true), (true, true, true)] {
            var calls = 0
            let reply = await stopIntentDialog(safetyRunningAtLaunch: probe, hasSeenTreadmillConnection: seen) {
                calls += 1
                return "Stop unconfirmed. Use the physical stop control."
            }
            XCTAssertEqual(calls, sendsStop ? 1 : 0)
            XCTAssertEqual(reply, sendsStop ? "Stop unconfirmed. Use the physical stop control." : "PitPat wasn't open, so no treadmill is connected. Nothing was stopped.")
        }
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
            let reply = await stopIntentDialog(safetyRunningAtLaunch: true, hasSeenTreadmillConnection: false) {
                await withCheckedContinuation { continuation in
                    SafetyStop.run(runtime: fake.runtime) { continuation.resume(returning: $0) }
                }
            }
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
        let reply = await stopIntentDialog(safetyRunningAtLaunch: true, hasSeenTreadmillConnection: false) {
            await withCheckedContinuation { continuation in
                SafetyStop.run(runtime: fake.runtime + "/missing") { continuation.resume(returning: $0) }
            }
        }
        XCTAssertEqual(reply, "Stop unconfirmed. Use the physical stop control. No such file or directory")
    }
}
