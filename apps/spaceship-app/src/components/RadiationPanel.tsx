import type { SensorStatus } from "../api/types";
import { formatAge, readingValueText, unitLabel } from "../lib/format";
import { Panel } from "./Panel";

interface Props {
  sensor: SensorStatus | null;
  ageSeconds: number | null;
}

/**
 * Urine radiation marker. An indirect marker, NOT dosimetry: never shown as a
 * dose, never as [ OK ]. With a reading it is only ever presented as
 * «POSIBLE EXPOSICIÓN, REQUIERE CONFIRMACIÓN» plus the raw value.
 */
export function RadiationPanel({ sensor, ageSeconds }: Props) {
  const reading = sensor?.latest ?? null;
  return (
    <Panel title="⚠ RADIACIÓN · INDICADOR INDIRECTO" className="radiation">
      {reading ? (
        <div className="statebox statebox--exposure radiation__box">
          <div className="radiation__headline">POSIBLE EXPOSICIÓN, REQUIERE CONFIRMACIÓN</div>
          <div className="radiation__raw">
            valor bruto del marcador: <strong>{readingValueText(reading)}</strong>
            {reading.unit ? ` ${unitLabel(reading.unit)}` : ""}
          </div>
          <div className="radiation__age">
            {formatAge(ageSeconds)}
            {sensor?.status === "stale" ? " · [~ VIEJO ]" : ""}
          </div>
        </div>
      ) : (
        <div className="statebox statebox--no_data radiation__box">
          <div className="badge badge--no_data">[-- SIN DATOS ]</div>
          <div>SIN DATOS – marcador no definido.</div>
        </div>
      )}
      <div className="radiation__warning">
        <p>
          Marcador indirecto en orina. <strong>No es una dosimetría ni una dosis medida.</strong>
        </p>
        <p>
          Cualquier lectura se mostrará solo como POSIBLE EXPOSICIÓN, REQUIERE CONFIRMACIÓN por
          personal cualificado con instrumentación adecuada.
        </p>
      </div>
    </Panel>
  );
}
