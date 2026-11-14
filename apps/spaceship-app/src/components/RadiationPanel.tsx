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
 * «Posible exposición, requiere confirmación».
 */
export function RadiationPanel({ sensor, ageSeconds }: Props) {
  const reading = sensor?.latest ?? null;
  return (
    <section className={`radiation${reading ? " radiation--flag" : ""}`}>
      <div className="radiation__head">
        <strong>Marcador de radiación</strong>
        {reading ? (
          <span className="pill pill--doubtful">
            <StateIcon state="doubtful" />
            Posible exposición, requiere confirmación
          </span>
        ) : (
          <StatusPill state="no_data" />
        )}
      </div>
      {reading ? (
        <span className="radiation__age">
          Último dato {formatAge(ageSeconds)}
          {sensor?.status === "stale" ? " · dato viejo" : ""}
        </span>
      ) : null}
      <div className="radiation__warning">
        <StateIcon state="doubtful" size={18} />
        <span>
          Es un <strong>indicador indirecto</strong>, no una dosimetría: no mide dosis. Cualquier
          dato se muestra solo como «Posible exposición, requiere confirmación» por personal
          cualificado.
        </span>
      </div>
    </section>
  );
}
