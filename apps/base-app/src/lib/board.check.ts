// Self-check for lib/board.ts. Run: node src/lib/board.check.ts
import type { Link, ReadingStatus, SensorKind, SensorStatus } from "../api/types";
import {
  addToLedger,
  alertSerial,
  batchSerial,
  cascadeFrames,
  cellView,
  delaySeconds,
  linkState,
  rowState,
  shownStatus,
} from "./board.ts";
import { niceScale } from "./chart.ts";

function eq(actual: unknown, expected: unknown, what: string): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${what}: ${JSON.stringify(actual)} != ${JSON.stringify(expected)}`);
  }
}

function sensor(
  kind: SensorKind,
  status: ReadingStatus,
  value: number | null,
  min: number | null,
  max: number | null,
  role: "health" | "sample_validity" = "health",
): SensorStatus {
  return {
    kind,
    status,
    age_seconds: value === null ? null : 12,
    latest:
      value === null
        ? null
        : {
            id: 1,
            astronaut_id: "a",
            kind,
            value,
            value_text: null,
            unit: "",
            recorded_at: "",
            received_at: "",
            quality: "good",
            source: "manual",
            ground_received_at: "",
          },
    config: {
      kind,
      unit: null,
      stale_after_seconds: 300,
      normal_min: min,
      normal_max: max,
      range_role: role,
      provisional: true,
      range_source: null,
    },
  };
}

const high = sensor("heart_rate", "alert", 112, 60, 100);
const low = sensor("spo2", "alert", 90, 95, 100);
const ok = sensor("urine_ph", "normal", 6.2, 4.6, 8);
const old = sensor("urine_salinity", "stale", 24.3, null, null);
const none = sensor("muscle_density", "no_data", null, null, null);
const temp = sensor("urine_temperature", "alert", 39.2, 32, 38, "sample_validity");
const rad = sensor("urine_radiation_marker", "no_range", 1, null, null);

// Cells: words for every state, no invented values, radiation never shows its value.
eq(cellView(high, false), { text: "112", tone: "alert", note: "High" }, "cell high");
eq(cellView(low, false).note, "Low", "cell low");
eq(cellView(ok, false), { text: "6.2", tone: "plain", note: "" }, "cell ok");
eq(cellView(old, false), { text: "24.3", tone: "stale", note: "Old data" }, "cell stale");
eq(cellView(none, false), { text: "--", tone: "muted", note: "No data" }, "cell none");
eq(cellView(sensor("urine_salinity", "no_range", 20, null, null), false).note, "No range", "cell no range");
eq(cellView(temp, false).tone, "stale", "sample validity is not a health alert");
eq(cellView(rad, false).text, "Possible exposure", "radiation wording");
eq(cellView(high, true).tone, "stale", "offline shows stale");

// Rows.
eq(rowState([high, ok], false), "alert", "row alert");
eq(rowState([ok, old], false), "stale", "row stale");
eq(rowState([ok, none], false), "clear", "row clear");
eq(rowState([none], false), "empty", "row empty");
eq(rowState([temp, ok], false), "clear", "sample validity row");
eq(rowState([high], true), "stale", "row offline");
eq(shownStatus(none, true), "no_data", "offline keeps no data");

// Link.
const link: Link = {
  ship_id: "ship-01",
  last_batch_sent_at: "2026-11-14T18:02:15Z",
  last_batch_received_at: "2026-11-14T18:02:19Z",
  seconds_since_last_batch: 4,
  batches_received: 1284,
  readings_received: 5000,
};
eq(linkState(link, 4, false), "ok", "link ok");
eq(linkState(link, 20, false), "late", "link late");
eq(linkState(link, 90, false), "lost", "link lost");
eq(linkState(link, 4, true), "unreachable", "link unreachable");
eq(linkState({ ...link, last_batch_received_at: null, seconds_since_last_batch: null }, null, false), "no_batch", "no batch");
eq(linkState(null, null, false), "unknown", "link unknown");

// Serials and delay.
eq(alertSerial(412), "A-0412", "alert serial");
eq(alertSerial(123456), "A-123456", "long serial");
eq(batchSerial(7), "L-0007", "batch serial");
eq(delaySeconds("2026-11-14T18:02:10Z", "2026-11-14T18:02:19Z"), 9, "delay");
eq(delaySeconds("x", "2026-11-14T18:02:19Z"), null, "bad delay");

// Ledger: first snapshot has unknown content; a new batch adds deltas; same batch is ignored.
let ledger = addToLedger([], null, link);
eq(ledger[0].batches, null, "first snapshot");
const next = { ...link, last_batch_received_at: "2026-11-14T18:02:24Z", batches_received: 1286, readings_received: 5008 };
ledger = addToLedger(ledger, link, next);
eq([ledger[0].batch, ledger[0].batches, ledger[0].readings], [1286, 2, 8], "ledger delta");
eq(addToLedger(ledger, next, next).length, 2, "same batch ignored");
eq(addToLedger([], null, { ...link, last_batch_received_at: null }).length, 0, "no batch, no entry");
eq(addToLedger([], next, { ...link, last_batch_received_at: "2026-11-14T19:00:00Z", batches_received: 1 })[0].batches, null, "counter reset");

// Cascade: changed positions only, ends on target, bounded length.
eq(cascadeFrames("71", "71"), [], "no change");
const f = cascadeFrames(" 71", "112");
eq(f[f.length - 1], "112", "ends on target");
eq(f.length, 4, "frames = changed + 1");
for (const s of f) eq(s.length, 3, "fixed width");
eq(cascadeFrames("120", "125").every((s) => s.startsWith("12")), true, "unchanged chars stay");
eq(cascadeFrames("A", "ABCDEFGHIJKLMNOP").length, 8, "capped frames");
eq(cascadeFrames("ALERT", "NO ALERTS").slice(-1)[0], "NO ALERTS", "text target");

// Chart scale: round ticks only, SpO2 axis never above 100.
const round = (t: number[]) => t.every((v) => Number.isInteger(v * 2));
const hr = niceScale([71, 127.2, 88], [60, 100]);
eq(round(hr.ticks), true, "round hr ticks");
eq([hr.ticks[0] <= 60, hr.ticks[hr.ticks.length - 1] >= 127.2], [true, true], "hr covers data");
const sp = niceScale([91, 99, 100], [95, 100], 100);
eq(sp.hi, 100, "spo2 capped");
eq(Math.max(...sp.ticks) <= 100, true, "spo2 ticks capped");
eq(round(sp.ticks), true, "round spo2 ticks");
eq(niceScale([23.2, 28.8], [null, null]).ticks, [22, 24, 26, 28, 30], "salinity ticks");
eq(niceScale([6.2, 6.4], [4.6, 8]).ticks, [4, 6, 8], "ph ticks");
eq(niceScale([], [null]).ticks.length > 0, true, "empty scale");
eq(niceScale([97, 101.5], [95, 100], 100).hi >= 101.5, true, "cap never hides data");

console.log("board.check: ok");
