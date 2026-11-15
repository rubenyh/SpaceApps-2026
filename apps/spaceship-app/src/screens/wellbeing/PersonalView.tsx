import { useState, type ReactNode } from "react";
import type { IndicatorKind, WellbeingAssessment, WellbeingTimeline as Timeline } from "../../api/types";
import { getWellbeing, getWellbeingParameters, getWellbeingTimeline, listCheckins } from "../../api/wellbeing";
import { IndicatorRow } from "../../components/IndicatorRow";
import { Panel } from "../../components/Panel";
import { ConfidenceMeter, OriginMark, TrendMark, WellbeingIcon, WellbeingPill } from "../../components/WellbeingMarks";
import { WellbeingServiceBanner } from "../../components/WellbeingServiceBanner";
import { WellbeingTimeline } from "../../components/WellbeingTimeline";
import { usePolling } from "../../hooks/usePolling";
import { formatClock, formatDay, formatDayLong, missionDay, sourcesText, TIMELINE_DAYS } from "../../lib/wellbeing";

interface Props {
  toggle: ReactNode;
  astronautId: string;
  displayName: string;
  onCheckin: () => void;
  onShare: () => void;
  onLock: () => void;
}

const POLL_MS = 30_000;
const PARAMS_POLL_MS = 300_000;

const days = (n: number) => `${n} ${n === 1 ? "day" : "days"}`;

/** Personal detail: summary, indicators and timeline, compared with the person's own usual. */
export function PersonalView({ toggle, astronautId, displayName, onCheckin, onShare, onLock }: Props) {
  const assessment = usePolling(`wb-assess:${astronautId}`, (s) => getWellbeing(astronautId, s), POLL_MS);
  const timeline = usePolling(
    `wb-timeline:${astronautId}`,
    (s) => getWellbeingTimeline(astronautId, TIMELINE_DAYS, s),
    POLL_MS,
  );
  const params = usePolling("wb-params", getWellbeingParameters, PARAMS_POLL_MS);
  const tz = params.data?.mission_tz;
  const today = tz ? missionDay(tz) : undefined;
  const checkin = usePolling(
    today ? `wb-checkin:${astronautId}:${today}` : null,
    (s) => listCheckins(astronautId, { since: today, until: today }, s),
    POLL_MS,
  );
  const todayCheckin = checkin.data?.[0] ?? null;
  const [open, setOpen] = useState<Partial<Record<IndicatorKind, boolean>>>({});

  const a = assessment.data;
  const t = timeline.data;
  // shortcut: z_threshold only comes with the timeline; ask backend to add it to WellbeingAssessment
  const threshold = t?.z_threshold ?? params.data?.z_threshold ?? null;
  const error = assessment.error ?? timeline.error;
  const retry = () => {
    assessment.refresh();
    timeline.refresh();
  };
  const empty = a?.level === "no_data" && !t?.days.some((d) => d.has_data);

  return (
    <div className="screen">
      <div className="wellbeing__bar">
        {toggle}
        <span className="wb-private">
          <WellbeingIcon kind="lock" size={18} />
          <strong>Private: only you can see this detail</strong>{" "}
          <span className="wb-private__who">· signed in as {displayName}</span>
        </span>
        <span className="wellbeing__spacer" />
        <button type="button" className="btn btn--ghost wb-checkin-btn" onClick={onCheckin}>
          {todayCheckin ? (
            <>
              <WellbeingIcon kind="ok" size={18} />
              Check-in done {formatClock(todayCheckin.submitted_at, tz)} · Edit
            </>
          ) : checkin.data ? (
            "Start today's check-in"
          ) : (
            "Daily check-in"
          )}
        </button>
        <button type="button" className="btn btn--ghost wb-share" onClick={onShare}>
          Share with ground psychologist…
        </button>
        <button type="button" className="btn btn--ghost wb-iconbtn" aria-label="Lock personal view" onClick={onLock}>
          <WellbeingIcon kind="lock" size={18} />
        </button>
      </div>

      <WellbeingServiceBanner error={error} updatedAt={assessment.updatedAt} onRetry={retry} timeZone={tz} />

      {!a || threshold === null ? (
        error ? null : (
          <div className="banner" role="status">
            <div className="banner__text">
              <span className="banner__title">Loading wellbeing…</span>
            </div>
          </div>
        )
      ) : empty ? (
        <section className="empty wb-empty">
          <WellbeingIcon kind="no_data" size={32} />
          <h2>No wellbeing data yet</h2>
          <p>Data will appear after the first daily check-in or video log.</p>
          <button type="button" className="btn" onClick={onCheckin}>
            Start today's check-in
          </button>
        </section>
      ) : (
        <div className={`wb-stack${error ? " wellbeing--stale" : ""}`}>
          {a.level === "baseline_pending" ? (
            <Calibrating a={a} timeline={t} minDays={params.data?.baseline_min_days ?? null} />
          ) : (
            <Summary a={a} />
          )}

          <Panel title="Indicators">
            <p className="wellbeing__faint">
              Green band = your usual range · dashed line = threshold z {threshold} (PROV.) · right = further
              from your usual
            </p>
            <div className="wb-inds">
              <div className="wb-ind__row wb-ind__row--head" aria-hidden="true">
                <span>Indicator</span>
                <span>Status</span>
                <span>Today vs. your baseline</span>
                <span className="wb-ind__z">z</span>
                <span>Sources</span>
                <span>Origin</span>
                <span />
              </div>
              {a.indicators.map((ind) => (
                <IndicatorRow
                  key={ind.kind}
                  indicator={ind}
                  threshold={threshold}
                  today={today}
                  expanded={open[ind.kind] ?? false}
                  onToggle={() => setOpen((o) => ({ ...o, [ind.kind]: !o[ind.kind] }))}
                />
              ))}
            </div>
          </Panel>

          {t ? <WellbeingTimeline timeline={t} /> : null}
        </div>
      )}
    </div>
  );
}

const SUMMARY_HEADING = "Your wellbeing · compared with your own usual";

function Sentence({ a }: { a: WellbeingAssessment }) {
  if (a.level === "stale") {
    return (
      <p className="wb-summary__sentence">
        Last data <strong>{a.latest_day ? formatDay(a.latest_day) : "---"}</strong>. Nothing newer has
        arrived.
      </p>
    );
  }
  if (a.sustained_days > 0) {
    return (
      <p className="wb-summary__sentence">
        Several signals have stayed away from your usual for <strong>{days(a.sustained_days)}</strong>
        {a.onset_date ? (
          <>
            , since <strong>{formatDayLong(a.onset_date)}</strong>
          </>
        ) : null}
        .
      </p>
    );
  }
  return (
    <p className="wb-summary__sentence">
      {a.level === "ok"
        ? "Your signals are within your usual range."
        : a.level === "no_data"
          ? "There is not enough recent data to compare with your usual."
          : "Some signals have moved away from your usual."}
    </p>
  );
}

function Summary({ a }: { a: WellbeingAssessment }) {
  const stats: [string, ReactNode][] = [
    ["Since", <span className="wb-mono">{a.onset_date ? formatDay(a.onset_date) : "---"}</span>],
    ["Sustained", <span className="wb-mono">{a.sustained_days > 0 ? days(a.sustained_days) : "---"}</span>],
    ["Trend", <TrendMark trend={a.trend} />],
    ["Confidence", <ConfidenceMeter confidence={a.confidence} />],
    ["Agreeing sources", sourcesText(a.sustained_sources)],
  ];
  return (
    <section className={`wb-summary wb-summary--${a.level}`} aria-labelledby="wb-sum-h">
      <div className="wb-summary__main">
        <h2 id="wb-sum-h" className="wb-summary__h">
          {SUMMARY_HEADING}
        </h2>
        <div className="wb-summary__marks">
          <WellbeingPill level={a.level} size="lg" />
          <span className="prov">PROV.</span>
          <OriginMark origin={a.latest_origin} />
        </div>
        <Sentence a={a} />
        <dl className="wb-stats">
          {stats.map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd>{value}</dd>
            </div>
          ))}
        </dl>
        {a.discrepancy ? (
          <div className="wb-discrepancy" role="note">
            <WellbeingIcon kind="discrepancy" size={22} />
            <div>
              <strong>Your check-ins and other signals don't match</strong>
              <span>
                Your check-ins say you're fine, but other signals have changed for several days. Both can be
                true. It may be worth a moment to reflect, or to talk to someone.
              </span>
              <span className="wellbeing__faint">Changed: {sourcesText(a.sustained_sources)}</span>
            </div>
          </div>
        ) : null}
      </div>
      <div className="wb-summary__side">
        {a.support_notes.length > 0 ? (
          <div className="wb-help">
            <strong>What might help</strong>
            <ul>
              {a.support_notes.map((n) => (
                <li key={n}>{n}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {a.data_notices.map((n) => (
          <p key={n} className="wb-notice" role="note">
            <WellbeingIcon kind="info" size={16} />
            {n}
          </p>
        ))}
      </div>
    </section>
  );
}

interface CalibratingProps {
  a: WellbeingAssessment;
  timeline: Timeline | null;
  minDays: number | null;
}

function Calibrating({ a, timeline, minDays }: CalibratingProps) {
  // shortcut: baseline progress approximated from days with data; ask backend for min_baseline_days per person
  const have = timeline?.days.filter((d) => d.has_data).length ?? 0;
  const n = minDays === null ? have : Math.min(have, minDays);
  return (
    <section className="wb-summary wb-summary--baseline_pending wb-calib" aria-labelledby="wb-sum-h">
      <h2 id="wb-sum-h" className="wb-summary__h">
        {SUMMARY_HEADING}
      </h2>
      <div className="wb-summary__marks">
        <WellbeingPill level="baseline_pending" size="lg" />
        <span className="prov">PROV.</span>
        <OriginMark origin={a.latest_origin} />
      </div>
      <p className="wb-summary__sentence">
        Building your personal baseline. Changes will be shown once we know your usual.
      </p>
      {minDays !== null ? (
        <>
          <div className="wb-calib__bar" role="img" aria-label={`${n} of ${minDays} baseline days`}>
            {Array.from({ length: minDays }, (_, i) => (
              <span key={i} className={i < n ? "wb-calib__seg wb-calib__seg--on" : "wb-calib__seg"} />
            ))}
          </div>
          <span className="wellbeing__note">
            {n} of {minDays} days · keep doing your daily check-in
          </span>
        </>
      ) : null}
    </section>
  );
}
