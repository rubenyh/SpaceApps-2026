import { useEffect, useRef, useState, type FormEvent, type MouseEvent } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import {
  SYMPTOM_CODES,
  type AssistantRequest,
  type AssistantResponse,
  type Astronaut,
  type AstronautStatus,
  type CaseReport,
  type Finding,
  type ReadingStatus,
  type ReportedSymptom,
  type SymptomCode,
  type SymptomStatus,
} from "../api/types";
import { sendAssistantMessage } from "../api/assistant";
import { HttpError, NetworkError, toApiError } from "../api/client";
import { EvidenceFlags, IncidentPanel } from "../components/IncidentPanel";
import { Panel } from "../components/Panel";
import { withSub2 } from "../components/Sub2";
import { StateIcon, type VisualState } from "../components/StatusPill";
import { useNow } from "../hooks/useNow";
import { formatAge, formatUtcTime } from "../lib/format";
import { URINE_KINDS, aggregateUrine, findSensor, liveAge } from "../lib/sensors";
import {
  CAUSE_STATUS_LABELS,
  STEP_GROUPS,
  SYMPTOM_LABELS,
  SYMPTOM_STATUS_LABELS,
  URGENCY_LABELS,
  buildRequest,
  explanation,
  mergeSymptoms,
} from "../lib/assistant";
import { ruleLabel } from "../lib/incident";

interface Props {
  astronautId: string | null;
  /** Whole crew, to pick who sends the report. */
  astronauts: Astronaut[];
  /** Latest status of the selected crew member, for the "what the assistant can see" list. */
  status: AstronautStatus | null;
  statusUpdatedAt: number | null;
}

type Entry =
  | { id: number; at: number; role: "user"; text: string; symptoms: ReportedSymptom[] }
  | { id: number; at: number; role: "assistant"; response: AssistantResponse }
  | { id: number; at: number; role: "error"; text: string };

type WithoutMeta<T> = T extends unknown ? Omit<T, "id" | "at"> : never;
type NewEntry = WithoutMeta<Entry>;

const DISCLAIMER = "Supporting information, not a diagnosis.";
const SUGGESTIONS = ["Summarize my status today", "Which readings am I missing?"];
const FINDING_LABELS: Record<Finding["kind"], string> = {
  symptom: "Symptom",
  reading: "Reading",
  event: "Event",
  data_gap: "Missing data",
};
const SORTED_CODES = [...SYMPTOM_CODES].sort((a, b) => SYMPTOM_LABELS[a].localeCompare(SYMPTOM_LABELS[b], "en"));

function openExternal(e: MouseEvent<HTMLAnchorElement>, url: string) {
  e.preventDefault();
  // Plain browser (vite dev without Tauri): fall back to a new tab.
  openUrl(url).catch(() => window.open(url, "_blank", "noopener"));
}

function symptomText(s: ReportedSymptom): string {
  return `${SYMPTOM_LABELS[s.symptom]}: ${SYMPTOM_STATUS_LABELS[s.status ?? "present"]}`;
}

/** Copyable case report. "not_sent" until a real delivery mechanism confirms transmission. */
function CaseReportBox({ report }: { report: CaseReport }) {
  const [copied, setCopied] = useState<"idle" | "copied" | "failed">("idle");
  const copy = () =>
    navigator.clipboard.writeText(report.text).then(
      () => setCopied("copied"),
      () => setCopied("failed"),
    );
  return (
    <section className="report">
      <div className="report__head">
        <strong>Report to copy</strong>
        <span className="msg__tag report__status">Not sent</span>
        <button type="button" className="btn btn--ghost" onClick={() => void copy()}>
          {copied === "copied" ? "Copied" : "Copy report"}
        </button>
      </div>
      {copied === "failed" ? <p className="caption">Copy failed: select the text and copy it by hand.</p> : null}
      <pre className="report__text">{report.text}</pre>
    </section>
  );
}

/** Action first, copyable report second, then explanation, evidence and sources. Each once. */
function AssistantReply({ response, at }: { response: AssistantResponse; at: number }) {
  const clarification = response.needs_clarification;
  const urgency = response.urgency;
  const steps = response.steps ?? [];
  const procedures = response.mission_procedures ?? [];
  const missing = response.missing_guidance ?? [];
  const text = explanation(response);
  const sourceIndex = (id: string) => String(response.sources.findIndex((s) => s.id === id) + 1 || "?");
  return (
    <article className={clarification ? "msg msg--clarification" : "msg msg--answer"}>
      <span className="msg__who">
        {clarification ? "Clarifying question" : "Assistant"} · {formatUtcTime(at)} UTC
      </span>
      {urgency ? (
        <div className={`triage triage--${urgency}`} role={urgency === "immediate" ? "alert" : undefined}>
          <strong className="triage__label">
            {urgency === "immediate" ? <StateIcon state="alert" /> : null}
            {URGENCY_LABELS[urgency]}
          </strong>
          {response.action ? <p className="triage__action">{response.action}</p> : null}
          {procedures.map((p) => (
            <p key={p.title} className="triage__procedure">
              <strong>Mission procedure:</strong> {p.title}
              {p.loaded ? null : " — not loaded in the assistant: use the mission's own copy."}
            </p>
          ))}
          {STEP_GROUPS.map(({ who, label }) => {
            const group = steps.filter((s) => s.who === who);
            return group.length > 0 ? (
              <div key={who} className="triage__steps">
                <strong>{label}</strong>
                <ol>
                  {group.map((s) => (
                    <li key={s.text}>
                      {s.text} <span className="msg__source">[{s.source_ids.map(sourceIndex).join(", ")}]</span>
                    </li>
                  ))}
                </ol>
              </div>
            ) : null;
          })}
          {response.notify.length > 0 ? (
            <p className="triage__notify">
              <strong>Tell (nothing is sent automatically):</strong> {response.notify.join(", ")}
            </p>
          ) : null}
          {urgency === "immediate" && response.matched_rules.length > 0 ? (
            <p className="triage__procedure">
              <strong>Matched rules:</strong> {response.matched_rules.map(ruleLabel).join(", ")}
            </p>
          ) : null}
          {response.incident?.recorded === false ? (
            <p className="triage__notify">
              <StateIcon state="alert" size={15} />
              <strong>Incident not recorded:</strong> {response.incident.error ?? "unknown reason"}
            </p>
          ) : null}
        </div>
      ) : null}
      {clarification && response.clarifying_question ? (
        <p className="msg__question">{response.clarifying_question}</p>
      ) : null}
      {response.report ? <CaseReportBox report={response.report} /> : null}
      {text ? <p className="msg__text">{text}</p> : null}
      {missing.length > 0 ? (
        <section className="msg__section">
          <h4>Missing guidance</h4>
          <ul>
            {missing.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {response.protocol_id ? (
        <p className="msg__meta">
          <strong>Protocol:</strong> {response.protocol_id}
          {response.additional_protocol_ids.length > 0
            ? ` · Additional protocols: ${response.additional_protocol_ids.join(", ")}`
            : null}
        </p>
      ) : null}
      {response.findings.length > 0 ? (
        <section className="msg__section">
          <h4>Evidence used</h4>
          <ul>
            {response.findings.map((f, i) => (
              <li key={i}>
                <span className="msg__tag">{FINDING_LABELS[f.kind]}</span> {f.detail}{" "}
                <span className="msg__source">({f.source})</span> <EvidenceFlags flags={f.evidence_flags} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {response.possible_causes.length > 0 ? (
        <section className="msg__section">
          <h4>Causes to consider (not ranked by likelihood)</h4>
          <ul>
            {response.possible_causes.map((c) => (
              <li key={c.id}>
                {c.label} <span className="msg__tag">{CAUSE_STATUS_LABELS[c.status]}</span>
                {c.evidence_for.length > 0 ? <div>Supporting: {c.evidence_for.join(", ")}</div> : null}
                {c.missing_data.length > 0 ? <div>Missing: {c.missing_data.join(", ")}</div> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {response.data_notices.length > 0 ? (
        <ul className="msg__notices" aria-label="Data notices">
          {response.data_notices.map((n, i) => (
            <li key={i}>
              <StateIcon state="stale" size={15} />
              {n}
            </li>
          ))}
        </ul>
      ) : null}
      {response.sources.length > 0 ? (
        <section className="msg__sources">
          <strong>Sources:</strong>
          <ol>
            {response.sources.map((s) => (
              <li key={s.id}>
                <span className="msg__tag">{s.kind === "protocol" ? "Reviewed protocol" : "Guide"}</span>{" "}
                {s.url ? (
                  <a href={s.url} onClick={(e) => openExternal(e, s.url as string)}>
                    {s.title}
                  </a>
                ) : (
                  s.title
                )}
                {s.section ? ` · ${s.section}` : null}
              </li>
            ))}
          </ol>
        </section>
      ) : null}
      {response.matched_rules.length > 0 ? (
        <details className="msg__rules">
          <summary>Technical traceability</summary>
          <ul>
            {response.matched_rules.map((r) => (
              <li key={r.rule_id}>
                {r.rule_id} · {r.protocol_id}@{r.protocol_version} · {r.urgency}
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      <div className="msg__disclaimer">
        <StateIcon state="doubtful" />
        {response.disclaimer ?? DISCLAIMER}
      </div>
    </article>
  );
}

/** What the assistant works from: each reading with its state icon and age. */
function VisibleData({ status, updatedAt }: { status: AstronautStatus | null; updatedAt: number | null }) {
  const now = useNow(1000);
  const urine = URINE_KINDS.map((k) => findSensor(status, k));
  const urineAges = urine.map((s) => liveAge(s, updatedAt, now)).filter((a): a is number => a !== null);
  const one = (kind: "heart_rate" | "spo2" | "muscle_density") => {
    const s = findSensor(status, kind);
    return { state: (s?.status ?? "no_data") as ReadingStatus, age: liveAge(s, updatedAt, now) };
  };
  const radiation = findSensor(status, "urine_radiation_marker");
  const rows: { label: string; state: VisualState; age: number | null }[] = [
    { label: "Heart rate", ...one("heart_rate") },
    { label: "Oxygen (SpO₂)", ...one("spo2") },
    {
      label: "Urine",
      state: aggregateUrine(urine),
      age: urineAges.length > 0 ? Math.min(...urineAges) : null,
    },
    { label: "Muscle", ...one("muscle_density") },
    {
      label: "Radiation",
      state: radiation?.status ?? "no_data",
      age: liveAge(radiation, updatedAt, now),
    },
  ];
  return (
    <ul className="visible">
      {rows.map((r) => (
        <li key={r.label}>
          <span className={`visible__name visible__name--${r.state}`}>
            <StateIcon state={r.state} />
            {withSub2(r.label)}
          </span>
          <span className={r.state === "stale" ? "visible__age visible__age--stale" : "visible__age"}>
            {status === null ? "…" : r.age === null ? "never measured" : formatAge(r.age)}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function AsistenteScreen({ astronautId, astronauts, status, statusUpdatedAt }: Props) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [draft, setDraft] = useState("");
  const [reportedBy, setReportedBy] = useState("");
  const [symptoms, setSymptoms] = useState<ReportedSymptom[]>([]);
  const [code, setCode] = useState<SymptomCode>(SORTED_CODES[0]);
  const [codeStatus, setCodeStatus] = useState<SymptomStatus>("present");
  /** Request whose reply asked a clarifying question; the next message answers it. */
  const [pending, setPending] = useState<AssistantRequest | null>(null);
  const [sending, setSending] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(1);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    inputRef.current?.focus();
    return () => controllerRef.current?.abort();
  }, []);

  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [entries, sending]);

  const push = (entry: NewEntry) => {
    const id = nextId.current++;
    setEntries((prev) => [...prev, { ...entry, id, at: Date.now() } as Entry]);
  };

  const send = async (text: string, fresh = false) => {
    const message = text.trim();
    if (!message || sending) return;
    const added = fresh ? [] : symptoms;
    const request = buildRequest(fresh ? null : pending, message, astronautId, reportedBy || null, added);
    push({ role: "user", text: message, symptoms: added });
    setDraft("");
    setSending(true);
    const controller = new AbortController();
    controllerRef.current = controller;
    try {
      const response = await sendAssistantMessage(request, controller.signal);
      push({ role: "assistant", response });
      setPending(response.needs_clarification ? { ...request, clarification: response.clarification ?? null } : null);
      if (!fresh) setSymptoms([]);
    } catch (err) {
      if (controller.signal.aborted) return;
      const apiError = toApiError(err);
      const errorText =
        apiError instanceof HttpError
          ? `Error ${apiError.status}: ${apiError.detail}`
          : apiError instanceof NetworkError
            ? apiError.message === "request timed out"
              ? "NO REPLY IN TIME: the onboard assistant took too long. Try again."
              : "ONBOARD SERVICE UNAVAILABLE: the message was not sent."
            : String(apiError);
      push({ role: "error", text: errorText });
    } finally {
      if (!controller.signal.aborted) {
        setSending(false);
        // Keep focus in the input, notably after a clarifying question.
        requestAnimationFrame(() => inputRef.current?.focus());
      }
    }
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void send(draft);
  };

  return (
    <div className="asistente__grid">
      <section className="chat">
        <IncidentPanel crew={astronauts} />
        <div className="chat__log" ref={logRef} aria-live="polite">
          {entries.length === 0 ? (
            <p className="chat__hint">
              Ask a question about your readings. The history is cleared when you leave this tab.
            </p>
          ) : null}
          {entries.map((entry) =>
            entry.role === "user" ? (
              <div key={entry.id} className="msg msg--user">
                <div className="msg__bubble">
                  {entry.text}
                  {entry.symptoms.length > 0 ? (
                    <span className="msg__bubble-symptoms">{entry.symptoms.map(symptomText).join(" · ")}</span>
                  ) : null}
                </div>
                <span className="msg__when">You · {formatUtcTime(entry.at)} UTC</span>
              </div>
            ) : entry.role === "assistant" ? (
              <AssistantReply key={entry.id} response={entry.response} at={entry.at} />
            ) : (
              <div key={entry.id} className="msg msg--error" role="alert">
                <StateIcon state="alert" />
                {entry.text}
              </div>
            ),
          )}
          {sending ? <div className="chat__hint">Sending…</div> : null}
        </div>
        <div className="chat__report">
          {pending ? (
            <p className="chat__pending">
              Answering the clarifying question: the open case is sent back with your answer.{" "}
              <button type="button" className="btn btn--ghost" onClick={() => setPending(null)}>
                New report
              </button>
            </p>
          ) : (
            <label>
              Reported by
              <select value={reportedBy} onChange={(e) => setReportedBy(e.target.value)}>
                <option value="">The person being assessed</option>
                {astronauts
                  .filter((a) => a.id !== astronautId)
                  .map((a) => (
                    <option key={a.id} value={a.id}>
                      {a.display_name}
                    </option>
                  ))}
              </select>
            </label>
          )}
          <label>
            Symptom
            <select value={code} onChange={(e) => setCode(e.target.value as SymptomCode)}>
              {SORTED_CODES.map((c) => (
                <option key={c} value={c}>
                  {SYMPTOM_LABELS[c]}
                </option>
              ))}
            </select>
          </label>
          <select
            aria-label="Present?"
            value={codeStatus}
            onChange={(e) => setCodeStatus(e.target.value as SymptomStatus)}
          >
            {(Object.keys(SYMPTOM_STATUS_LABELS) as SymptomStatus[]).map((st) => (
              <option key={st} value={st}>
                {SYMPTOM_STATUS_LABELS[st]}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => setSymptoms((prev) => mergeSymptoms(prev, [{ symptom: code, status: codeStatus }]))}
          >
            Add
          </button>
          {symptoms.length > 0 ? (
            <ul className="chat__chips" aria-label="Symptoms to send">
              {symptoms.map((s) => (
                <li key={s.symptom}>
                  {symptomText(s)}
                  <button
                    type="button"
                    aria-label={`Remove ${SYMPTOM_LABELS[s.symptom]}`}
                    onClick={() => setSymptoms((prev) => prev.filter((p) => p.symptom !== s.symptom))}
                  >
                    ×
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <form className="chat__form" onSubmit={onSubmit}>
          <input
            ref={inputRef}
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Type your question…"
            aria-label="Type your question"
            autoComplete="off"
          />
          <button type="submit" className="btn" disabled={sending || draft.trim() === ""}>
            {sending ? "Sending…" : "Send"}
          </button>
        </form>
      </section>
      <Panel title="What the assistant can see">
        <VisibleData status={status} updatedAt={statusUpdatedAt} />
        <p className="caption">
          The assistant only uses the readings in this console. It says when data is missing or old
          and never diagnoses.
        </p>
        <div className="suggestions">
          <span className="caption">Try asking</span>
          {SUGGESTIONS.map((s) => (
            <button key={s} type="button" className="btn btn--ghost" disabled={sending} onClick={() => void send(s, true)}>
              {s}
            </button>
          ))}
        </div>
      </Panel>
    </div>
  );
}
