import { S } from "../surface";
import { ReadingsTable } from "spaceship-app";

const row = (id: number, kind: string, value: number | null, unit: string, minute: number, extra = {}) => ({
  id,
  astronaut_id: "ast-01",
  kind,
  value,
  value_text: null,
  unit,
  recorded_at: `2026-11-14T11:${String(minute).padStart(2, "0")}:00Z`,
  received_at: `2026-11-14T11:${String(minute).padStart(2, "0")}:02Z`,
  quality: "good",
  source: "serial:pulse",
  ...extra,
});

const readings = [
  row(108, "heart_rate", 72, "bpm", 58),
  row(107, "spo2", 97, "%", 58),
  row(106, "urine_ph", 6.2, "pH", 41, { source: "manual" }),
  row(105, "urine_color", null, "hex", 41, { value_text: "#e8c84a", source: "manual" }),
  row(104, "urine_temperature", 31.5, "°C", 41, { quality: "suspect", source: "manual" }),
  row(103, "muscle_density", 1.058, "g/cm3", 20, { source: "manual" }),
  row(102, "heart_rate", 181, "bpm", 12, { quality: "bad" }),
];

export const MixedReadings = () => (
  <S>
    <ReadingsTable readings={readings as any} />
  </S>
);
export const SingleSensor = () => (
  <S>
    <ReadingsTable readings={readings.filter((r) => r.kind === "heart_rate" || r.kind === "spo2") as any} />
  </S>
);
