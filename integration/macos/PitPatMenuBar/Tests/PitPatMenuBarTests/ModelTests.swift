import Foundation
import XCTest
@testable import PitPatMenuBar

final class ModelTests: XCTestCase {
    // Generated from Model.js by tests/gen-model-cases.cjs.
    private func fixture() throws -> JSON {
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { url.deleteLastPathComponent() }
        let text = try String(contentsOf: url.appendingPathComponent("tests/fixtures/model-cases.json"), encoding: .utf8)
        return try XCTUnwrap(JSON.parse(text))
    }

    func testViewMatchesModelJsForEveryFixtureCase() throws {
        guard case .array(let cases)? = try fixture()["cases"] else { return XCTFail("no cases") }
        XCTAssertGreaterThanOrEqual(cases.count, 40)
        for item in cases {
            let name = item["name"].jsString + (item["isOwner"] == .bool(true) ? " (owner)" : "")
            let v = Model.view(item["snapshot"], item["isOwner"] == .bool(true))
            let expected = try XCTUnwrap(item["view"]?.object, name)
            let actual: [String: JSON] = [
                "state": .string(v.state), "label": .string(v.label), "owner": .string(v.owner),
                "canStartPause": .bool(v.canStartPause), "canAdjust": .bool(v.canAdjust), "canStop": .bool(v.canStop),
                "canTakeControl": .bool(v.canTakeControl), "startText": .string(v.startText), "speed": .string(v.speed),
                "distance": .string(v.distance), "calories": .string(v.calories), "steps": .string(v.steps),
                "duration": .string(v.duration), "target": .string(v.target)]
            XCTAssertEqual(actual, expected, name)
        }
    }

    func testTargetUnitsMatchModelJs() throws {
        guard case .array(let targets)? = try fixture()["targets"] else { return XCTFail("no targets") }
        for item in targets {
            XCTAssertEqual(try Model.targetUnits(item["mph"].jsNumber), Int(item["units"].jsNumber), item["mph"].jsString)
        }
        XCTAssertThrowsError(try Model.targetUnits(.nan))
    }

    func testJavaScriptNumberFormatting() {
        XCTAssertEqual(jsFixed(0.125, 2), "0.13")
        XCTAssertEqual(jsFixed(1.005, 2), "1.00")
        XCTAssertEqual(jsFixed(.nan, 2), "NaN")
        XCTAssertEqual(Model.duration(3723), "1h 2m 3s")
        XCTAssertEqual(Model.duration(3600), "1h 0m 0s")
        XCTAssertEqual(Model.duration(59.9), "59s")
        XCTAssertEqual(jsRound(2.5), 3)
        XCTAssertEqual(jsRound(-2.5), -2)
    }
}

final class ServiceTests: XCTestCase {
    private func authorized(_ simulator: Bool = true) -> Service {
        let service = Service(runtime: "/nonexistent")
        service.receive(#"{"v":1,"event":"authorized","generation":4,"simulator":\#(simulator),"snapshot":{"connected":false,"is_owner":false}}"#)
        return service
    }

    func testRuntimePathMatchesPlatformPaths() {
        XCTAssertEqual(runtimePath(["PITPAT_RUNTIME_ROOT": "/r"]), "/r/pitpat")
        XCTAssertEqual(runtimePath(["PITPAT_RUNTIME_DIR": "/d", "PITPAT_RUNTIME_ROOT": "/r"]), "/d")
        XCTAssertTrue(runtimePath([:]).hasSuffix("/Library/Application Support/PitPat/run/pitpat"))
    }

    func testAuthorizedSnapshotIsAvailableAndShowsSimulator() {
        let service = authorized()
        XCTAssertTrue(service.authorized)
        XCTAssertEqual(service.model.label, "SIMULATOR · Disconnected")
    }

    func testEventsOlderThanSequenceOrGenerationAreDropped() {
        let service = authorized()
        service.receive(#"{"v":1,"event":"state","generation":4,"seq":2,"snapshot":{"connected":true,"stopping":true}}"#)
        XCTAssertEqual(service.model.state, "Stopping")
        service.receive(#"{"v":1,"event":"state","generation":4,"seq":2,"snapshot":{"connected":false}}"#)
        service.receive(#"{"v":1,"event":"state","generation":3,"seq":9,"snapshot":{"connected":false}}"#)
        XCTAssertEqual(service.model.state, "Stopping")
        service.receive(#"{"v":1,"event":"safety","generation":5,"seq":3,"data":{},"snapshot":{"connected":true}}"#)
        XCTAssertEqual(service.warning, "Motion unconfirmed")
        XCTAssertEqual(service.model.label, "SIMULATOR · Motion unknown")
    }

    func testRequestsNeedAnAuthorizedSocket() {
        let service = Service(runtime: "/nonexistent")
        XCTAssertFalse(service.request("stop"))
        XCTAssertEqual(service.errorText, "Local bridge unavailable. Open Controls to start it.")
        XCTAssertFalse(service.stop())
    }
}
