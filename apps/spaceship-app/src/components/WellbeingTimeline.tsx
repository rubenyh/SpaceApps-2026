import type { Origin, WellbeingTimeline as Timeline } from "../api/types";
import { INDICATOR_KINDS } from "../api/types";
import {
  barFraction,
  dayRange,
  formatDay,
  formatDayLong,
  INDICATOR_LABELS,
  SUPPORT_LABELS,
  timelineRanges,
} from "../lib/wellbeing";
import { Panel } from "./Panel";
import { WellbeingIcon } from "./WellbeingMarks";

const ORIGIN_LETTER: Record<Origin, string> = { simulated: "S", live: "L", mixed: "M" };

/** One column per day: origin, level and the six indicator strips (bar = min(z, 4) / 4). */
export function WellbeingTimeline({ timeline, sustainDays }: { timeline: Timeline; sustainDays?: number }) {
  const { days, onset_date, z_threshold } = timeline;
  const { beforeData, baseline } = timelineRanges(days);
  const footnote = [
    beforeData ? `${dayRange(...beforeData)}: before monitoring started.` : null,
    baseline ? `${dayRange(...baseline)}: building your personal baseline.` : null,
    sustainDays !== undefined
      ? `Threshold z ${z_threshold} and ${sustainDays} sustained days are provisional design values.`
      : null,
  ].filter((x) => x !== null);
  const last = days[days.length - 1] as (typeof days)[number] | undefined;
  const thresholdPct = `${barFraction(z_threshold) * 100}%`;
  const summary = `${days.length} days shown. ${
    onset_date ? `Sustained change since ${formatDayLong(onset_date)}.` : "No sustained change."
  } Today: ${last?.has_data ? SUPPORT_LABELS[last.level] : "no data"}.`;

  return (
    <Panel
      title={`Last ${days.length} days`}
      aside={
        <span className="wb-tl__legend">
          <span>
            <span className="wb-tl__swatch sim-hatch" />S = simulated
          </span>
          <span className="wb-live-text">
            <span className="wb-tl__swatch wb-tl__swatch--live" />L = live
          </span>
          <span>
            <span className="wb-tl__swatch wb-tl__swatch--none" />
            No data
          </span>
        </span>
      }
    >
      <p className="wellbeing__faint">
        Bar height = distance from your usual (z, 0–4). Solid amber bar = at or beyond threshold z{" "}
        {z_threshold} (PROV.). Dotted cell = no data.
      </p>
      <p className="sr-only">{summary}</p>
      <div className="wb-tl">
        <div className="wb-tl__col wb-tl__col--labels">
          <div className="wb-tl__mark" />
          <div className="wb-tl__date">Date</div>
          <div className="wb-tl__origin">Origin</div>
          <div className="wb-tl__level">Level</div>
          {INDICATOR_KINDS.map((k) => (
            <div key={k} className="wb-tl__strip">
              {INDICATOR_LABELS[k]}
            </div>
          ))}
        </div>
        {days.map((d) => {
          const onset = d.day === onset_date;
          const today = d === last;
          const cls = `wb-tl__col${onset ? " wb-tl__col--onset" : ""}${today ? " wb-tl__col--today" : ""}`;
          return (
            <div key={d.day} className={cls}>
              <div className="wb-tl__mark">
                {onset ? (
                  <span className="wb-tl__since">Since {formatDay(d.day)}</span>
                ) : today ? (
                  <span className="wb-tl__today">Today</span>
                ) : null}
              </div>
              <div className="wb-tl__date wb-mono">{Number(d.day.slice(8))}</div>
              <div className="wb-tl__origin">
                <span className={`wb-tl__o wb-tl__o--${d.origin ?? "none"}${d.origin === "simulated" ? " sim-hatch" : ""}`}>
                  {d.origin ? ORIGIN_LETTER[d.origin] : ""}
                </span>
              </div>
              <div className="wb-tl__level">
                {d.has_data ? (
                  <span className={`footer__state--wb-${d.level}`} role="img" aria-label={SUPPORT_LABELS[d.level]}>
                    <WellbeingIcon kind={d.level} />
                  </span>
                ) : (
                  <span className="wb-mono wb-tl__nodash">---</span>
                )}
              </div>
              {INDICATOR_KINDS.map((k) => {
                const z = d.has_data ? d.indicators[k] : null;
                return (
                  <div key={k} className="wb-tl__strip">
                    <div className={`wb-tl__cell${z === null ? " wb-tl__cell--none" : ""}`}>
                      {z !== null ? (
                        <span
                          className={`wb-tl__bar${z >= z_threshold ? " wb-tl__bar--over" : ""}`}
                          style={{ height: `${barFraction(z) * 100}%` }}
                        />
                      ) : null}
                      <span className="wb-tl__thr" style={{ bottom: thresholdPct }} />
                    </div>
                  </div>
                );
              })}
            </div>
          );
        })}
      </div>
      {footnote.length > 0 ? <p className="wellbeing__faint">{footnote.join(" ")}</p> : null}
    </Panel>
  );
}
