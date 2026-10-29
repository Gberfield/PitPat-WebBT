// Literal port of integration/omarchy/gabe.pitpat/Model.js, including its JavaScript
// truthiness and number formatting. tests/fixtures/model-cases.json guards the two ports.
import Foundation

enum JSON: Equatable {
    case null, bool(Bool), number(Double), string(String), array([JSON]), object([String: JSON])

    static func parse(_ text: String) -> JSON? {
        guard let data = text.data(using: .utf8),
              let value = try? JSONSerialization.jsonObject(with: data, options: [.fragmentsAllowed]) else { return nil }
        return JSON(value)
    }

    init(_ value: Any) {
        switch value {
        case let n as NSNumber where CFGetTypeID(n) == CFBooleanGetTypeID(): self = .bool(n.boolValue)
        case let n as NSNumber: self = .number(n.doubleValue)
        case let s as String: self = .string(s)
        case let a as [Any]: self = .array(a.map(JSON.init))
        case let o as [String: Any]: self = .object(o.mapValues(JSON.init))
        default: self = .null
        }
    }

    var any: Any {
        switch self {
        case .null: return NSNull()
        case .bool(let b): return b
        case .number(let n): return n == n.rounded() && abs(n) < 1e15 ? Int(n) as Any : n
        case .string(let s): return s
        case .array(let a): return a.map(\.any)
        case .object(let o): return o.mapValues(\.any)
        }
    }

    subscript(key: String) -> JSON? {
        if case .object(let o) = self { return o[key] }
        return nil
    }

    var object: [String: JSON]? {
        if case .object(let o) = self { return o }
        return nil
    }
}

// A missing key is JavaScript's undefined.
extension Optional where Wrapped == JSON {
    var truthy: Bool {
        switch self {
        case .none, .null?, .bool(false)?: return false
        case .number(let n)?: return n != 0 && !n.isNaN
        case .string(let s)?: return !s.isEmpty
        default: return true
        }
    }

    // ToNumber, as used by arithmetic and relational comparison.
    var jsNumber: Double {
        switch self {
        case .none: return .nan
        case .null?: return 0
        case .bool(let b)?: return b ? 1 : 0
        case .number(let n)?: return n
        case .string(let s)?:
            let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
            return t.isEmpty ? 0 : Double(t) ?? .nan
        default: return .nan
        }
    }

    // String(value), as used by concatenation.
    var jsString: String {
        switch self {
        case .none: return "undefined"
        case .null?: return "null"
        case .bool(let b)?: return b ? "true" : "false"
        case .number(let n)?: return jsNumberString(n)
        case .string(let s)?: return s
        case .array?: return ""
        case .object?: return "[object Object]"
        }
    }

    func strictlyEquals(_ value: Double) -> Bool {
        if case .number(let n)? = self { return n == value }
        return false
    }
}

func jsNumberString(_ n: Double) -> String {
    if n.isNaN { return "NaN" }
    if n.isInfinite { return n > 0 ? "Infinity" : "-Infinity" }
    if n == 0 { return "0" }
    if n == n.rounded() && abs(n) < 1e21 { return String(format: "%.0f", n) }
    return "\(n)"
}

// Math.round: halves go toward +Infinity.
func jsRound(_ x: Double) -> Double {
    let f = x.rounded(.down)
    return x - f >= 0.5 ? f + 1 : f
}

// Number.prototype.toFixed: an exact tie picks the larger value, unlike printf.
func jsFixed(_ x: Double, _ digits: Int) -> String {
    if !x.isFinite { return jsNumberString(x) }
    let scale = pow(10, Double(digits)), y = abs(x) * scale
    if y < 9e15 && y.rounded(.down) + 0.5 == y {
        let n = y.rounded(.up), whole = Int(n / scale), frac = Int(n) - whole * Int(scale)
        let text = digits == 0 ? "\(whole)" : "\(whole)." + String(repeating: "0", count: digits - String(frac).count) + String(frac)
        return x < 0 ? "-" + text : text
    }
    return String(format: "%.\(digits)f", x)
}

struct ModelView: Equatable {
    var state, label, owner: String
    var canStartPause, canAdjust, canStop, canTakeControl: Bool
    var startText, speed, distance, calories, steps, duration, target: String
}

enum ModelError: Error { case invalidSpeed }

enum Model {
    static func targetUnits(_ mph: Double) throws -> Int {
        if !mph.isFinite { throw ModelError.invalidSpeed }
        return Int(min(6000, max(1000, jsRound(mph * 1.609344 * 10) * 100)))
    }

    static func duration(_ seconds: Double) -> String {
        let n = seconds.rounded(.down), h = (n / 3600).rounded(.down)
        let m = (n.truncatingRemainder(dividingBy: 3600) / 60).rounded(.down), s = n.truncatingRemainder(dividingBy: 60)
        let hours: JSON? = .number(h), minutes: JSON? = .number(m)
        return (hours.truthy ? jsNumberString(h) + "h " : "") + (minutes.truthy || hours.truthy ? jsNumberString(m) + "m " : "") + jsNumberString(s) + "s"
    }

    static func view(_ snapshot: JSON?, _ isOwner: Bool) -> ModelView {
        let s: JSON = snapshot.truthy ? snapshot! : .object([:])
        let m: JSON = s["metrics"].truthy ? s["metrics"]! : .object([:])
        let known = s["connected"].truthy && !s["stale"].truthy && m["state"] != nil
        let healthy = known && !s["fault_id"].truthy && !s["blocked"].truthy && !s["recovery"].truthy && !s["storage_fault"].truthy
            && !s["stopping"].truthy && s["session"]?["status"] != .string("interrupted")
        let states = ["Starting", "Walking", "Paused", "Stopped"]
        var named: String? = nil
        switch m["state"] {
        case .number(let n)? where n == n.rounded() && n >= 0 && n < 4: named = states[Int(n)]
        case .string(let t)? where ["0", "1", "2", "3"].contains(t): named = states[Int(t)!]
        default: break
        }
        let state = s["stopping"].truthy ? "Stopping" : s["connecting"].truthy ? "Connecting" : !s["available"].truthy ? "Application unavailable" :
            s["safety_available"] == .bool(false) ? "Safety unavailable" : !s["connected"].truthy ? "Disconnected" :
            !known || s["recovery"].truthy ? "Motion unknown" : named ?? "Motion unknown"
        let miles = m["unit_mode"].truthy ? 1 : 1.609344
        let target = s["target_speed"].truthy ? s["target_speed"].jsNumber : 1000
        return ModelView(
            state: state, label: (s["simulator"].truthy ? "SIMULATOR · " : "") + state,
            owner: isOwner ? "Tray controls motion" : s["owner_kind"].truthy ? s["owner_kind"].jsString + " controls motion · observing" : "No motion controller",
            canStartPause: isOwner && healthy && !m["state"].strictlyEquals(0), canAdjust: isOwner && healthy && !m["state"].strictlyEquals(0),
            canStop: s["connected"].truthy,
            canTakeControl: !isOwner && healthy && s["owner_present"].truthy && m["state"].strictlyEquals(3) && m["speed_raw"].strictlyEquals(0),
            startText: m["state"].strictlyEquals(1) ? "Pause" : "Start",
            speed: known ? jsFixed(m["speed_raw"].jsNumber / 1000 / miles, 2) + " mph" : "—",
            distance: known ? jsFixed(m["distance"].jsNumber / 1000 / miles, 3) + " mi" : "—",
            calories: known ? m["calories"].jsString + " Cal" : "—", steps: known ? m["steps"].jsString : "—",
            duration: known ? duration(m["duration"].jsNumber / 1000) : "—",
            target: jsFixed(target / 1000 / 1.609344, 2))
    }
}
