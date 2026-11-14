import type { Astronaut } from "../api/types";
import type { ConnectionState } from "../hooks/connection";
import { useNow } from "../hooks/useNow";
import { formatUtcDay, formatUtcSeconds } from "../lib/format";
import { StateIcon, type VisualState } from "./StatusPill";

interface Props {
  astronauts: Astronaut[] | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  connection: ConnectionState;
}

const CONNECTION: Record<ConnectionState, { icon: VisualState; text: string }> = {
  unknown: { icon: "no_data", text: "Connecting to the service…" },
  online: { icon: "normal", text: "Connected to the onboard service" },
  offline: { icon: "alert", text: "No connection to the service" },
};

/** Top band: brand, crew selector, UTC clock and connection indicator. */
export function Header({ astronauts, selectedId, onSelect, connection }: Props) {
  const now = useNow(1000);
  const list = astronauts ?? [];
  const conn = CONNECTION[connection];

  return (
    <header className="header">
      <div className="header__group">
        <div className="header__brand">
          <svg width="30" height="30" viewBox="0 0 30 30" aria-hidden="true">
            <circle cx="15" cy="15" r="7" fill="none" stroke="currentColor" strokeWidth="2" />
            <ellipse className="header__orbit" cx="15" cy="15" rx="13.5" ry="5.5" transform="rotate(-24 15 15)" />
          </svg>
          <h1>Biomedical console</h1>
        </div>
        <span className="header__rule" aria-hidden="true" />
        <label className="header__crew">
          <span>Crew member</span>
          <select
            value={selectedId ?? ""}
            onChange={(e) => onSelect(e.target.value)}
            disabled={list.length === 0}
          >
            {list.length === 0 ? <option value="">None</option> : null}
            {list.map((a) => (
              <option key={a.id} value={a.id}>
                {a.id} · {a.display_name}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="header__group">
        <time className="header__clock" dateTime={new Date(now).toISOString()}>
          UTC <strong>{formatUtcSeconds(now)}</strong> · {formatUtcDay(now)} {new Date(now).getUTCFullYear()}
        </time>
        <span className={`header__conn header__conn--${connection}`} role="status" aria-live="polite">
          <StateIcon state={conn.icon} />
          {conn.text}
        </span>
      </div>
    </header>
  );
}
