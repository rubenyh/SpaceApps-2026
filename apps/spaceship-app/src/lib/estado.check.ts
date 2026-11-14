// Self-check for lib/estado.ts. Run: node src/lib/estado.check.ts
import type { AstronautStatus, ReadingStatus, SensorKind, SensorStatus } from "../api/types";
import { explain, healthAlerts, rangeSide, shownStatus, tabFlags, trackPercent } from "./estado.ts";

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
          },
    config: {
      kind,
      unit: null,
      stale_after_seconds: null,
      normal_min: min,
      normal_max: max,
      range_role: role,
      provisional: true,
      range_source: null,
    },
  };
}

// Marker position, as in the mockups: 112 on 40–160 is 60 %, 97 on 85–100 is 80 %.
eq(trackPercent(112, [40, 160]), 60, "pulse marker");
eq(trackPercent(97, [85, 100]), 80, "spo2 marker");
eq(trackPercent(200, [40, 160]), 100, "clamped high");
eq(trackPercent(10, [40, 160]), 0, "clamped low");
eq(trackPercent(5, [5, 5]), 0, "empty scale");

const high = sensor("heart_rate", "alert", 112, 60, 100);
const low = sensor("spo2", "alert", 90, 95, 100);
const temp = sensor("urine_temperature", "alert", 39.2, 32, 38, "sample_validity");
const radiation = sensor("urine_radiation_marker", "alert", 1, 0, 0);
const ok = sensor("urine_ph", "normal", 6.1, 4.6, 8);
const none = sensor("muscle_density", "no_data", null, null, null);

eq(rangeSide(high), "high", "side high");
eq(rangeSide(low), "low", "side low");
eq(rangeSide(ok), "in", "side in");
eq(rangeSide(none), null, "side unknown");

const status: AstronautStatus = {
  astronaut_id: "a",
  generated_at: "",
  sensors: [high, low, none, ok, temp, radiation],
};
// Sample validity and the radiation marker never reach the health banner.
eq(healthAlerts(status).map((s) => s.kind), ["heart_rate", "spo2"], "health alerts");
eq(healthAlerts(null), [], "no status");

eq(shownStatus(high, false), "alert", "online keeps status");
eq(shownStatus(high, true), "stale", "offline shows stale");
eq(shownStatus(none, true), "no_data", "offline keeps no data");
eq(shownStatus(null, false), "no_data", "missing sensor");

eq(explain(high, false), "Por encima de lo normal", "explain high");
eq(explain(low, false), "Por debajo de lo normal", "explain low");
eq(explain(ok, false), "Dentro de lo normal", "explain normal");
eq(explain(none, true), "Todavía no hay lecturas", "explain no data");
eq(explain(high, true), "Último valor recibido: estaba alto", "explain offline");

// Tabs flag problems only; a doubtful sample (temperature) is not a health alert.
eq(tabFlags(status), { vitales: "alert", musculo: null, orina: null }, "tab flags");
eq(
  tabFlags({ ...status, sensors: [sensor("urine_ph", "stale", 6.1, 4.6, 8), ok] }).orina,
  "stale",
  "stale tab",
);
eq(tabFlags(null), { vitales: null, musculo: null, orina: null }, "no status flags");

console.log("estado.check: ok");
