import type { SensorConfig, SensorKind } from "../api/types";
import { configRange, isHexColor, SENSOR_LABELS } from "../lib/format";

/** Sensor name; SpO₂ gets a real subscript (the bundled font has no ₂ glyph). */
export function SensorName({ kind }: { kind: SensorKind }) {
  if (kind === "spo2") {
    return (
      <>
        SpO<sub>2</sub>
      </>
    );
  }
  return <>{SENSOR_LABELS[kind]}</>;
}

/** Range with PROV. for provisional values; "No range" when there is none. */
export function RangeLabel({ config }: { config: SensorConfig }) {
  const text = configRange(config);
  if (text === null) return <span className="muted">No range</span>;
  return (
    <span className="range">
      {config.range_role === "sample_validity" ? "Sample validity " : ""}
      {text}
      {config.provisional ? (
        <abbr className="tag tag--prov" title="Provisional range, not clinically validated">
          PROV.
        </abbr>
      ) : null}
    </span>
  );
}

/** Urine colour painted with its own hex value, next to the hex text. */
export function Swatch({ value }: { value: string | null | undefined }) {
  if (!isHexColor(value)) return null;
  return <span className="swatch" style={{ backgroundColor: value }} aria-hidden="true" />;
}
