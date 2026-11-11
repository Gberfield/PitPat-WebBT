import Foundation
import XCTest
@testable import PitPatMenuBar

final class StatusDialogTests: XCTestCase {
    func testAuthorizedFixtureDialogs() throws {
        var url = URL(fileURLWithPath: #filePath)
        for _ in 0..<6 { url.deleteLastPathComponent() }
        let fixture = try XCTUnwrap(JSON.parse(String(contentsOf: url.appendingPathComponent("tests/fixtures/model-cases.json"), encoding: .utf8)))
        guard case .array(let cases)? = fixture["cases"] else { return XCTFail("no cases") }
        let required: Set<String> = ["stopped-owner", "walking-owner", "stale", "fault", "simulator-walking"]
        var seen = Set<String>()
        for item in cases {
            let name = item["name"].jsString
            let view = try XCTUnwrap(item["view"], name)
            let expected = "\(view["label"].jsString). \(view["speed"].jsString), \(view["distance"].jsString), \(view["duration"].jsString)."
            XCTAssertEqual(statusDialog(authorized: true, model: Model.view(item["snapshot"], item["isOwner"] == .bool(true))), expected, name)
            seen.insert(name)
        }
        XCTAssertTrue(required.isSubset(of: seen))
    }

    func testUnauthorizedDiscardsEvenAPreviouslyWalkingSnapshot() {
        let model = Model.view(.object(["available": .bool(true), "connected": .bool(true), "metrics": .object(["state": .number(1)])]), true)
        XCTAssertEqual(statusDialog(authorized: false, model: model), "PitPat isn't connected to its services.")
    }
}
