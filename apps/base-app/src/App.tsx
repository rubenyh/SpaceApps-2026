import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { API_BASE_URL, type ApiError } from "./api/client";
import { getAlerts, getCrew, getLink } from "./api/ground";
import type { Link } from "./api/types";
import { Flap } from "./components/Flap";
import { useNow } from "./hooks/useNow";
import { usePolling } from "./hooks/usePolling";
import { addToLedger, LINK_HEADLINES, liveAge, linkState, type LedgerEntry } from "./lib/board";
import { formatAge, formatDuration, utcSeconds } from "./lib/format";
import { Alertas } from "./screens/Alertas";
import { Astronauta } from "./screens/Astronauta";
import { Enlace } from "./screens/Enlace";
import { Incidents } from "./screens/Incidents";
import { Tripulacion } from "./screens/Tripulacion";

type Tab = "crew" | "astro" | "alerts" | "incidents" | "link";

const TABS: { key: Tab; label: string }[] = [
  { key: "crew", label: "Crew" },
  { key: "astro", label: "Astronaut" },
  { key: "alerts", label: "Alerts" },
  { key: "incidents", label: "Incidents" },
  { key: "link", label: "Link" },
];

const LINK_POLL_MS = 2_000;
const CREW_POLL_MS = 3_000;
const ALERTS_POLL_MS = 5_000;
const ALERTS_LIMIT = 200;

export default function App() {
  const [tab, setTab] = useState<Tab>("crew");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const now = useNow(1000);

  const link = usePolling("link", getLink, LINK_POLL_MS);
  const crew = usePolling("crew", getCrew, CREW_POLL_MS);
  const alerts = usePolling("alerts", (s) => getAlerts(ALERTS_LIMIT, s), ALERTS_POLL_MS);

  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const prevLink = useRef<Link | null>(null);
  useEffect(() => {
    if (!link.data) return;
    const prev = prevLink.current;
    prevLink.current = link.data;
    setLedger((l) => addToLedger(l, prev, link.data as Link));
  }, [link.data]);

  // Default the astronaut view to the first crew member, and recover if they disappear.
  useEffect(() => {
    const members = crew.data ?? [];
    if (members.length && !members.some((m) => m.astronaut_id === selectedId)) {
      setSelectedId(members[0].astronaut_id);
    }
  }, [crew.data, selectedId]);

  const offline = link.error?.kind === "network" || crew.error?.kind === "network";
  const httpError: ApiError | null =
    [link.error, crew.error, alerts.error].find((e) => e?.kind === "http") ?? null;
  const since = liveAge(link.data?.seconds_since_last_batch, link.updatedAt, now);
  const state = linkState(link.data, since, offline);

  const retry = () => {
    link.refresh();
    crew.refresh();
    alerts.refresh();
  };

  const open = (id: string) => {
    setSelectedId(id);
    setTab("astro");
  };

  const onTabKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const idx = TABS.findIndex((t) => t.key === tab);
    let next = -1;
    if (e.key === "ArrowRight") next = (idx + 1) % TABS.length;
    else if (e.key === "ArrowLeft") next = (idx - 1 + TABS.length) % TABS.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = TABS.length - 1;
    if (next < 0) return;
    e.preventDefault();
    setTab(TABS[next].key);
    tabRefs.current[next]?.focus();
  };

  const lastOk = Math.max(link.updatedAt ?? 0, crew.updatedAt ?? 0);

  return (
    <div className="app">
      <header className="topbar">
        <span className="brand">Ground · Crew health</span>
        <div className="tabs" role="tablist" aria-label="Screens" onKeyDown={onTabKey}>
          {TABS.map((t, i) => (
            <button
              key={t.key}
              ref={(el) => {
                tabRefs.current[i] = el;
              }}
              type="button"
              role="tab"
              id={`tab-${t.key}`}
              aria-selected={tab === t.key}
              aria-controls="panel"
              tabIndex={tab === t.key ? 0 : -1}
              className="tab"
              onClick={() => setTab(t.key)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className={`linkbar linkbar--${state}`}>
          {/* Headline changes only with the state, so the live region does not announce every tick. */}
          <span className="linkbar__words" role="status">
            {LINK_HEADLINES[state]}
          </span>
          <span className="linkbar__facts">
            Batch no.{" "}
            <Flap text={link.data?.batches_received ? String(link.data.batches_received) : "--"} className="flap--inline" />
            {" · "}
            {since === null ? "no batches" : formatAge(since)}
            <span className="linkbar__utc">
              {" · "}UTC <strong>{utcSeconds(now)}</strong>
            </span>
          </span>
        </div>
      </header>

      {offline ? (
        <div className="banner banner--alert" role="alert">
          <p>
            No connection to the ground service ({API_BASE_URL}).{" "}
            {lastOk
              ? `Showing the last data received ${formatAge((now - lastOk) / 1000)}, marked as old data.`
              : "No data has been received yet."}{" "}
            Retrying automatically every {formatDuration(LINK_POLL_MS / 1000)}.
          </p>
          <button type="button" className="button" onClick={retry}>
            Retry now
          </button>
        </div>
      ) : httpError ? (
        <div className="banner banner--stale" role="alert">
          <p>
            The ground service answered with an error ({httpError.message}). The last data stays on
            screen; retrying automatically.
          </p>
          <button type="button" className="button" onClick={retry}>
            Retry now
          </button>
        </div>
      ) : null}

      <main className="panel" id="panel" role="tabpanel" aria-labelledby={`tab-${tab}`}>
        {tab === "crew" ? (
          <Tripulacion
            crew={crew.data}
            crewAt={crew.updatedAt}
            offline={offline}
            now={now}
            link={link.data}
            ledger={ledger}
            onOpen={open}
          />
        ) : tab === "astro" ? (
          <Astronauta
            crew={crew.data}
            crewAt={crew.updatedAt}
            offline={offline}
            now={now}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        ) : tab === "alerts" ? (
          <Alertas alerts={alerts.data} limit={ALERTS_LIMIT} crew={crew.data} offline={offline} />
        ) : tab === "incidents" ? (
          <Incidents />
        ) : (
          <Enlace link={link.data} since={since} state={state} crew={crew.data} ledger={ledger} offline={offline} />
        )}
      </main>
    </div>
  );
}
