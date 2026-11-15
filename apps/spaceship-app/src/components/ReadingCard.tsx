import type { ReactNode } from "react";
import type { Quality } from "../api/types";
import { formatAge } from "../lib/format";
import { Flap } from "./Flap";
import { StateIcon, StatusPill, type VisualState } from "./StatusPill";
import { withSub2 } from "./Sub2";

const QUALITY_TEXT: Record<Quality, string> = {
  good: "Good quality",
  suspect: "Suspect quality",
  bad: "Bad quality",
};

interface Props {
  title: string;
  /** Organ or body area the reading belongs to. */
  organ: string;
  /** "doubtful" is for a sample-validity range out of bounds: never drawn as an alert. */
  status: VisualState;
  /** Formatted value: a string is drawn on a split-flap plate. Ignored when there is no data. */
  value: ReactNode;
  unit?: string;
  ageSeconds: number | null;
  quality?: Quality | null;
  /** Where the reading came from, shown after the quality. */
  source?: string | null;
  /** Value size: "sm" in dense grids, "lg" on detail screens. */
  size?: "sm" | "md" | "lg";
  /** One plain sentence about the reading. */
  explanation: string;
  /** Extra label next to the explanation, e.g. a "Doubtful sample" pill. */
  tag?: ReactNode;
  /** Bottom area, e.g. a RangeTrack. */
  children?: ReactNode;
}

/** Card for one reading: label, value and age follow its status; only an alert turns the border red. */
export function ReadingCard({
  title,
  organ,
  status,
  value,
  unit,
  ageSeconds,
  quality,
  source,
  size = "md",
  explanation,
  tag,
  children,
}: Props) {
  const noData = status === "no_data";
  const age = formatAge(ageSeconds);
  return (
    <section className={`card card--${status} card--${size}`}>
      <div className="card__head">
        <div className="card__titles">
          <span className="card__title">{withSub2(title)}</span>
          <span className="card__organ">{withSub2(organ)}</span>
        </div>
        <StatusPill state={status} />
      </div>
      <div className="card__reading">
        <div className="card__value">
          {noData ? "---" : typeof value === "string" ? (
            <Flap text={value} className={status === "alert" ? "flap--red" : ""} />
          ) : (
            value
          )}
          {!noData && unit ? <span className="card__unit">{unit}</span> : null}
        </div>
        <div className="card__meta">
          <span className="card__age">
            {status === "stale" || status === "future" ? <StateIcon state={status} size={15} /> : null}
            {noData || !age ? "Never measured" : age.charAt(0).toUpperCase() + age.slice(1)}
          </span>
          {!noData && quality ? (
            <span className="card__quality">
              {QUALITY_TEXT[quality]}
              {source ? ` · ${source}` : ""}
            </span>
          ) : null}
        </div>
      </div>
      <div className="card__explain">
        <span>{explanation}</span>
        {tag}
      </div>
      {children ? <div className="card__bottom">{children}</div> : null}
    </section>
  );
}
