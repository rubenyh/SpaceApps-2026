import { S } from "../surface";
import { Panel, SegmentedControl } from "spaceship-app";

export const Basic = () => (
  <S>
    <Panel title="Lo que el asistente puede ver">
      <p className="caption">El asistente solo usa las lecturas de esta consola.</p>
    </Panel>
  </S>
);

export const WithAside = () => (
  <S>
    <Panel
      title="Tendencia"
      aside={
        <SegmentedControl
          label="Periodo"
          options={[
            { key: "7d", label: "7 D" },
            { key: "30d", label: "30 D" },
            { key: "all", label: "Todo" },
          ]}
          value="30d"
          onChange={() => {}}
        />
      }
    >
      <p className="caption">Valor en u.a. · 12 lecturas · fechas en UTC</p>
    </Panel>
  </S>
);
