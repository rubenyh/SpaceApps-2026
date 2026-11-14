import type { Reading } from "../api/types";
import {
  QUALITY_LABELS,
  SENSOR_LABELS,
  formatUtcDateTime,
  readingValueText,
  unitLabel,
} from "../lib/format";
import { ColorSwatch } from "./ColorSwatch";

interface Props {
  readings: Reading[];
}

export function ReadingsTable({ readings }: Props) {
  return (
    <div className="table-wrap">
      <table className="readings">
        <thead>
          <tr>
            <th scope="col">CAPTURA (UTC)</th>
            <th scope="col">SENSOR</th>
            <th scope="col">VALOR</th>
            <th scope="col">UNIDAD</th>
            <th scope="col">CALIDAD</th>
            <th scope="col">ORIGEN</th>
          </tr>
        </thead>
        <tbody>
          {readings.map((r) => (
            <tr key={r.id} className={`quality--${r.quality}`}>
              <td>{formatUtcDateTime(r.recorded_at)}</td>
              <td>{SENSOR_LABELS[r.kind] ?? r.kind}</td>
              <td className="num">
                {r.kind === "urine_color" ? (
                  <ColorSwatch value={r.value_text} />
                ) : (
                  readingValueText(r)
                )}
              </td>
              <td>{unitLabel(r.unit)}</td>
              <td>{QUALITY_LABELS[r.quality] ?? r.quality}</td>
              <td>{r.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
