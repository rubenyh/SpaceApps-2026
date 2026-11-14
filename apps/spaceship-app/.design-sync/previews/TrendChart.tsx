import { S } from "../surface";
import { TrendChart } from "spaceship-app";

const DAY = 86_400_000;
const END = Date.UTC(2026, 10, 14, 12, 0, 0);
const ph = [6.1, 6.3, 5.9, 6.4, 6.8, 7.1, 6.6, 6.2, 5.4, 5.8, 6.0, 6.3, 6.5, 6.2].map((v, i) => ({
  t: END - (13 - i) * DAY - 4 * 3_600_000,
  v,
}));
const muscle = [62.1, 61.8, 61.0, 60.4, 60.4, 59.2].map((v, i) => ({ t: END - (5 - i) * 7 * DAY, v }));

export const FourteenDaysWithRange = () => (
  <S>
    <TrendChart points={ph} start={END - 14 * DAY} end={END} normalMin={5.5} normalMax={7} label="pH, 14 días" emptyText="SIN LECTURAS EN 14 DÍAS" />
  </S>
);
export const WeeksWithoutRange = () => (
  <S>
    <TrendChart points={muscle} start={END - 42 * DAY} end={END} label="Densidad muscular" emptyText="SIN LECTURAS EN ESTE PERIODO" />
  </S>
);
export const Empty = () => (
  <S>
    <TrendChart points={[]} start={END - 14 * DAY} end={END} label="SALINIDAD, 14 días" emptyText="SIN LECTURAS EN 14 DÍAS" />
  </S>
);
