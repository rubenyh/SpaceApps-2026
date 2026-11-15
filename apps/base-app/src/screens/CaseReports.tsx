import { useEffect, useState } from "react";
import { getCaseReport, getCaseReports } from "../api/ground";
import type { CaseUrgency, CrewMember, GroundCaseReport, SensorKind } from "../api/types";
import { usePolling } from "../hooks/usePolling";
import { formatDuration, QUALITY_LABELS, readingValueText, SENSOR_LABELS } from "../lib/format";
import { utcFull } from "../lib/incidents";

const POLL_MS = 5_000;

const URGENCY: Record<CaseUrgency, { label: string; className: string }> = {
  immediate: { label: "Immediate", className: "tag tag--alert" },
  review_required: { label: "Review required", className: "tag tag--prov quality--warn" },
  undetermined: { label: "Undetermined", className: "tag tag--prov" },
  informational: { label: "Informational", className: "tag tag--prov" },
};

const FRESHNESS = { current: "Current", stale: "Stale", future: "Future date" } as const;

function Urgency({ value }: { value: CaseUrgency }) {
  const u = URGENCY[value] ?? { label: value, className: "tag tag--prov" };
  return <span className={u.className}>{u.label}</span>;
}

function Report({
  report: r,
  name,
  onOpenIncident,
}: {
  report: GroundCaseReport;
  name: (id: string | null) => string | null;
  onOpenIncident: (id: string) => void;
}) {
  const none = (text: string) => <span className="muted">{text}</span>;
  return (
    <section className="section" aria-labelledby="report-title">
      <h2 id="report-title">
        Report {r.report_id.slice(0, 8)}
        <Urgency value={r.urgency} />
      </h2>
      <dl className="facts">
        <div>
          <dt>Astronaut</dt>
          <dd>{name(r.astronaut_id) ?? none("Not named")}</dd>
        </div>
        <div>
          <dt>Reported by</dt>
          <dd>{name(r.reported_by) ?? none("The astronaut assessed")}</dd>
        </div>
        <div>
          <dt>Sent by</dt>
          <dd>{name(r.sent_by) ?? none("Not recorded")}</dd>
        </div>
        <div>
          <dt>Assessed onboard</dt>
          <dd>{utcFull(r.assessed_at)}</dd>
        </div>
        <div>
          <dt>Sent onboard</dt>
          <dd>{utcFull(r.sent_at)}</dd>
        </div>
        <div>
          <dt>Received on ground</dt>
          <dd>{utcFull(r.received_at)}</dd>
        </div>
        <div>
          <dt>Incident</dt>
          <dd>
            {r.incident_id ? (
              <button type="button" className="button" onClick={() => onOpenIncident(r.incident_id as string)}>
                Open incident {r.incident_id.slice(0, 8)}
              </button>
            ) : (
              none("No incident")
            )}
          </dd>
        </div>
        <div>
          <dt>Action presented onboard</dt>
          <dd>{r.action ?? none("No action recorded")}</dd>
        </div>
        <div>
          <dt>Knowledge version</dt>
          <dd>
            {r.knowledge_version
              ? `${r.knowledge_version.candidate_id} · ${r.knowledge_version.digest.slice(0, 12)}`
              : none("Not recorded")}
          </dd>
        </div>
      </dl>
      <h3 className="eval-subhead">Report text</h3>
      <div className="eval-answer">
        <p className="eval-reply">{r.text}</p>
      </div>
      <h3 className="eval-subhead">Readings in the report</h3>
      {r.readings.length === 0 ? (
        <p className="empty">The report carries no readings.</p>
      ) : (
        <table className="log">
          <thead>
            <tr>
              <th scope="col">Sensor</th>
              <th scope="col">Value</th>
              <th scope="col">Captured</th>
              <th scope="col">Freshness at assessment</th>
              <th scope="col">Quality</th>
              <th scope="col">Source</th>
            </tr>
          </thead>
          <tbody>
            {r.readings.map((x) => (
              <tr key={x.id}>
                <td>{SENSOR_LABELS[x.kind as SensorKind] ?? x.kind}</td>
                <td>
                  {readingValueText(x)}
                  {x.value_text === null && x.value !== null && x.unit ? ` ${x.unit}` : ""}
                  {x.simulated ? <span className="tag tag--prov">Simulated</span> : null}
                </td>
                <td>{utcFull(x.recorded_at)}</td>
                <td className={x.freshness === "current" ? undefined : "quality--warn"}>
                  {FRESHNESS[x.freshness] ?? x.freshness}
                  <span className="muted"> · {formatDuration(Math.abs(x.age_seconds))} old</span>
                </td>
                <td className={x.quality === "good" ? undefined : "quality--warn"}>{QUALITY_LABELS[x.quality] ?? x.quality}</td>
                <td>{x.source}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <p className="hint">
        Protocol {r.protocol_id ?? "--"} · Drafted {utcFull(r.created_at)} · Ship {r.ship_id} · ID {r.report_id}
      </p>
    </section>
  );
}

/** Crew-reviewed case reports sent from the ship, as stored by ground-api. */
export function CaseReports({
  crew,
  selectedId,
  onSelect,
  onOpenIncident,
}: {
  crew: CrewMember[] | null;
  selectedId: string | null;
  onSelect: (id: string) => void;
  onOpenIncident: (id: string) => void;
}) {
  const [urgency, setUrgency] = useState<CaseUrgency | "">("");
  const { data, error } = usePolling(
    `case-reports|${urgency}`,
    (s) => getCaseReports({ urgency: urgency || undefined }, s),
    POLL_MS,
  );
  // A report opened from an incident may be outside the filtered list: load it on its own.
  const inList = data?.find((r) => r.report_id === selectedId) ?? null;
  const single = usePolling(
    selectedId && data && !inList ? `case-report|${selectedId}` : null,
    (s) => getCaseReport(selectedId as string, s),
    POLL_MS,
  );
  const selected = inList ?? (single.data?.report_id === selectedId ? single.data : null);

  // Default to the newest report.
  useEffect(() => {
    if (!selectedId && data?.length) onSelect(data[0].report_id);
  }, [data, selectedId, onSelect]);

  const name = (id: string | null) => (id ? (crew?.find((m) => m.astronaut_id === id)?.display_name ?? id) : null);

  return (
    <>
      <h1 className="sr-only">Case reports</h1>
      <p className="hint">
        Read-only. Medical case reports reviewed and sent by the crew. Informational support only: diagnosis and
        treatment decisions stay with qualified personnel. Newest received first.
      </p>
      <div className="toolbar">
        <label className="toolbar__label" htmlFor="report-urgency">
          Urgency
        </label>
        <select id="report-urgency" value={urgency} onChange={(e) => setUrgency(e.target.value as CaseUrgency | "")}>
          <option value="">All</option>
          {(Object.keys(URGENCY) as CaseUrgency[]).map((k) => (
            <option key={k} value={k}>
              {URGENCY[k].label}
            </option>
          ))}
        </select>
      </div>
      {error ? (
        <p className="empty" role="alert">
          {error.kind === "network" ? "Ground service unreachable." : `Ground service error (${error.message}).`}{" "}
          {data ? "Showing the last reports received; retrying automatically." : "Retrying automatically."}
        </p>
      ) : null}
      {data === null && !error ? <p className="empty">Loading reports…</p> : null}
      {data?.length === 0 ? <p className="empty">No case reports have reached ground{urgency ? " with this urgency" : ""}.</p> : null}
      {data?.length ? (
        <table className="log">
          <thead>
            <tr>
              <th scope="col">Report</th>
              <th scope="col">Astronaut</th>
              <th scope="col">Urgency</th>
              <th scope="col">Assessed onboard</th>
              <th scope="col">Received on ground</th>
            </tr>
          </thead>
          <tbody>
            {data.map((r) => (
              <tr key={r.report_id}>
                <td>
                  <button
                    type="button"
                    className="button"
                    aria-pressed={r.report_id === selectedId}
                    onClick={() => onSelect(r.report_id)}
                  >
                    {r.report_id === selectedId ? "▸ " : ""}
                    {r.report_id.slice(0, 8)}
                  </button>
                </td>
                <td>{name(r.astronaut_id) ?? <span className="muted">Not named</span>}</td>
                <td>
                  <Urgency value={r.urgency} />
                </td>
                <td>{utcFull(r.assessed_at)}</td>
                <td>{utcFull(r.received_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      {selected ? (
        <Report report={selected} name={name} onOpenIncident={onOpenIncident} />
      ) : selectedId && single.error ? (
        <p className="empty" role="alert">
          {single.error.kind === "http" && single.error.status === 404
            ? `Report ${selectedId.slice(0, 8)} has not reached ground.`
            : `Could not load report ${selectedId.slice(0, 8)} (${single.error.message}).`}
        </p>
      ) : null}
    </>
  );
}
