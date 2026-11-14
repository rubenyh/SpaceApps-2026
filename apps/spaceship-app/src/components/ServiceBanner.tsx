import { HttpError, type ApiError } from "../api/client";
import { formatUtcSeconds } from "../lib/format";
import { StateIcon } from "./StatusPill";

interface Props {
  /** Error of the latest request. Renders nothing when null. */
  error: ApiError | null;
  /** Date.now() of the last successful response, if any. */
  updatedAt: number | null;
  onRetry: () => void;
}

/** Notice for a failed request, with a retry button. The last known data stays on screen below it. */
export function ServiceBanner({ error, updatedAt, onRetry }: Props) {
  if (!error) return null;
  return (
    <div className="banner banner--error" role="alert">
      <StateIcon state="alert" size={30} />
      <div className="banner__text">
        <span className="banner__title">
          {error instanceof HttpError
            ? `Error ${error.status}: ${error.detail}`
            : "SERVICIO ONBOARD NO DISPONIBLE"}
        </span>
        <span>
          {updatedAt !== null
            ? `No llegan datos nuevos desde las ${formatUtcSeconds(updatedAt)} UTC. Abajo ves los últimos valores recibidos. `
            : "Todavía no se ha recibido ningún dato. "}
          Se reintenta automáticamente.
        </span>
      </div>
      <button type="button" className="btn" onClick={onRetry}>
        Reintentar ahora
      </button>
    </div>
  );
}
