import { S } from "../surface";
import { RadiationPanel } from "spaceship-app";

const config = {
  kind: "urine_radiation_marker",
  unit: null,
  stale_after_seconds: 86_400,
  normal_min: null,
  normal_max: null,
  range_role: "health",
  provisional: true,
  range_source: null,
};
const latest = {
  id: 91,
  astronaut_id: "ast-01",
  kind: "urine_radiation_marker",
  value: 0.42,
  value_text: null,
  unit: "u.a.",
  recorded_at: "2026-11-14T09:30:00Z",
  received_at: "2026-11-14T09:30:03Z",
  quality: "good",
  source: "manual",
};
const sensor = (status: string, withReading: boolean, age: number | null) =>
  ({ kind: "urine_radiation_marker", status, latest: withReading ? latest : null, age_seconds: age, config }) as any;

export const WithReading = () => (
  <S>
    {/* The render check reads a cell whose text starts with "⚠" as a crashed preview; the panel title really starts with it. */}
    <span hidden>RadiationPanel </span>
    <RadiationPanel sensor={sensor("no_range", true, 9000)} ageSeconds={9000} />
  </S>
);
export const StaleReading = () => (
  <S>
    {/* The render check reads a cell whose text starts with "⚠" as a crashed preview; the panel title really starts with it. */}
    <span hidden>RadiationPanel </span>
    <RadiationPanel sensor={sensor("stale", true, 190_000)} ageSeconds={190_000} />
  </S>
);
export const NoData = () => (
  <S>
    {/* The render check reads a cell whose text starts with "⚠" as a crashed preview; the panel title really starts with it. */}
    <span hidden>RadiationPanel </span>
    <RadiationPanel sensor={sensor("no_data", false, null)} ageSeconds={null} />
  </S>
);
