import { useState } from "react";
import type { Astronaut, EvidenceFlag, Incident } from "../api/types";
import { acknowledgeIncident, listIncidents } from "../api/incidents";
import { HttpError, toApiError } from "../api/client";
import { usePolling } from "../hooks/usePolling";
import { formatUtcDateTime } from "../lib/format";
import { STEP_GROUPS } from "../lib/assistant";
import {
  EVIDENCE_FLAG_LABELS,
  ackLabels,
  defaultAcknowledger,
  groundLabel,
  guidanceMissing,
  ruleLabel,
} from "../lib/incident";
import { StateIcon } from "./StatusPill";

/** Small evidence-quality labels on a finding. */
export function EvidenceFlags({ flags }: { flags?: EvidenceFlag[] }) {
  if (!flags || flags.length === 0) return null;
  return (
    <>
      {flags.map((f) => (
        <span key={f} className="msg__tag evidence-flag">
          {EVIDENCE_FLAG_LABELS[f]}
        </span>
      ))}
    </>
  );
}

function IncidentCard({ incident, crew, onChanged }: { incident: Incident; crew: Astronaut[]; onChanged: () => void }) {
  const [by, setBy] = useState(() => defaultAcknowledger(crew, incident.astronaut_id));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const name = (id: string | null) => crew.find((a) => a.id === id)?.display_name ?? id ?? "Unknown";
  const next = incident.steps[0]?.text ?? incident.action;
  const acked = incident.acknowledgments.some((a) => a.acknowledged_by === by);

  const acknowledge = async () => {
    setBusy(true);
    setError(null);
    try {
      await acknowledgeIncident(incident.id, by);
      onChanged();
    } catch (err) {
      const e = toApiError(err);
      setError(e instanceof HttpError ? `Error ${e.status}: ${e.detail}` : "ONBOARD SERVICE UNAVAILABLE: not acknowledged.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className="incident" role="alert">
      <header className="incident__head">
        <StateIcon state="alert" />
        <strong>Open incident · {name(incident.astronaut_id)}</strong>
        <span className="incident__since">since {formatUtcDateTime(incident.began_at)} UTC</span>
      </header>
      {next ? (
        <p className="incident__next">
          <span className="incident__label">Next action</span> {next}
        </p>
      ) : null}
      <div className="incident__ack">
        <label>
          Acknowledged by
          <select value={by} onChange={(e) => setBy(e.target.value)}>
            {crew.map((a) => (
              <option key={a.id} value={a.id}>
                {a.display_name}
              </option>
            ))}
          </select>
        </label>
        <button type="button" className="btn incident__ack-btn" disabled={busy || !by || acked} onClick={() => void acknowledge()}>
          {acked ? "Acknowledged" : busy ? "Acknowledging…" : "Acknowledge"}
        </button>
      </div>
      {error ? <p className="incident__error">{error}</p> : null}
      <ul className="incident__states">
        {ackLabels(incident).map((l) => (
          <li key={l}>{l}</li>
        ))}
        <li>{groundLabel(incident)}</li>
      </ul>
      {guidanceMissing(incident) ? (
        <div className="incident__guidance">
          <strong>Mission guidance not loaded</strong>
          <ul>
            {incident.mission_procedures
              .filter((p) => !p.loaded)
              .map((p) => (
                <li key={p.title}>{p.title}: use the mission's own copy.</li>
              ))}
            {incident.missing_guidance.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <details className="incident__more">
        <summary>Full checklist, evidence and rules</summary>
        {incident.action ? <p>{incident.action}</p> : null}
        {STEP_GROUPS.map(({ who, label }) => {
          const group = incident.steps.filter((s) => s.who === who);
          return group.length > 0 ? (
            <div key={who}>
              <strong>{label}</strong>
              <ol>
                {group.map((s) => (
                  <li key={s.text}>{s.text}</li>
                ))}
              </ol>
            </div>
          ) : null;
        })}
        {incident.findings.length > 0 ? (
          <ul>
            {incident.findings.map((f, i) => (
              <li key={i}>
                {f.detail} <EvidenceFlags flags={f.evidence_flags} />
              </li>
            ))}
          </ul>
        ) : null}
        {incident.matched_rules.length > 0 ? (
          <p className="msg__meta">
            <strong>Matched rules:</strong> {incident.matched_rules.map(ruleLabel).join(", ")}
          </p>
        ) : null}
      </details>
    </article>
  );
}

/** Open incidents from onboard-api. State comes only from polling, never from chat history. */
export function IncidentPanel({ crew }: { crew: Astronaut[] }) {
  const open = usePolling("incidents:open", (signal) => listIncidents("open", signal), 5000);
  if (!open.data || open.data.length === 0) return null;
  return (
    <section className="incidents" aria-label="Open incidents">
      {open.data.map((i) => (
        <IncidentCard key={i.id} incident={i} crew={crew} onChanged={open.refresh} />
      ))}
    </section>
  );
}
