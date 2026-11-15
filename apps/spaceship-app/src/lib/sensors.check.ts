// Self-check for lib/sensors.ts. Run: node src/lib/sensors.check.ts
import type { ReadingStatus, SensorKind, SensorStatus } from "../api/types";
import { aggregateUrine, isSimulatedSource } from "./sensors.ts";

function eq(actual: unknown, expected: unknown, what: string): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${what}: ${JSON.stringify(actual)} != ${JSON.stringify(expected)}`);
  }
}

eq(
  ["simulated", "demo", "simulated:urine", "manual", "serial:pulseox", "Simulated", "", null, undefined].map(
    isSimulatedSource,
  ),
  [true, true, true, false, false, false, false, false, false],
  "isSimulatedSource",
);

function s(kind: SensorKind, status: ReadingStatus, role: "health" | "sample_validity" = "health"): SensorStatus {
  return {
    kind,
    status,
    latest: null,
    age_seconds: null,
    config: {
      kind,
      unit: null,
      stale_after_seconds: null,
      normal_min: null,
      normal_max: null,
      range_role: role,
      provisional: true,
      range_source: null,
    },
  };
}

eq(aggregateUrine([null, s("urine_ph", "normal")]), "normal", "missing never hides present");
eq(aggregateUrine([s("urine_ph", "stale"), s("urine_salinity", "future")]), "future", "future beats stale");
eq(aggregateUrine([s("urine_ph", "future"), s("urine_salinity", "alert")]), "alert", "alert beats future");
eq(aggregateUrine([s("urine_temperature", "alert", "sample_validity")]), "normal", "validity is not health");
eq(aggregateUrine([]), "no_data", "empty");

console.log("sensors.check: ok");
