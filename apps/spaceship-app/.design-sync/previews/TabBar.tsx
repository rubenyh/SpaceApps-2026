import { S } from "../surface";
import { useState } from "react";
import { TabBar } from "spaceship-app";

const TABS = [
  { key: "estado", label: "Estado" },
  { key: "vitales", label: "Signos vitales" },
  { key: "musculo", label: "Músculo" },
  { key: "orina", label: "Orina" },
  { key: "asistente", label: "Asistente" },
  { key: "registros", label: "Registros" },
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
          { key: "salinidad", label: "Salinidad" },
          { key: "ph", label: "pH" },
        ]}
        active={active}
        onChange={setActive}
      />
    </S>
  );
};
