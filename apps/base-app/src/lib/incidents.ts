import type { GroundIncident, GroundIncidentUpdate, IncidentUpdateType } from "../api/types";
import { delaySeconds } from "./board.ts";
import { utcSeconds } from "./format.ts";

/** Delays at or below this are normal link transit and are not called out. */
export const DELAY_NOTICE_S = 5;

export const UPDATE_LABELS: Record<IncidentUpdateType, string> = {
  created: "Incident began",
  acknowledged: "Acknowledged onboard",
  closed: "Closed onboard",
};

const time = (iso: string | null | undefined) => {
  const t = iso ? Date.parse(iso) : NaN;
  return Number.isNaN(t) ? null : t;
};

/** "2026-11-14 18:02:11 UTC", "--" for null, the raw text when unparseable. */
export function utcFull(iso: string | null | undefined): string {
  const t = time(iso);
  if (t === null) return iso || "--";
  return `${new Date(t).toISOString().slice(0, 10)} ${utcSeconds(t)} UTC`;
}

/** "45 s", "4 min 12 s", "1 h 3 min". */
export function formatDelay(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s} s`;
  if (s < 3600) return `${Math.floor(s / 60)} min ${s % 60} s`;
  return `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`;
}

/** "+4 min 12 s after event" when the ground received it noticeably late, else "". */
export function delayLabel(occurredAt: string, receivedAt: string): string {
  const d = delaySeconds(occurredAt, receivedAt);
  return d !== null && d > DELAY_NOTICE_S ? `+${formatDelay(d)} after event` : "";
}

/** Updates once each (by id), oldest onboard event first; unparseable times last. */
export function sortUpdates(updates: GroundIncidentUpdate[]): GroundIncidentUpdate[] {
  const unique = [...new Map(updates.map((u) => [u.id, u])).values()];
  const key = (u: GroundIncidentUpdate) => time(u.occurred_at) ?? Infinity;
  return unique.sort((a, b) => key(a) - key(b));
}

/** Incidents once each (by ship and id), newest began_at first; not yet begun (null) last. */
export function sortIncidents(incidents: GroundIncident[]): GroundIncident[] {
  const unique = [...new Map(incidents.map((i) => [`${i.ship_id}|${i.id}`, i])).values()];
  const key = (i: GroundIncident) => time(i.began_at) ?? -Infinity;
  return unique.sort((a, b) => key(b) - key(a));
}
