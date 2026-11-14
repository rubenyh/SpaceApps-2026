import { CrtFrame, Header, Panel, StatusBadge } from "spaceship-app";

const crew = [{ id: "ast-01", display_name: "Valentina Ríos", created_at: "2026-11-01T08:00:00Z" }];

export const ConsoleShell = () => (
  <CrtFrame>
    <div className="app">
      <Header astronauts={crew} selectedId="ast-01" onSelect={() => {}} connection="online" />
      <main className="main">
        <Panel title="PULSO" aside={<StatusBadge status="normal" />}>
          <div className="vital__value">
            <span className="value-lg">72</span>
            <span className="unit">lpm</span>
          </div>
          <div className="muted">RANGO 50 – 100</div>
        </Panel>
      </main>
    </div>
  </CrtFrame>
);
