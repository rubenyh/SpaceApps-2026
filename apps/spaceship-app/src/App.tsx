import { useCallback, useState } from "react";
import { listAstronauts } from "./api/astronauts";
import { API_BASE_URL } from "./api/client";
import { CrtFrame } from "./components/CrtFrame";
import { Header } from "./components/Header";
import { Panel } from "./components/Panel";
import { TabBar, type TabDef } from "./components/TabBar";
import { ConnectionContext, type ConnectionState } from "./hooks/connection";
import { usePolling } from "./hooks/usePolling";
import { AsistenteScreen } from "./screens/AsistenteScreen";
import { EstadoScreen } from "./screens/EstadoScreen";
import { MusculoScreen } from "./screens/MusculoScreen";
import { OrinaScreen } from "./screens/OrinaScreen";
import { RegistrosScreen } from "./screens/RegistrosScreen";
import { VitalesScreen } from "./screens/VitalesScreen";

type TabKey = "estado" | "vitales" | "musculo" | "orina" | "asistente" | "registros";

const TABS: TabDef<TabKey>[] = [
  { key: "estado", label: "ESTADO" },
  { key: "vitales", label: "SIGNOS VITALES" },
  { key: "musculo", label: "MÚSCULO" },
  { key: "orina", label: "ORINA" },
  { key: "asistente", label: "ASISTENTE" },
  { key: "registros", label: "REGISTROS" },
];

const STORAGE_KEY = "consola-medica.astronaut";

function readStoredAstronaut(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function storeAstronaut(id: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, id);
  } catch {
    // Storage unavailable: the choice is simply not remembered.
  }
}

function CrewScreen({
  tab,
  astronautId,
  onNavigate,
}: {
  tab: TabKey;
  astronautId: string;
  onNavigate: (tab: TabKey) => void;
}) {
  switch (tab) {
    case "estado":
      return <EstadoScreen astronautId={astronautId} onNavigate={onNavigate} />;
    case "vitales":
      return <VitalesScreen astronautId={astronautId} />;
    case "musculo":
      return <MusculoScreen astronautId={astronautId} />;
    case "orina":
      return <OrinaScreen astronautId={astronautId} />;
    case "asistente":
      return <AsistenteScreen astronautId={astronautId} />;
    case "registros":
      return <RegistrosScreen astronautId={astronautId} />;
  }
}

function NoCrew() {
  const curl = `curl -X POST ${API_BASE_URL}/astronauts \\
  -H "Content-Type: application/json" \\
  -d '{"id":"ast-01","display_name":"Nombre Apellido"}'`;
  return (
    <Panel title="SIN TRIPULACIÓN REGISTRADA" className="statebox statebox--no_data">
      <p>No hay ningún tripulante dado de alta en el servicio onboard.</p>
      <p>Para registrar uno:</p>
      <pre className="code">{curl}</pre>
      <p className="muted">La lista se actualiza cada 30 s.</p>
    </Panel>
  );
}

function WaitingForService() {
  return (
    <Panel title="ESPERANDO AL SERVICIO ONBOARD" className="statebox statebox--no_data">
      <p>[-- SIN DATOS ] No se ha podido obtener la lista de tripulantes.</p>
      <p className="muted">
        Dirección configurada: {API_BASE_URL}. Se reintenta automáticamente cada 30 s.
      </p>
    </Panel>
  );
}

export default function App() {
  const [connection, setConnection] = useState<ConnectionState>("unknown");
  const report = useCallback((reachable: boolean) => {
    setConnection(reachable ? "online" : "offline");
  }, []);

  return (
    <ConnectionContext.Provider value={report}>
      <Console connection={connection} />
    </ConnectionContext.Provider>
  );
}

/** Lives inside the provider so the astronaut poll also reports connectivity. */
function Console({ connection }: { connection: ConnectionState }) {
  const [tab, setTab] = useState<TabKey>("estado");
  const [preferred, setPreferred] = useState<string | null>(readStoredAstronaut);
  const astronauts = usePolling("astronauts", (signal) => listAstronauts(signal), 30_000);

  const list = astronauts.data;
  const selected =
    list && list.length > 0 ? (list.find((a) => a.id === preferred)?.id ?? list[0].id) : null;

  const onSelect = (id: string) => {
    storeAstronaut(id);
    setPreferred(id);
  };

  let content;
  if (selected) {
    content = <CrewScreen key={`${tab}:${selected}`} tab={tab} astronautId={selected} onNavigate={setTab} />;
  } else if (tab === "asistente") {
    // The assistant also works without a selected astronaut (astronaut_id: null).
    content = <AsistenteScreen astronautId={null} />;
  } else if (list && list.length === 0) {
    content = <NoCrew />;
  } else if (astronauts.error) {
    content = <WaitingForService />;
  } else {
    content = <div className="muted">Cargando tripulación…</div>;
  }

  return (
    <CrtFrame>
      <div className="app">
        <Header
          astronauts={list}
          selectedId={selected}
          onSelect={onSelect}
          connection={connection}
        />
        {connection === "offline" ? (
          <div className="banner" role="alert">
            SERVICIO ONBOARD NO DISPONIBLE · {API_BASE_URL} · reintentando
          </div>
        ) : null}
        <TabBar tabs={TABS} active={tab} onChange={setTab} />
        <main id="screen" className="main" role="tabpanel" aria-labelledby={`tab-${tab}`}>
          {content}
        </main>
      </div>
    </CrtFrame>
  );
}
