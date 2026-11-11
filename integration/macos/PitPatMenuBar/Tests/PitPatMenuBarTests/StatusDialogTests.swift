import Foundation
import XCTest
@testable import PitPatMenuBar

final class StatusDialogTests: XCTestCase {
    func testAuthorizedFixtureDialogs() throws {
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { url.deleteLastPathComponent() }
        let fixture = try XCTUnwrap(JSON.parse(String(contentsOf: url.appendingPathComponent("tests/fixtures/model-cases.json"), encoding: .utf8)))
        guard case .array(let cases)? = fixture["cases"] else { return XCTFail("no cases") }
        // Names deliberately select the reply category, independently of Model.view's state.
        let metrics: Set<String> = ["stopped-owner", "stopped-observer-browser", "stopped-no-owner", "walking-owner", "walking-observer", "paused-owner", "starting-owner", "imperial-walking", "storage-fault", "interrupted-session", "interrupted-no-owner-claimant", "resolved-no-owner-claimant", "blocked", "zero-target", "simulator-walking", "hour-duration"]
        let special = [
            "unavailable": "PitPat is open but no treadmill is connected.",
            "empty": "PitPat is open but no treadmill is connected.",
            "disconnected": "PitPat is open but no treadmill is connected.",
            "simulator-disconnected": "SIMULATOR · PitPat is open but no treadmill is connected.",
            "connecting": "PitPat is connecting to the treadmill.",
            "stale": "Motion unknown. The reading is stale.",
            "fault": "Stopped. 0.00 mph, 1.000 mi, 10m 0s, 1000 steps. Use the physical stop control if needed.",
            "recovery": "Motion unknown. Use the physical stop control if needed.",
            "stopping": "Stopping.", "stopping-no-owner": "Stopping.", "stopped-state-moving": "Stopping.",
            "safety-unavailable": "Safety unavailable.",
            "unknown-state": "Motion unknown.", "no-metrics": "Motion unknown."
        ]
        var seen = Set<String>()
        for item in cases {
            let name = item["name"].jsString
            let view = try XCTUnwrap(item["view"], name)
            let snapshot = item["snapshot"]
            let reply = statusDialog(authorized: true, model: Model.view(snapshot, item["isOwner"] == .bool(true)), snapshot: snapshot)
            if metrics.contains(name) {
                XCTAssertEqual(reply, "\(view["label"].jsString). \(view["speed"].jsString), \(view["distance"].jsString), \(view["duration"].jsString), \(view["steps"].jsString) steps.", name)
            } else {
                XCTAssertEqual(reply, try XCTUnwrap(special[name], "uncategorized fixture: " + name), name)
            }
            if name == "walking-owner" {
                XCTAssertEqual(reply, "Walking. 1.99 mph, 1.500 mi, 1h 2m 3s, 4321 steps.")
            }
            seen.insert(name)
        }
        XCTAssertEqual(seen, metrics.union(special.keys))
    }

    func testWarningIsVerbatimEvenWithoutFault() {
        let snapshot: JSON = .object(["available": .bool(true), "connected": .bool(false)])
        let warning = "Controller connection lost; belt state is unconfirmed."
        XCTAssertEqual(statusDialog(authorized: true, model: Model.view(snapshot, false), snapshot: snapshot, warning: warning),
                       "PitPat is open but no treadmill is connected. " + warning + " Use the physical stop control if needed.")
    }

    func testFaultWithWarningDoesNotClaimStoppedFromZeroSpeed() {
        let snapshot: JSON = .object(["available": .bool(true), "connected": .bool(true), "fault_id": .string("f1"), "metrics": .object(["state": .number(7), "speed_raw": .number(0)])])
        XCTAssertEqual(statusDialog(authorized: true, model: Model.view(snapshot, false), snapshot: snapshot, warning: "Stop unconfirmed"),
                       "Motion unknown. Stop unconfirmed. Use the physical stop control if needed.")
    }

    func testConnectionLostWarningIncludesGuidanceOnlyOnce() {
        let snapshot: JSON = .object(["available": .bool(true), "connected": .bool(false)])
        let warning = "Controller connection lost; belt state is unconfirmed. Use the physical stop control."
        let reply = statusDialog(authorized: true, model: Model.view(snapshot, false), snapshot: snapshot, warning: warning)
        XCTAssertEqual(reply, "PitPat is open but no treadmill is connected. " + warning)
        XCTAssertEqual(reply.components(separatedBy: "physical stop control").count - 1, 1)
    }

    func testSafetyStopGuidanceIncludesGuidanceOnlyOnce() {
        let snapshot: JSON = .object(["available": .bool(true), "connected": .bool(true), "fault_id": .string("f1")])
        let reply = statusDialog(authorized: true, model: Model.view(snapshot, false), snapshot: snapshot, warning: SafetyStop.guidance)
        XCTAssertEqual(reply, "Motion unknown. Stop unconfirmed. Use the physical stop control.")
        XCTAssertEqual(reply.components(separatedBy: "physical stop control").count - 1, 1)
    }

    func testMotionUnconfirmedGetsFullStop() {
        let model = Model.view(nil, false)
        XCTAssertEqual(statusDialog(authorized: true, model: model, warning: "Motion unconfirmed"),
                       "PitPat is open but no treadmill is connected. Motion unconfirmed. Use the physical stop control if needed.")
    }

    func testWarningTerminalPunctuationIsPreserved() {
        let model = Model.view(nil, false)
        for warning in ["Motion unconfirmed.", "Motion unconfirmed!", "Motion unconfirmed?"] {
            XCTAssertEqual(statusDialog(authorized: true, model: model, warning: warning),
                           "PitPat is open but no treadmill is connected. " + warning + " Use the physical stop control if needed.")
        }
    }

    func testExistingGuidanceIsDetectedCaseInsensitivelyInWarningOrReply() {
        var model = Model.view(nil, false)
        let warning = "Use the PHYSICAL STOP CONTROL!"
        XCTAssertEqual(statusDialog(authorized: true, model: model, warning: warning),
                       "PitPat is open but no treadmill is connected. " + warning)
        model.state = "Motion unknown"
        model.label = "Use the PHYSICAL STOP CONTROL"
        XCTAssertEqual(statusDialog(authorized: true, model: model, warning: "Motion unconfirmed"),
                       "Use the PHYSICAL STOP CONTROL. Motion unconfirmed.")
    }

    @MainActor
    func testAuthorizationArrivesWithinTimeout() async throws {
        var time = ContinuousClock.now
        let start = time
        let authorized = try await waitForAuthorization(timeout: .seconds(5), authorized: { time - start >= .seconds(1) }, now: { time }, sleep: { time = time.advanced(by: $0) })
        XCTAssertTrue(authorized)
        XCTAssertEqual(time - start, .seconds(1))
    }

    @MainActor
    func testAuthorizationTimeoutDiscardsPreviouslyWalkingSnapshot() async throws {
        var time = ContinuousClock.now
        let start = time
        let authorized = try await waitForAuthorization(timeout: .milliseconds(250), authorized: { false }, now: { time }, sleep: { time = time.advanced(by: $0) })
        XCTAssertFalse(authorized)
        XCTAssertEqual(time - start, .milliseconds(250))
        let snapshot: JSON = .object(["available": .bool(true), "connected": .bool(true), "metrics": .object(["state": .number(1)])])
        XCTAssertEqual(statusDialog(authorized: authorized, model: Model.view(snapshot, true), snapshot: snapshot, warning: "Old warning"),
                       "PitPat couldn't reach its services. Open PitPat from the menu bar to check.")
    }

    @MainActor
    func testAlreadyAuthorizedDoesNotSleep() async throws {
        let authorized = try await waitForAuthorization(timeout: .seconds(5), authorized: { true }, sleep: { _ in XCTFail("already authorized") })
        XCTAssertTrue(authorized)
    }

    @MainActor
    func testCancelledWaitThrows() async {
        do {
            _ = try await waitForAuthorization(timeout: .seconds(5), authorized: { false }, sleep: { _ in throw CancellationError() })
            XCTFail("cancellation swallowed")
        } catch { XCTAssertTrue(error is CancellationError) }
    }
}
