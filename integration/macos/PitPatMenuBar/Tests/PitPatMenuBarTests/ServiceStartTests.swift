import XCTest
@testable import PitPatMenuBar

final class ServiceStartTests: XCTestCase {
    func testStartsSafetyThenBridgeWithoutRestarting() {
        XCTAssertEqual(ServiceStart.commands(uid: 501), [
            ["kickstart", "gui/501/com.gberfield.pitpat.safety"],
            ["kickstart", "gui/501/com.gberfield.pitpat.bridge"],
        ])
    }

    func testStopsBridgeThenSafety() {
        XCTAssertEqual(ServiceStart.stopCommands(uid: 501), [
            ["kill", "SIGTERM", "gui/501/com.gberfield.pitpat.bridge"],
            ["kill", "SIGTERM", "gui/501/com.gberfield.pitpat.safety"],
        ])
    }

    func testSkipsRealServicesForCustomRuntimes() {
        XCTAssertTrue(ServiceStart.shouldStart([:]))
        XCTAssertTrue(ServiceStart.shouldStart(["PITPAT_RUNTIME_DIR": ""]))
        XCTAssertFalse(ServiceStart.shouldStart(["PITPAT_RUNTIME_DIR": "/tmp/r"]))
        XCTAssertFalse(ServiceStart.shouldStart(["PITPAT_RUNTIME_ROOT": "/tmp/r"]))
        XCTAssertFalse(ServiceStart.shouldStart(["PITPAT_NO_SERVICE_START": "1"]))
    }
}
