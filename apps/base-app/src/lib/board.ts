import type { Link, ReadingStatus, SensorKind, SensorStatus } from "../api/types";
import { formatDuration, readingValueText } from "./format.ts";

// --- Status ---------------------------------------------------------------

/** Status to draw: while ground-api is unreachable, known values are shown as stale. */
export function shownStatus(s: SensorStatus | null | undefined, offline: boolean): ReadingStatus {
  const st = s?.status ?? "no_data";
  return offline && st !== "no_data" ? "stale" : st;
}

/** Sample-validity ranges and the radiation marker never count as health alerts. */
export function isHealthAlert(s: SensorStatus, offline: boolean): boolean {
  return (
    shownStatus(s, offline) === "alert" &&
    s.config.range_role === "health" &&
    s.kind !== "urine_radiation_marker"
  );
}

export type RowState = "alert" | "stale" | "clear" | "empty";

export const ROW_LABELS: Record<RowState, string> = {
  alert: "Alerta",
  stale: "Dato viejo",
  clear: "Sin alertas",
  empty: "Sin datos",
};

/** Worst state of one astronaut: health alert > stale > some data > nothing. */
export function rowState(sensors: SensorStatus[], offline: boolean): RowState {
  if (sensors.some((s) => isHealthAlert(s, offline))) return "alert";
  const shown = sensors.map((s) => shownStatus(s, offline));
  if (shown.includes("stale")) return "stale";
  return shown.some((st) => st !== "no_data") ? "clear" : "empty";
}

export function rangeSide(s: SensorStatus): "high" | "low" | null {
  const v = s.latest?.value;
  const { normal_min: min, normal_max: max } = s.config;
  if (v === null || v === undefined) return null;
  if (max !== null && v > max) return "high";
  if (min !== null && v < min) return "low";
  return null;
}

export type CellTone = "alert" | "stale" | "plain" | "muted";

export interface CellView {
  /** What the flap shows. "--" when there is no value. */
  text: string;
  tone: CellTone;
  /** Word for the state; empty for an in-range value. */
  note: string;
}

/** One board/sensor cell. Never invents a value; the radiation marker never shows its value. */
export function cellView(s: SensorStatus | null | undefined, offline: boolean): CellView {
  const st = shownStatus(s, offline);
  if (!s || !s.latest || st === "no_data") return { text: "--", tone: "muted", note: "Sin dato" };
  if (s.kind === "urine_radiation_marker") {
    return { text: "Posible exposición", tone: st === "stale" ? "stale" : "plain", note: st === "stale" ? "Dato viejo" : "Requiere confirmación" };
  }
  const text = readingValueText(s.latest);
  if (st === "stale") return { text, tone: "stale", note: "Dato viejo" };
  if (st === "no_range") return { text, tone: "plain", note: "Sin rango" };
  if (st === "alert") {
    if (s.config.range_role === "sample_validity") return { text, tone: "stale", note: "Muestra no válida" };
    const side = rangeSide(s);
    return { text, tone: "alert", note: side === "high" ? "Alto" : side === "low" ? "Bajo" : "Fuera de rango" };
  }
  return { text, tone: "plain", note: "" };
}

/** Age measured at ground that keeps ticking between polls. */
export function liveAge(ageAtPoll: number | null | undefined, updatedAt: number | null, now: number): number | null {
  if (ageAtPoll === null || ageAtPoll === undefined) return null;
  return ageAtPoll + (updatedAt === null ? 0 : Math.max(0, (now - updatedAt) / 1000));
}

/** Youngest sensor age in a row (age measured at ground), or null when nothing arrived. */
export function freshestAge(sensors: SensorStatus[]): number | null {
  const ages = sensors.map((s) => s.age_seconds).filter((a): a is number => a !== null);
  return ages.length ? Math.min(...ages) : null;
}

export const BOARD_KINDS: SensorKind[] = ["heart_rate", "spo2", "urine_ph", "urine_salinity", "muscle_density"];

// --- Link -----------------------------------------------------------------

// shortcut: fixed thresholds for a publisher that sends every few seconds; move to config if the cadence changes.
export const LINK_LATE_S = 15;
export const LINK_LOST_S = 60;

export type LinkState = "unknown" | "unreachable" | "no_batch" | "ok" | "late" | "lost";

export function linkState(link: Link | null, sinceSeconds: number | null, unreachable: boolean): LinkState {
  if (unreachable) return "unreachable";
  if (!link) return "unknown";
  if (link.last_batch_received_at === null || sinceSeconds === null) return "no_batch";
  if (sinceSeconds >= LINK_LOST_S) return "lost";
  if (sinceSeconds >= LINK_LATE_S) return "late";
  return "ok";
}

/** Short state words for the top bar (stable between ticks). */
export const LINK_HEADLINES: Record<LinkState, string> = {
  unknown: "Consultando",
  unreachable: "Tierra sin respuesta",
  no_batch: "Sin lotes todavía",
  ok: "Enlace al día",
  late: "Lote retrasado",
  lost: "Sin enlace",
};

/** Plain words for the link state, with the time without data. */
export function linkWords(state: LinkState, sinceSeconds: number | null): string {
  switch (state) {
    case "unknown":
      return "Consultando servicio de tierra";
    case "unreachable":
      return "Servicio de tierra sin respuesta";
    case "no_batch":
      return "Aún no ha llegado ningún lote";
    case "ok":
      return "Enlace al día";
    case "late":
      return `Lote retrasado: ${formatDuration(sinceSeconds ?? 0)} sin datos`;
    case "lost":
      return `Sin lotes desde hace ${formatDuration(sinceSeconds ?? 0)}`;
  }
}

// --- Serials --------------------------------------------------------------

/** Stable alert serial from the onboard reading id, e.g. 412 -> "A-0412". */
export const alertSerial = (readingId: number) => `A-${String(readingId).padStart(4, "0")}`;

/** Batch serial from ground's running batch count, e.g. 1284 -> "L-1284". */
export const batchSerial = (n: number) => `L-${String(n).padStart(4, "0")}`;

/** Seconds between capture onboard and storage at ground, or null. */
export function delaySeconds(recordedAt: string, groundReceivedAt: string): number | null {
  const a = Date.parse(recordedAt);
  const b = Date.parse(groundReceivedAt);
  return Number.isNaN(a) || Number.isNaN(b) ? null : Math.max(0, (b - a) / 1000);
}

// --- Batch ledger -----------------------------------------------------------

export interface LedgerEntry {
  /** Ground batch count when this batch was observed. */
  batch: number;
  /** Batches since the previous observation (>1: several arrived between polls). null: first snapshot. */
  batches: number | null;
  /** Readings that arrived with them. null: first snapshot, content unknown. */
  readings: number | null;
  sentAt: string | null;
  receivedAt: string;
}

/**
 * Add a /link snapshot to the ledger (newest first) when a new batch arrived since `prev`.
 * The contract has no batch list, so the console records what it observes between polls.
 */
export function addToLedger(ledger: LedgerEntry[], prev: Link | null, next: Link, max = 12): LedgerEntry[] {
  if (!next.last_batch_received_at) return ledger;
  if (prev && prev.last_batch_received_at === next.last_batch_received_at) return ledger;
  // No usable previous snapshot (first poll, or ground restarted and its counters reset).
  const base = prev && prev.batches_received <= next.batches_received ? prev : null;
  const entry: LedgerEntry = {
    batch: next.batches_received,
    batches: base ? next.batches_received - base.batches_received : null,
    readings: base ? next.readings_received - base.readings_received : null,
    sentAt: next.last_batch_sent_at,
    receivedAt: next.last_batch_received_at,
  };
  return [entry, ...ledger].slice(0, max);
}

// --- Split-flap cascade -----------------------------------------------------

const FLAP_CHARS = " ABCDEFGHIJKLMNOPQRSTUVWXYZÁÉÍÓÚÑ0123456789.-:#";

/**
 * Intermediate strings for a split-flap change from `from` to `to`.
 * Only changed positions flip; they settle left to right. The last frame is `to`.
 * At most `maxFrames` frames so the whole cascade stays short.
 */
export function cascadeFrames(from: string, to: string, maxFrames = 8): string[] {
  const n = Math.max(from.length, to.length);
  const a = from.padEnd(n);
  const b = to.padEnd(n);
  const changed: number[] = [];
  for (let i = 0; i < n; i++) if (a[i] !== b[i]) changed.push(i);
  if (changed.length === 0) return [];
  const frames = Math.min(maxFrames, changed.length + 1);
  const settle = new Map(changed.map((i, r) => [i, 1 + Math.ceil(((r + 1) * (frames - 1)) / changed.length)]));
  const out: string[] = [];
  for (let k = 1; k < frames; k++) {
    let s = "";
    for (let i = 0; i < n; i++) {
      const at = settle.get(i);
      if (at === undefined || k >= at) s += b[i];
      else s += FLAP_CHARS[(Math.max(0, FLAP_CHARS.indexOf(a[i].toUpperCase())) + k) % FLAP_CHARS.length];
    }
    out.push(s);
  }
  out.push(to);
  return out;
}
