import { HttpError, type ApiError } from "../api/client";
import { formatClock } from "../lib/wellbeing";
import { WellbeingIcon } from "./WellbeingMarks";

interface Props {
  /** Error of the latest request. Renders nothing when null. */
  error: ApiError | null;
  /** Date.now() of the last successful response, if any. */
  updatedAt: number | null;
  onRetry: () => void;
  /** Mission time zone for HH:MM; UTC until parameters load. */
  timeZone?: string;
}

/** Wellbeing's own service notice (stale grammar, not the physical alert). Last data stays below it. */
export function WellbeingServiceBanner({ error, updatedAt, onRetry, timeZone }: Props) {
  if (!error) return null;
  return (
    <div className="banner banner--stale" role="alert">
      <WellbeingIcon kind="service_off" size={30} />
      <div className="banner__text">
        <span className="banner__title">Wellbeing service unavailable</span>
        <span>
          {updatedAt !== null
            ? `Showing the last data received, at ${formatClock(new Date(updatedAt).toISOString(), timeZone)}. `
            : "No data received yet. "}
          Physical health tabs are not affected.
        </span>
        {error instanceof HttpError ? (
          <span className="wellbeing__faint">
            Error {error.status}: {error.detail}
          </span>
        ) : null}
      </div>
      <button type="button" className="btn btn--ghost" onClick={onRetry}>
        Retry
      </button>
    </div>
  );
}
