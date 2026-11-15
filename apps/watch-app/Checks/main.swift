import Foundation

// Self-check: swiftc WatchApp/Api.swift Checks/main.swift -o /tmp/watch-checks && /tmp/watch-checks

let sample = """
{"astronaut_id":"ast-02","generated_at":"2026-11-15T18:03:33.717274Z","sensors":[
 {"kind":"heart_rate","status":"alert","latest":{"value":104.0,"value_text":null,"unit":"bpm","recorded_at":"2026-11-15T18:03:33.105354Z","quality":"good"},"age_seconds":12,"config":{}},
 {"kind":"urine_color","status":"stale","latest":{"value":null,"value_text":"#E0C868","unit":"rgb_hex","recorded_at":"2026-11-15T17:40:00Z"},"age_seconds":1380,"config":{}},
 {"kind":"urine_radiation_marker","status":"no_data","latest":null,"age_seconds":null,"config":{}}
]}
"""

let status = try Api.decoder().decode(Status.self, from: Data(sample.utf8))
assert(status.astronautId == "ast-02")
assert(status.sensors.map(\.kind) == ["heart_rate", "urine_color", "urine_radiation_marker"])

let hr = status.sensors[0], color = status.sensors[1], rad = status.sensors[2]
assert(Labels.name(hr.kind) == "Pulso")
assert(Labels.value(hr.latest) == "104 bpm")
assert(Labels.state(hr.status) == "ALERTA")
assert(Labels.age(hr.ageSeconds) == "hace 12 s")
let utc = TimeZone(identifier: "UTC")!
assert(Labels.clock(hr.latest?.recordedAt, timeZone: utc) == "18:03")

assert(Labels.value(color.latest) == "#E0C868")
assert(Labels.state(color.status) == "OBSOLETO")
assert(Labels.age(color.ageSeconds) == "hace 23 min")
assert(Labels.clock(color.latest?.recordedAt, timeZone: utc) == "17:40")

assert(rad.latest == nil)
assert(Labels.value(rad.latest) == "—")
assert(Labels.state(rad.status) == "SIN DATOS")
assert(Labels.age(rad.ageSeconds) == "")
assert(Labels.clock(nil as String?) == "")

assert(Labels.state("normal") == "" && Labels.state("no_range") == "")
assert(Labels.age(3 * 3600) == "hace 3 h" && Labels.age(2 * 86400) == "hace 2 d")
assert(Labels.name("unknown_kind") == "unknown_kind")

let incidents = try Api.decoder().decode([Incident].self, from: Data(#"[{"id":"x","astronaut_id":"ast-01","urgency":"immediate"}]"#.utf8))
assert(incidents.first?.astronautId == "ast-01")

print("watch-app checks OK")
