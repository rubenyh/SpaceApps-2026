import { S } from "../surface";
import { useState } from "react";
import { TabBar } from "spaceship-app";

const TABS = [
  { key: "estado", label: "ESTADO" },
  { key: "vitales", label: "SIGNOS VITALES" },
  { key: "musculo", label: "MÚSCULO" },
  { key: "orina", label: "ORINA" },
  { key: "asistente", label: "ASISTENTE" },
  { key: "registros", label: "REGISTROS" },
];

function Stateful({ initial }: { initial: string }) {
  const [active, setActive] = useState(initial);
  return (
    <S>
      <TabBar tabs={TABS} active={active} onChange={setActive} />
    </S>
  );
}

export const FirstTabActive = () => (
  <S>
    <Stateful initial="estado" />
  </S>
);
export const MiddleTabActive = () => (
  <S>
    <Stateful initial="orina" />
  </S>
);
export const TwoTabs = () => {
  const [active, setActive] = useState("ph");
  return (
    <S>
      <TabBar
        tabs={[
          { key: "salinidad", label: "SALINIDAD" },
          { key: "ph", label: "pH" },
        ]}
        active={active}
        onChange={setActive}
      />
    </S>
  );
};
