import type { SensorStatus } from "../api/types";
import { formatAge } from "../lib/format";
import { StateIcon, StatusPill } from "./StatusPill";

interface Props {
  sensor: SensorStatus | null;
  ageSeconds: number | null;
}

/**
 * Urine radiation marker. An indirect marker, NOT dosimetry: never a dose, a dose unit
 * or a "normal" look. Any reading is only ever shown as
 * "Possible exposure, needs confirmation".
 */
export function RadiationPanel({ sensor, ageSeconds }: Props) {
  const reading = sensor?.latest ?? null;
  return (
    <section className={`radiation${reading ? " radiation--flag" : ""}`}>
      <div className="radiation__head">
        <strong>Radiation marker</strong>
        {reading ? (
          <span className="pill pill--doubtful">
            <StateIcon state="doubtful" />
            Possible exposure, needs confirmation
          </span>
        ) : (
          <StatusPill state="no_data" />
        )}
      </div>
      {reading ? (
        <span className="radiation__age">
          Last data {formatAge(ageSeconds)}
          {sensor?.status === "stale" ? " · old data" : ""}
        </span>
      ) : null}
      <div className="radiation__warning">
        <StateIcon state="doubtful" size={18} />
        <span>
          It is an <strong>indirect indicator</strong>, not dosimetry: it does not measure dose. Any
          data is only shown as "Possible exposure, needs confirmation" by qualified
          personnel.
        </span>
      </div>
    </section>
  );
}
