import type { Reading } from "../api/types";
import { SENSOR_LABELS, formatUtcDateTime, readingValueText, unitLabel } from "../lib/format";
import { ColorSwatch } from "./ColorSwatch";
import { QualityMark } from "./QualityMark";

interface Props {
  readings: Reading[];
}

/** Raw readings, newest first as the service returns them. */
export function ReadingsTable({ readings }: Props) {
  return (
    <div className="table-wrap">
      <table className="readings">
        <thead>
          <tr>
            <th scope="col">Captured (UTC)</th>
            <th scope="col">Sensor</th>
            <th scope="col" className="num">
              Value
            </th>
            <th scope="col">Unit</th>
            <th scope="col">Quality</th>
            <th scope="col">Source</th>
          </tr>
        </thead>
        <tbody>
          {readings.map((r) => (
            <tr key={r.id}>
              <td className="readings__dim">{formatUtcDateTime(r.recorded_at)}</td>
              <td className="readings__sensor">{SENSOR_LABELS[r.kind] ?? r.kind}</td>
              <td className="num">
                {r.kind === "urine_color" ? <ColorSwatch value={r.value_text} /> : readingValueText(r)}
              </td>
              <td className="readings__dim">{unitLabel(r.unit)}</td>
              <td>
                <QualityMark quality={r.quality} />
              </td>
              <td className="readings__dim">{r.source}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
