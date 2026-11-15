import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import type { Astronaut, AstronautStatus } from "./api/types";
import { listAstronauts } from "./api/astronauts";
import { listIncidents } from "./api/incidents";
import { getAstronautStatus } from "./api/status";
import { Header } from "./components/Header";
import { STATE_LABELS, StateIcon } from "./components/StatusPill";
import { TabBar, type TabDef } from "./components/TabBar";
import { ConnectionContext, type ConnectionState } from "./hooks/connection";
import { usePolling } from "./hooks/usePolling";
import { tabFlags } from "./lib/estado";
import { formatUtcSeconds } from "./lib/format";
import { newIncidentIds } from "./lib/incident";
import { AsistenteScreen } from "./screens/AsistenteScreen";
import { EstadoScreen } from "./screens/EstadoScreen";
import { MusculoScreen } from "./screens/MusculoScreen";
import { OrinaScreen } from "./screens/OrinaScreen";
import { RegistrosScreen } from "./screens/RegistrosScreen";
import { VitalesScreen } from "./screens/VitalesScreen";
import { WellbeingScreen } from "./screens/WellbeingScreen";
import { WellbeingIcon } from "./components/WellbeingMarks";
import { SUPPORT_LABELS } from "./lib/wellbeing";

type TabKey = "estado" | "vitales" | "musculo" | "orina" | "asistente" | "registros" | "wellbeing";

const TABS: TabDef<TabKey>[] = [
  { key: "estado", label: "Status" },
  { key: "vitales", label: "Vital signs" },
  { key: "musculo", label: "Muscle" },
  { key: "orina", label: "Urine" },
  { key: "asistente", label: "Assistant" },
  { key: "registros", label: "Records" },
  // No alert or stale flag: wellbeing is personal and never raises a tab alarm.
  { key: "wellbeing", label: "Wellbeing" },
];

const LEGEND = ["alert", "stale", "no_data", "no_range", "normal"] as const;
const WELLBEING_LEGEND = ["ok", "attention", "needs_support", "baseline_pending", "stale", "no_data"] as const;
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
  astronauts: Astronaut[];
  onNavigate: (tab: TabKey) => void;
  status: AstronautStatus | null;
  statusUpdatedAt: number | null;
}

function CrewScreen({ tab, astronautId, astronauts, onNavigate, status, statusUpdatedAt }: CrewScreenProps) {
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
      return <AsistenteScreen astronautId={astronautId} astronauts={astronauts} status={status} statusUpdatedAt={statusUpdatedAt} />;
    case "registros":
      return <RegistrosScreen astronautId={astronautId} />;
    case "wellbeing":
      return <WellbeingScreen astronautId={astronautId} astronauts={astronauts} />;
  }
}

let audio: AudioContext | null = null;

/** Short 880 Hz beep for a new incident. Never throws: sound is a cue, not the alert itself. */
function beep(): void {
  try {
    if (!audio || audio.state === "closed") audio = new AudioContext();
    const ctx = audio;
    // Autoplay policy can leave the context suspended until a user gesture; ignore if resume fails.
    void ctx.resume().catch(() => {});
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.frequency.value = 880;
    gain.gain.setValueAtTime(0.2, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
    osc.connect(gain).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 0.3);
  } catch {
    // No audio available: the incident still shows in the assistant tab.
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

  // Beep when a new incident opens (e.g. watch SOS), on any tab. IncidentPanel polls too;
  // usePolling keys are per hook instance, not a shared cache, so there is no collision.
  const openIncidents = usePolling("shell:incidents:open", (signal) => listIncidents("open", signal), 5000);
  const seenIncidents = useRef<Set<string> | null>(null);
  useEffect(() => {
    const data = openIncidents.data;
    if (!data) return;
    if (newIncidentIds(seenIncidents.current, data).length > 0) beep();
    seenIncidents.current = new Set([...(seenIncidents.current ?? []), ...data.map((i) => i.id)]);
  }, [openIncidents.data]);

  const onSelect = (id: string) => {
    storeAstronaut(id);
    setPreferred(id);
  };

  const recheck = (
    <>
      <button type="button" className="btn" onClick={astronauts.refresh}>
        Check again
      </button>
      <span className="empty__foot">
        {astronauts.updatedAt
          ? `Last checked at ${formatUtcSeconds(astronauts.updatedAt)} UTC. `
          : ""}
        Checked every 30 s.
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
        astronauts={list ?? []}
        onNavigate={setTab}
        status={status.data}
        statusUpdatedAt={status.updatedAt}
      />
    );
  } else if (list && list.length === 0) {
    content = (
      <EmptyState title="No crew members registered">
        <p>
          The onboard service is connected but has no crew members yet. This console only shows
          data: crew members are registered in the onboard service.
        </p>
        {recheck}
      </EmptyState>
    );
  } else if (astronauts.error) {
    content = (
      <EmptyState title="ONBOARD SERVICE UNAVAILABLE">
        <p>Could not load the crew list, so there is no data to show.</p>
        {recheck}
      </EmptyState>
    );
  } else {
    content = (
      <EmptyState title="Loading crew…">
        <p>Connecting to the onboard service. This usually takes a few seconds.</p>
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
        {tab === "wellbeing" && selected ? (
          <>
            <div className="footer__legend">
              {WELLBEING_LEGEND.map((s) => (
                <span key={s} className={`footer__state footer__state--wb-${s}`}>
                  <WellbeingIcon kind={s} size={16} />
                  {SUPPORT_LABELS[s]}
                </span>
              ))}
            </div>
            <span>LIVE · SIMULATED · MIXED · PROV. = provisional</span>
          </>
        ) : (
          <>
            <div className="footer__legend">
              <span>States:</span>
              {LEGEND.map((s) => (
                <span key={s} className={`footer__state footer__state--${s}`}>
                  <StateIcon state={s} size={15} />
                  {STATE_LABELS[s]}
                </span>
              ))}
            </div>
            <span>
              {selected
                ? "Ranges marked PROV. are provisional"
                : "Tabs become available once there is a crew member"}
            </span>
          </>
        )}
      </footer>
    </div>
  );
}
