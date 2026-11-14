import { useCallback, useState, type ReactNode } from "react";
import type { AstronautStatus } from "./api/types";
import { listAstronauts } from "./api/astronauts";
import { getAstronautStatus } from "./api/status";
import { Header } from "./components/Header";
import { STATE_LABELS, StateIcon } from "./components/StatusPill";
import { TabBar, type TabDef } from "./components/TabBar";
import { ConnectionContext, type ConnectionState } from "./hooks/connection";
import { usePolling } from "./hooks/usePolling";
import { tabFlags } from "./lib/estado";
import { formatUtcSeconds } from "./lib/format";
import { AsistenteScreen } from "./screens/AsistenteScreen";
import { EstadoScreen } from "./screens/EstadoScreen";
import { MusculoScreen } from "./screens/MusculoScreen";
import { OrinaScreen } from "./screens/OrinaScreen";
import { RegistrosScreen } from "./screens/RegistrosScreen";
import { VitalesScreen } from "./screens/VitalesScreen";

type TabKey = "estado" | "vitales" | "musculo" | "orina" | "asistente" | "registros";

const TABS: TabDef<TabKey>[] = [
  { key: "estado", label: "Estado" },
  { key: "vitales", label: "Signos vitales" },
  { key: "musculo", label: "Músculo" },
  { key: "orina", label: "Orina" },
  { key: "asistente", label: "Asistente" },
  { key: "registros", label: "Registros" },
];

const LEGEND = ["alert", "stale", "no_data", "no_range", "normal"] as const;
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

interface CrewScreenProps {
  tab: TabKey;
  astronautId: string;
  onNavigate: (tab: TabKey) => void;
  status: AstronautStatus | null;
  statusUpdatedAt: number | null;
}

function CrewScreen({ tab, astronautId, onNavigate, status, statusUpdatedAt }: CrewScreenProps) {
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
      return <AsistenteScreen astronautId={astronautId} status={status} statusUpdatedAt={statusUpdatedAt} />;
    case "registros":
      return <RegistrosScreen astronautId={astronautId} />;
  }
}

/** Centred message for the states with no crew member to show. */
function EmptyState({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="empty">
      <StateIcon state="no_data" size={96} />
      <h2>{title}</h2>
      {children}
    </section>
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

  // Shell-level status: tab problem icons and the assistant's "what I can see" list.
  const status = usePolling(
    selected ? `shell:${selected}` : null,
    (signal) => getAstronautStatus(selected as string, signal),
    5000,
  );

  const onSelect = (id: string) => {
    storeAstronaut(id);
    setPreferred(id);
  };

  const recheck = (
    <>
      <button type="button" className="btn" onClick={astronauts.refresh}>
        Volver a comprobar
      </button>
      <span className="empty__foot">
        {astronauts.updatedAt
          ? `Comprobado por última vez a las ${formatUtcSeconds(astronauts.updatedAt)} UTC. `
          : ""}
        Se comprueba cada 30 s.
      </span>
    </>
  );

  let content;
  if (selected) {
    content = (
      <CrewScreen
        key={`${tab}:${selected}`}
        tab={tab}
        astronautId={selected}
        onNavigate={setTab}
        status={status.data}
        statusUpdatedAt={status.updatedAt}
      />
    );
  } else if (list && list.length === 0) {
    content = (
      <EmptyState title="No hay tripulantes registrados">
        <p>
          El servicio de a bordo está conectado, pero todavía no tiene ningún tripulante. Esta consola
          solo muestra datos: los tripulantes se dan de alta en el servicio de a bordo.
        </p>
        {recheck}
      </EmptyState>
    );
  } else if (astronauts.error) {
    content = (
      <EmptyState title="SERVICIO ONBOARD NO DISPONIBLE">
        <p>No se ha podido obtener la lista de tripulantes, así que no hay datos que mostrar.</p>
        {recheck}
      </EmptyState>
    );
  } else {
    content = (
      <EmptyState title="Cargando tripulación…">
        <p>Conectando con el servicio de a bordo. Suele tardar unos segundos.</p>
      </EmptyState>
    );
  }

  return (
    <div className="app">
      <Header astronauts={list} selectedId={selected} onSelect={onSelect} connection={connection} />
      <TabBar
        tabs={TABS}
        active={tab}
        onChange={setTab}
        flags={tabFlags(status.data)}
        disabled={!selected}
      />
      <main id="screen" className="main" role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {content}
      </main>
      <footer className="footer">
        <div className="footer__legend">
          <span>Estados:</span>
          {LEGEND.map((s) => (
            <span key={s} className={`footer__state footer__state--${s}`}>
              <StateIcon state={s} size={15} />
              {STATE_LABELS[s]}
            </span>
          ))}
        </div>
        <span>
          {selected
            ? "Los rangos marcados PROV. son provisionales"
            : "Las pestañas se activan cuando haya un tripulante"}
        </span>
      </footer>
    </div>
  );
}
