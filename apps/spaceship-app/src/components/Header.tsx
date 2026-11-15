import type { Astronaut } from "../api/types";
import { getEarthLink, type EarthLink } from "../api/status";
import type { ConnectionState } from "../hooks/connection";
import { useNow } from "../hooks/useNow";
import { usePolling } from "../hooks/usePolling";
import { formatUtcDay, formatUtcSeconds } from "../lib/format";
import { StateIcon, type VisualState } from "./StatusPill";

interface Props {
  /** Label of the screen on show. */
  title: string;
  astronauts: Astronaut[] | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  connection: ConnectionState;
}

const CONNECTION: Record<ConnectionState, { icon: VisualState; text: string }> = {
  unknown: { icon: "no_data", text: "Onboard service: connecting…" },
  online: { icon: "normal", text: "Onboard service: connected" },
  offline: { icon: "alert", text: "Onboard service: no connection" },
};

/** Ship-to-Earth telemetry link, worded like the ground console's link bar. */
function earthLink(link: EarthLink): { state: ConnectionState; icon: VisualState; text: string } {
  if (!link.enabled) return { state: "unknown", icon: "no_data", text: "Earth link: off" };
  if (link.paused) return { state: "offline", icon: "alert", text: "Earth link: down (simulated outage)" };
  if (link.failures > 0) return { state: "offline", icon: "alert", text: "Earth link: ground not answering" };
  if (link.batches_sent === 0) return { state: "unknown", icon: "no_data", text: "Earth link: checking…" };
  return { state: "online", icon: "normal", text: "Earth link: up" };
}

/** Top bar: screen title, crew selector, connection indicators and UTC clock. */
export function Header({ title, astronauts, selectedId, onSelect, connection }: Props) {
  const now = useNow(1000);
  const list = astronauts ?? [];
  const conn = CONNECTION[connection];
  const earth = usePolling("earth-link", (signal) => getEarthLink(signal), 2000);
  const el = earth.data ? earthLink(earth.data) : null;

  return (
    <header className="topbar">
      <span className="topbar__title">{title}</span>
      <label className="topbar__crew">
        <span>Crew member</span>
        <select
          value={selectedId ?? ""}
          onChange={(e) => onSelect(e.target.value)}
          disabled={list.length === 0}
        >
          {list.length === 0 ? <option value="">None</option> : null}
          {list.map((a) => (
            <option key={a.id} value={a.id}>
              {a.display_name === a.id ? a.id : `${a.id} · ${a.display_name}`}
            </option>
          ))}
        </select>
      </label>
      <span className={`topbar__conn topbar__conn--${connection}`} role="status" aria-live="polite">
        <StateIcon state={conn.icon} />
        {conn.text}
      </span>
      {el ? (
        <span className={`topbar__conn topbar__conn--${el.state}`} role="status" aria-live="polite">
          <StateIcon state={el.icon} />
          {el.text}
        </span>
      ) : null}
      <time className="topbar__clock" dateTime={new Date(now).toISOString()}>
        UTC <strong>{formatUtcSeconds(now)}</strong> · {formatUtcDay(now)} {new Date(now).getUTCFullYear()}
      </time>
    </header>
  );
}
