import { S } from "../surface";
import { Panel, StatusBadge } from "spaceship-app";

export const Basic = () => (
  <S>
    <Panel title="LEYENDA">
      <p>Orina: estado más relevante entre pH, salinidad, color y temperatura.</p>
      <p className="muted">Refresco cada 5 s.</p>
    </Panel>
  </S>
);

export const WithAside = () => (
  <S>
    <Panel title="PULSO" aside={<StatusBadge status="normal" />}>
      <div className="vital__value">
        <span className="value-lg">72</span>
        <span className="unit">lpm</span>
      </div>
      <div className="muted">RANGO 50 – 100</div>
    </Panel>
  </S>
);

export const AlertStateBox = () => (
  <S>
    <Panel title="SpO₂" aside={<StatusBadge status="alert" />} className="statebox statebox--alert">
      <div className="vital__value">
        <span className="value-lg">88</span>
        <span className="unit">%</span>
      </div>
      <div className="muted">RANGO 94 – 100</div>
    </Panel>
  </S>
);

export const NoDataStateBox = () => (
  <S>
    <Panel title="SIN TRIPULACIÓN REGISTRADA" className="statebox statebox--no_data">
      <p>No hay ningún tripulante dado de alta en el servicio onboard.</p>
      <p className="muted">La lista se actualiza cada 30 s.</p>
    </Panel>
  </S>
);
