import { S } from "../surface";
import type { ReactNode } from "react";
import { AgeLabel, BodyDiagram, StatusBadge } from "spaceship-app";

// Callout markup ported from src/screens/EstadoScreen.tsx (it is app glue, not a library component).
function Callout({ title, status, value, unit, age }: { title: string; status: any; value: ReactNode; unit: string; age: number | null }) {
  const noData = status === "no_data";
  return (
    <div className={`callout statebox statebox--${status}`}>
      <div className="callout__title">{title}</div>
      <div className="callout__value">
        <span className="value-lg">{noData ? "---" : value}</span>
        {!noData && unit ? <span className="unit">{unit}</span> : null}
        <AgeLabel seconds={noData ? null : age} emphasis={status === "stale"} />
      </div>
      <div className="callout__state">
        <StatusBadge status={status} />
      </div>
    </div>
  );
}

export const AllNormal = () => (
  <S>
    <BodyDiagram
      lungs={<Callout title="PULMONES · SpO₂" status="normal" value="97" unit="%" age={4} />}
      heart={<Callout title="CORAZÓN · PULSO" status="normal" value="72" unit="lpm" age={4} />}
      kidneys={<Callout title="RIÑONES · ORINA" status="normal" value={<><span className="value-prefix">pH</span> 6,2</>} unit="" age={1140} />}
      limbs={<Callout title="EXTREMIDADES · MÚSCULO" status="no_range" value="1,058" unit="g/cm³" age={86_400} />}
    />
  </S>
);

export const MixedStates = () => (
  <S>
    <BodyDiagram
      lungs={<Callout title="PULMONES · SpO₂" status="alert" value="88" unit="%" age={6} />}
      heart={<Callout title="CORAZÓN · PULSO" status="normal" value="104" unit="lpm" age={6} />}
      kidneys={<Callout title="RIÑONES · ORINA" status="stale" value={<><span className="value-prefix">pH</span> 5,4</>} unit="" age={93_600} />}
      limbs={<Callout title="EXTREMIDADES · MÚSCULO" status="no_data" value="" unit="" age={null} />}
    />
  </S>
);
