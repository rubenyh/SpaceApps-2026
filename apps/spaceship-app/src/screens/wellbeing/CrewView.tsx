import type { ReactNode } from "react";
import type { CrewMemberSummary, WellbeingParameters } from "../../api/types";
import { getCrewWellbeing, getWellbeing, getWellbeingParameters } from "../../api/wellbeing";
import { Panel } from "../../components/Panel";
import { OriginMark, TrendMark, WellbeingIcon, WellbeingPill } from "../../components/WellbeingMarks";
import { WellbeingServiceBanner } from "../../components/WellbeingServiceBanner";
import { ZTrack } from "../../components/ZTrack";
import { usePolling } from "../../hooks/usePolling";
import { firstName, formatClock, formatZ, missionDay, supportSuggestion, videoLogZ } from "../../lib/wellbeing";

const POLL_MS = 30_000;
const PARAMS_POLL_MS = 300_000;

/** Crew view: level, trend and origin per person only (CrewMemberSummary). */
export function CrewView({ toggle }: { toggle: ReactNode }) {
  const crew = usePolling("wb-crew", getCrewWellbeing, POLL_MS);
  const params = usePolling("wb-params", getWellbeingParameters, PARAMS_POLL_MS);
  const tz = params.data?.mission_tz ?? "UTC";
  const data = crew.data;
  const suggestions = (data?.members ?? []).flatMap((m) => {
    const s = supportSuggestion(m);
    return s ? [s] : [];
  });

  return (
    <div className="screen">
      <div className="wellbeing__bar">
        {toggle}
        <span className="wellbeing__note">
          Changes are measured against each person's own usual, not against the crew. This is not a
          diagnosis.
        </span>
        <span className="wellbeing__spacer" />
        <span className="wb-bar-end">
          <span className="prov">PROV.</span>
          {data ? (
            <span className="wellbeing__faint">
              Updated <span className="wb-mono">{formatClock(data.generated_at, tz)}</span>
            </span>
          ) : null}
        </span>
      </div>

      <div className="infobox wb-honesty" role="note">
        <WellbeingIcon kind="info" size={18} />
        <span>
          Demo data: history is <strong>SIMULATED</strong>; today's video log is{" "}
          <strong className="wb-live-text">LIVE</strong>. Thresholds are provisional and not clinically
          validated.
        </span>
      </div>

      {crew.error ? (
        <WellbeingServiceBanner error={crew.error} updatedAt={crew.updatedAt} onRetry={crew.refresh} timeZone={tz} />
      ) : !data ? (
        <div className="banner" role="status">
          <div className="banner__text">
            <span className="banner__title">Loading wellbeing…</span>
          </div>
        </div>
      ) : null}

      {data && data.members.length === 0 ? (
        <section className="empty wb-empty">
          <WellbeingIcon kind="no_data" size={32} />
          <h2>No wellbeing data yet</h2>
        </section>
      ) : data ? (
        <div className={`wb-crew${crew.error ? " wellbeing--stale" : ""}`}>
          <Panel title="Crew wellbeing" className="wb-crew__main">
            <p className="wellbeing__faint">Overall level and trend only. Personal detail stays private.</p>
            <div className="wb-cards">
              {data.members.map((m) => (
                <article key={m.astronaut_id} className={`wcard wcard--${m.level}`}>
                  <div className="wcard__head">
                    <h3>{m.display_name}</h3>
                    <OriginMark origin={m.latest_origin} />
                  </div>
                  <div className="wcard__row">
                    <WellbeingPill level={m.level} />
                    <TrendMark trend={m.trend} />
                  </div>
                </article>
              ))}
            </div>
          </Panel>

          <div className="wb-crew__side">
            <Panel title="The crew as a support network">
              <p className="wellbeing__note">Small gestures help. No need to mention this screen.</p>
              {suggestions.length > 0 ? (
                <ul className="wb-support">
                  {suggestions.map((s) => (
                    <li key={s.title}>
                      <WellbeingIcon kind="chat" />
                      <div>
                        <strong>{s.title}</strong>
                        <span>{s.gesture}</span>
                      </div>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="wb-support__none">Nobody needs a check-in right now.</p>
              )}
            </Panel>
            <VideoLog members={data.members} params={params.data} />
          </div>
        </div>
      ) : null}

      <p className="wellbeing__faint">
        All crew members agreed to wellbeing monitoring before the mission. Crew view shows level and trend
        only.
      </p>
      <details className="wb-shared wellbeing__faint">
        <summary>What is shared and with whom</summary>
        <p>
          The crew view shows only each person's overall level, trend and data origin. Indicators, check-in
          answers, comments and notes stay in Personal, behind each person's PIN. Nothing goes to the ground
          psychologist without that person's confirmation.
        </p>
      </details>
    </div>
  );
}

function VideoLog({ members, params }: { members: CrewMemberSummary[]; params: WellbeingParameters | null }) {
  // User-approved exception to "crew view uses only CrewMemberSummary": vision components of one person.
  const member = members.find((m) => m.latest_origin === "live" || m.latest_origin === "mixed") ?? null;
  const poll = usePolling(
    member ? `wb-vlog:${member.astronaut_id}` : null,
    (signal) => getWellbeing(member!.astronaut_id, signal),
    POLL_MS,
  );
  const log = poll.data && params ? videoLogZ(poll.data, missionDay(params.mission_tz)) : null;

  if (!member || !params || !log) {
    const failed = member !== null && poll.error !== null && !poll.data;
    const pending = member !== null && !failed && (!params || !poll.data);
    return (
      <Panel title="Today's video log" className="wb-vlog wb-vlog--none">
        <p className="wb-vlog__none">
          {pending ? null : <WellbeingIcon kind="no_data" />}
          {pending ? "Loading video log…" : failed ? "Video log unavailable" : "No live video log today"}
        </p>
      </Panel>
    );
  }

  const name = firstName(member.display_name);
  const rows = [
    { label: "Fatigue", z: log.fatigue },
    { label: "Tension", z: log.tension },
  ];
  const shown = rows.flatMap((r) => (r.z === null ? [] : [r.z]));
  const within = shown.every((z) => z < params.z_threshold);
  return (
    <Panel title={`Today's video log · ${name}`} aside={<OriginMark origin="live" />} className="wb-vlog">
      {/* shortcut: contract has no log time; show the day only, add when vision exposes it */}
      <p className="wellbeing__faint">Today · compared with {name}'s own baseline</p>
      <div className="wb-vlog__grid">
        {rows.map((r) => (
          <div key={r.label} className="wb-vlog__row">
            <span>{r.label}</span>
            <ZTrack z={r.z} threshold={params.z_threshold} />
            <span className="wb-mono">z {formatZ(r.z)}</span>
          </div>
        ))}
      </div>
      {shown.length > 0 ? (
        <p className={`wb-vlog__foot${within ? " wb-vlog__foot--ok" : " wb-vlog__foot--changed"}`}>
          <WellbeingIcon kind={within ? "ok" : "attention"} size={18} />
          {within ? `Within ${name}'s usual range` : `Changed vs. ${name}'s usual`}
        </p>
      ) : null}
    </Panel>
  );
}
