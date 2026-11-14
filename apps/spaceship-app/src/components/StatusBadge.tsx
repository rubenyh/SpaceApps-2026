import type { RangeRole, ReadingStatus } from "../api/types";
import { STATUS_MARKERS } from "../lib/format";

interface Props {
  status: ReadingStatus;
  /** "sample_validity" turns normal/alert into MUESTRA VÁLIDA / MUESTRA DUDOSA. */
  rangeRole?: RangeRole;
}

function badgeText(status: ReadingStatus, rangeRole: RangeRole = "health"): string {
  if (rangeRole === "sample_validity") {
    if (status === "normal") return "[ MUESTRA VÁLIDA ]";
    if (status === "alert") return "[? MUESTRA DUDOSA ]";
  }
  return STATUS_MARKERS[status];
}

/** Bracketed state marker. Distinguishable without colour (text + border/inverse). */
export function StatusBadge({ status, rangeRole = "health" }: Props) {
  // A sample-validity alert is not a health alert: never inverse/blinking.
  const visual =
    rangeRole === "sample_validity" && status === "alert" ? "doubtful" : status;
  return <span className={`badge badge--${visual}`}>{badgeText(status, rangeRole)}</span>;
}
