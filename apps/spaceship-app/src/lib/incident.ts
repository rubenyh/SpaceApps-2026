import type { Astronaut, EvidenceFlag, Incident, MatchedRule } from "../api/types";
import { formatUtcDateTime } from "./format.ts";

/** Evidence quality labels shown on findings. */
export const EVIDENCE_FLAG_LABELS: Record<EvidenceFlag, string> = {
  simulated: "Simulated",
  stale: "Stale",
  missing: "Missing",
  poor_quality: "Poor quality",
};

/** "<rule_id> · <protocol_id>@<protocol_version>" */
export function ruleLabel(r: MatchedRule): string {
  return `${r.rule_id} · ${r.protocol_id}@${r.protocol_version}`;
}

/** Crew acknowledgment only. Never mentions ground. */
export function ackLabels(incident: Incident): string[] {
  if (incident.acknowledgments.length === 0) return ["Not acknowledged"];
  return incident.acknowledgments.map(
    (a) => `Acknowledged onboard by ${a.acknowledged_by} at ${formatUtcDateTime(a.acknowledged_at)} UTC`,
  );
}

/** Ground delivery only. Never mentions acknowledgment. */
export function groundLabel(incident: Incident): string {
  if (incident.ground_delivery === "disabled") return "Ground delivery: not available (telemetry off)";
  if (incident.ground_delivery === "queued") return "Ground delivery: queued, not delivered";
  const latest = incident.events
    .map((e) => e.delivered_at)
    .filter((t): t is string => t !== null)
    .sort((a, b) => Date.parse(a) - Date.parse(b))
    .pop();
  return latest ? `Delivered to ground ${formatUtcDateTime(latest)} UTC` : "Delivered to ground";
}

export function guidanceMissing(incident: Pick<Incident, "missing_guidance" | "mission_procedures">): boolean {
  return incident.missing_guidance.length > 0 || incident.mission_procedures.some((p) => !p.loaded);
}

/** Default acknowledger: a crewmate other than the affected astronaut when there is one. */
export function defaultAcknowledger(crew: Astronaut[], affected: string | null): string {
  return (crew.find((a) => a.id !== affected) ?? crew[0])?.id ?? "";
}

/** Ids not in `seen`. `seen` null is the first load: those were already open, so none are new. */
export function newIncidentIds(seen: ReadonlySet<string> | null, incidents: Incident[]): string[] {
  if (seen === null) return [];
  return incidents.map((i) => i.id).filter((id) => !seen.has(id));
}
