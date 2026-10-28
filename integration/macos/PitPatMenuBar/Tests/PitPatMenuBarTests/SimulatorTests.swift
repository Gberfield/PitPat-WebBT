import Foundation
import XCTest
@testable import PitPatMenuBar

// Opt-in walk against a running `--simulate` bridge and safety process:
//   PITPAT_SIMULATOR_RUNTIME=<runtime dir> [PITPAT_SIMULATOR_BRIDGE_PID=<pid>] swift test --filter SimulatorTests
// It refuses to send anything unless the bridge reports simulator mode.
final class SimulatorTests: XCTestCase {
    private func wait(_ what: String, _ seconds: Double = 10, _ done: () -> Bool) throws {
        let deadline = Date().addingTimeInterval(seconds)
        while !done() {
            if Date() > deadline { throw NSError(domain: "Timed out waiting for " + what, code: 1) }
            RunLoop.main.run(until: Date().addingTimeInterval(0.05))
        }
    }

    func testTrayWalkStopAndRecoveryAgainstSimulator() throws {
        let env = ProcessInfo.processInfo.environment
        guard let runtime = env["PITPAT_SIMULATOR_RUNTIME"] else { throw XCTSkip("PITPAT_SIMULATOR_RUNTIME not set") }
        let service = Service(runtime: runtime)
        service.registerView("test")
        try wait("authorized") { service.authorized }
        guard service.snapshot["simulator"] == .bool(true) else { return XCTFail("Bridge is not in simulator mode; refusing to continue") }
        XCTAssertEqual(service.model.label, "SIMULATOR · Disconnected")

        service.discover()
        try wait("devices") { !service.devices.isEmpty }
        let device = try XCTUnwrap(service.devices.first)
        XCTAssertEqual(device.name, "SIMULATOR — no physical treadmill")
        service.connectDevice(device.id)
        try wait("tray owns a stopped belt", 30) { service.isOwner && service.model.state == "Stopped" && service.model.canStartPause }
        XCTAssertEqual(service.model.owner, "Tray controls motion")

        XCTAssertTrue(service.startPause())
        try wait("walking") { service.model.state == "Walking" }
        XCTAssertEqual(service.model.startText, "Pause")
        XCTAssertTrue(service.startPause())
        try wait("paused") { service.model.state == "Paused" }
        XCTAssertTrue(service.startPause())
        try wait("walking again") { service.model.state == "Walking" }

        // The Stop hotkey path: straight to safety.sock, independent of control.sock.
        var failure: String?? = .none
        SafetyStop.run(runtime: runtime) { failure = .some($0) }
        try wait("safety stop") { failure != nil }
        XCTAssertEqual(failure, .some(nil))
        try wait("stopped") { service.model.state == "Stopped" }

        if let pid = env["PITPAT_SIMULATOR_BRIDGE_PID"].flatMap(Int32.init) {
            XCTAssertTrue(service.startPause())
            try wait("walking before freeze") { service.model.state == "Walking" }
            kill(pid, SIGSTOP)
            defer { kill(pid, SIGCONT) }
            try wait("controller loss", 15) { !service.authorized }
            XCTAssertEqual(service.warning, "Controller connection lost; belt state is unconfirmed. Use the physical stop control.")
            XCTAssertEqual(service.errorText, "Request timed out; motion unconfirmed. Use the physical stop control.")
            kill(pid, SIGCONT)
            try wait("reconnected in recovery", 20) { service.authorized && service.snapshot["fault_id"].truthy }
            service.recover()
            try wait("recovery claimant") { service.snapshot["is_recovery_claimant"].truthy }
            if service.snapshot["session"]?["status"] == .string("interrupted") {
                service.resolve("continue")
                try wait("record resolved") { service.snapshot["session"]?["status"] != .string("interrupted") }
            }
            service.acknowledgeRecovery()
            try wait("recovery acknowledged", 15) { !service.snapshot["fault_id"].truthy && service.isOwner }
            XCTAssertEqual(service.model.state, "Stopped")
        }

        service.stopDisconnect()
        try wait("disconnected", 15) { !service.snapshot["connected"].truthy && service.authorized }
        var quit = false
        service.quit { quit = true }
        try wait("released") { quit }
    }
}
