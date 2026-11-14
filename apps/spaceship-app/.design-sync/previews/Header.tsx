import { S } from "../surface";
import { Header } from "spaceship-app";

const crew = [
  { id: "ast-01", display_name: "Valentina Ríos", created_at: "2026-11-01T08:00:00Z" },
  { id: "ast-02", display_name: "Mateo Herrera", created_at: "2026-11-01T08:05:00Z" },
  { id: "ast-03", display_name: "Lucía Campos", created_at: "2026-11-01T08:10:00Z" },
];

export const Online = () => (
  <S>
    <Header astronauts={crew} selectedId="ast-01" onSelect={() => {}} connection="online" />
  </S>
);
export const Offline = () => (
  <S>
    <Header astronauts={crew} selectedId="ast-02" onSelect={() => {}} connection="offline" />
  </S>
);
export const ConnectingNoCrew = () => (
  <S>
    <Header astronauts={null} selectedId={null} onSelect={() => {}} connection="unknown" />
  </S>
);
