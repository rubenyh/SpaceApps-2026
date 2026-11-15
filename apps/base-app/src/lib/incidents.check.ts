// Self-check for lib/incidents.ts. Run: node src/lib/incidents.check.ts
import type { GroundIncident, GroundIncidentUpdate } from "../api/types";
import { delayLabel, formatDelay, sortIncidents, sortUpdates, utcFull } from "./incidents.ts";

function eq(actual: unknown, expected: unknown, what: string): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${what}: ${JSON.stringify(actual)} != ${JSON.stringify(expected)}`);
  }
}

const upd = (id: string, type: GroundIncidentUpdate["type"], occurred_at: string, received_at: string): GroundIncidentUpdate => ({
  id,
  type,
  occurred_at,
  received_at,
  acknowledged_by: type === "acknowledged" ? "astro-01" : null,
});

// Link outage: both updates arrive in one batch after reconnection, ack listed before created.
const created = upd("e1", "created", "2026-11-14T18:00:00Z", "2026-11-14T18:06:30Z");
const acked = upd("e2", "acknowledged", "2026-11-14T18:02:18Z", "2026-11-14T18:06:30Z");
eq(sortUpdates([acked, created, acked]).map((u) => u.id), ["e1", "e2"], "updates once, by event time");
eq(sortUpdates([upd("x", "closed", "bad", "bad"), created]).map((u) => u.id), ["e1", "x"], "bad time last");

// Delay labels: outage visible, normal transit silent.
eq(delayLabel(acked.occurred_at, acked.received_at), "+4 min 12 s after event", "outage delay");
eq(delayLabel("2026-11-14T18:00:00Z", "2026-11-14T18:00:03Z"), "", "normal transit hidden");
eq(delayLabel("2026-11-14T18:00:00Z", "2026-11-14T18:00:06Z"), "+6 s after event", "just over threshold");
eq(delayLabel("x", "2026-11-14T18:00:06Z"), "", "bad time");
eq(formatDelay(3780), "1 h 3 min", "hours");

eq(utcFull("2026-11-14T18:02:11Z"), "2026-11-14 18:02:11 UTC", "utc stamp");
eq(utcFull(null), "--", "null stamp");

// Incidents: newest began_at first, one per (ship, id), not-yet-begun last.
const inc = (id: string, began_at: string | null, ship_id = "ship-01"): GroundIncident => ({
  ship_id,
  id,
  astronaut_id: null,
  began_at,
  urgency: "immediate",
  protocol_id: null,
  protocol_version: null,
  matched_rules: [],
  action: null,
  acknowledgments: [],
  updates: [],
});
eq(
  sortIncidents([inc("a", "2026-11-14T10:00:00Z"), inc("n", null), inc("b", "2026-11-14T12:00:00Z"), inc("a", "2026-11-14T10:00:00Z")]).map((i) => i.id),
  ["b", "a", "n"],
  "incident order",
);
eq(sortIncidents([inc("a", null, "s1"), inc("a", null, "s2")]).length, 2, "same id, two ships");

console.log("incidents.check: ok");
