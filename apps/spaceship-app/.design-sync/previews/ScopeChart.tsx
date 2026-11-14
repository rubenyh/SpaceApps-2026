import { S } from "../surface";
import { ScopeChart } from "spaceship-app";

const END = Date.UTC(2026, 10, 14, 12, 0, 0);
const WINDOW = 15 * 60 * 1000;
// One reading every 30 s, a calm pulse with a short excursion above range.
const pulse = Array.from({ length: 30 }, (_, i) => ({
  t: END - WINDOW + i * 30_000 + 15_000,
  v: 72 + Math.round(6 * Math.sin(i / 3)) + (i > 20 && i < 25 ? 32 : 0),
}));

export const PulseWithRange = () => (
  <S>
    <ScopeChart points={pulse} windowStart={END - WINDOW} windowEnd={END} normalMin={50} normalMax={100} label="PULSO" emptyText="SIN LECTURAS EN LOS ÚLTIMOS 15 MIN" />
  </S>
);
export const NoRangeGuides = () => (
  <S>
    <ScopeChart points={pulse.slice(0, 20)} windowStart={END - WINDOW} windowEnd={END} normalMin={null} normalMax={null} label="PULSO" emptyText="SIN LECTURAS EN LOS ÚLTIMOS 15 MIN" />
  </S>
);
export const Empty = () => (
  <S>
    <ScopeChart points={[]} windowStart={END - WINDOW} windowEnd={END} normalMin={94} normalMax={100} label="SpO₂" emptyText="SIN LECTURAS EN LOS ÚLTIMOS 15 MIN" />
  </S>
);
