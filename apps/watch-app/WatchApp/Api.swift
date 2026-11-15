import Foundation

// Foundation only, so Checks/main.swift can compile it with swiftc on macOS.

struct Astronaut: Codable, Identifiable {
    let id: String
    let displayName: String
}

struct Reading: Codable {
    let value: Double?
    let valueText: String?
    let unit: String?
    let recordedAt: String
}

struct Sensor: Codable, Identifiable {
    let kind: String
    let status: String // normal | alert | stale | no_data | no_range, straight from the server
    let latest: Reading?
    let ageSeconds: Int?
    var id: String { kind }
}

struct Status: Codable {
    let astronautId: String
    let sensors: [Sensor]
}

struct Incident: Codable {
    let id: String
    let astronautId: String
}

struct ApiError: Error {
    let message: String
}

enum Api {
    static func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    static func get<T: Decodable>(_ base: String, _ path: String, as: T.Type = T.self) async throws -> T {
        guard let url = URL(string: base + path) else { throw ApiError(message: "URL inválida") }
        return try decoder().decode(T.self, from: try await send(URLRequest(url: url)))
    }

    static func sos(_ base: String, astronautID: String) async throws {
        guard let url = URL(string: base + "/assistant/messages") else { throw ApiError(message: "URL inválida") }
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        // Only "SOS": other text can route to the symptom interpreter.
        req.httpBody = try JSONSerialization.data(withJSONObject: ["message": "SOS", "astronaut_id": astronautID])
        _ = try await send(req)
    }

    private static func send(_ req: URLRequest) async throws -> Data {
        var req = req
        req.timeoutInterval = 8
        let (data, resp) = try await URLSession.shared.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(code) else { throw ApiError(message: "HTTP \(code)") }
        return data
    }
}

enum Labels {
    static let names = [
        "heart_rate": "Pulso",
        "spo2": "SpO₂",
        "muscle_density": "Densidad muscular",
        "urine_ph": "pH orina",
        "urine_salinity": "Salinidad orina",
        "urine_color": "Color orina",
        "urine_temperature": "Temp. orina",
        "urine_radiation_marker": "Radiación orina",
    ]

    static func name(_ kind: String) -> String { names[kind] ?? kind }

    static func value(_ r: Reading?) -> String {
        guard let r else { return "—" }
        if let v = r.value {
            let n = String(format: "%g", v)
            return r.unit.map { "\(n) \($0)" } ?? n
        }
        return r.valueText ?? "—"
    }

    static func state(_ status: String) -> String {
        switch status {
        case "no_data": return "SIN DATOS"
        case "stale": return "OBSOLETO"
        case "alert": return "ALERTA"
        default: return ""
        }
    }

    static func age(_ seconds: Int?) -> String {
        guard let s = seconds else { return "" }
        if s < 60 { return "hace \(s) s" }
        if s < 3600 { return "hace \(s / 60) min" }
        if s < 86400 { return "hace \(s / 3600) h" }
        return "hace \(s / 86400) d"
    }

    static func date(_ iso: String) -> Date? {
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = f.date(from: iso) { return d }
        f.formatOptions = [.withInternetDateTime]
        return f.date(from: iso)
    }

    static func clock(_ date: Date?, timeZone: TimeZone = .current) -> String {
        guard let date else { return "" }
        let f = DateFormatter()
        f.dateFormat = "HH:mm"
        f.timeZone = timeZone
        return f.string(from: date)
    }

    static func clock(_ iso: String?, timeZone: TimeZone = .current) -> String {
        clock(iso.flatMap(date), timeZone: timeZone)
    }
}
