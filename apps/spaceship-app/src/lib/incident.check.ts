// Self-check for lib/incident.ts. Run: node src/lib/incident.check.ts
import type { Incident } from "../api/types";
import { ackLabels, defaultAcknowledger, groundLabel, guidanceMissing, ruleLabel } from "./incident.ts";

function eq(actual: unknown, expected: unknown, what: string): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${what}: ${JSON.stringify(actual)} != ${JSON.stringify(expected)}`);
  }
}

const base: Incident = {
  id: "i1", status: "open", astronaut_id: "ana", reported_by: null, began_at: "2026-11-14T12:00:00Z",
  closed_at: null, urgency: "immediate", action: "Act.", protocol_id: "p", steps: [], matched_rules: [],
  findings: [], data_notices: [], mission_procedures: [], missing_guidance: [], acknowledgments: [],
  events: [{ id: "e1", type: "created", occurred_at: "2026-11-14T12:00:00Z", acknowledged_by: null, delivered_at: null }],
  ground_delivery: "disabled",
};
const acked: Incident = {
  ...base,
  acknowledgments: [{ acknowledged_by: "ben", acknowledged_at: "2026-11-14T12:01:00Z" }],
  events: [
    ...base.events,
    { id: "e2", type: "acknowledged", occurred_at: "2026-11-14T12:01:00Z", acknowledged_by: "ben", delivered_at: null },
  ],
};

eq(ackLabels(base), ["Not acknowledged"], "not acked");
eq(ackLabels(acked), ["Acknowledged onboard by ben at 2026-11-14 12:01:00 UTC"], "acked");

eq(groundLabel(acked), "Ground delivery: not available (telemetry off)", "disabled");
eq(groundLabel({ ...acked, ground_delivery: "queued" }), "Ground delivery: queued, not delivered", "queued");
const delivered: Incident = {
  ...acked,
  ground_delivery: "delivered",
  events: [
    { ...acked.events[0], delivered_at: "2026-11-14T12:00:05Z" },
    { ...acked.events[1], delivered_at: "2026-11-14T12:01:07Z" },
  ],
};
eq(groundLabel(delivered), "Delivered to ground 2026-11-14 12:01:07 UTC", "delivered latest");

// Acknowledgment and ground delivery never stand in for each other.
for (const i of [base, acked, delivered, { ...acked, ground_delivery: "queued" as const }]) {
  for (const a of ackLabels(i)) if (/ground|deliver/i.test(a)) throw new Error(`ack mentions ground: ${a}`);
  if (/acknowledg/i.test(groundLabel(i))) throw new Error(`ground mentions ack: ${groundLabel(i)}`);
}
eq(ackLabels(delivered), ["Acknowledged onboard by ben at 2026-11-14 12:01:00 UTC"], "delivery is not an ack");
eq(ackLabels({ ...base, ground_delivery: "delivered" }), ["Not acknowledged"], "delivered but not acked");

eq(guidanceMissing(base), false, "guidance loaded");
eq(guidanceMissing({ ...base, missing_guidance: ["x"] }), true, "missing_guidance");
eq(guidanceMissing({ ...base, mission_procedures: [{ title: "EMER-1", loaded: false }] }), true, "procedure not loaded");

eq(ruleLabel({ rule_id: "r1", protocol_id: "resp", protocol_version: "1.2", urgency: "immediate" }), "r1 · resp@1.2", "rule");

const crew = [{ id: "ana", display_name: "Ana", created_at: "" }, { id: "ben", display_name: "Ben", created_at: "" }];
eq(defaultAcknowledger(crew, "ana"), "ben", "other crewmate");
eq(defaultAcknowledger(crew.slice(0, 1), "ana"), "ana", "alone");
eq(defaultAcknowledger([], "ana"), "", "no crew");

console.log("incident.check: ok");
