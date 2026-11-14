import type { Astronaut } from "../api/types";
import type { ConnectionState } from "../hooks/connection";
import { useNow } from "../hooks/useNow";
import { formatUtcClock } from "../lib/format";

interface Props {
  astronauts: Astronaut[] | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  connection: ConnectionState;
}

const CONNECTION_TEXT: Record<ConnectionState, string> = {
  unknown: "◌ CONECTANDO…",
  online: "● EN LÍNEA",
  offline: "○ SIN CONEXIÓN",
};

export function Header({ astronauts, selectedId, onSelect, connection }: Props) {
  const now = useNow(1000);
  const list = astronauts ?? [];

  return (
    <header className="header">
      <h1 className="header__title">CONSOLA MÉDICA</h1>
      <label className="header__crew">
        <span>TRIPULANTE:</span>
        <select
          value={selectedId ?? ""}
          onChange={(e) => onSelect(e.target.value)}
          disabled={list.length === 0}
          aria-label="Tripulante seleccionado"
        >
          {list.length === 0 ? <option value="">— ninguno —</option> : null}
          {list.map((a) => (
            <option key={a.id} value={a.id}>
              {a.id} · {a.display_name}
            </option>
          ))}
        </select>
      </label>
      <time className="header__clock" dateTime={new Date(now).toISOString()}>
        {formatUtcClock(new Date(now))}
      </time>
      <span
        className={`header__conn header__conn--${connection}`}
        role="status"
        aria-live="polite"
      >
        {CONNECTION_TEXT[connection]}
      </span>
    </header>
  );
}
