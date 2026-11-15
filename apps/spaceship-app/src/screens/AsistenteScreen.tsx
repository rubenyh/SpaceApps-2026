import { useEffect, useRef, useState, type FormEvent, type MouseEvent } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import {
  SYMPTOM_CODES,
  type AssistantRequest,
  type AssistantResponse,
  type Astronaut,
  type AstronautStatus,
  type CaseReport,
  type CaseReportStatus,
  type Finding,
  type ReportedSymptom,
  type SymptomCode,
  type SymptomStatus,
} from "../api/types";
import { sendAssistantMessage } from "../api/assistant";
import { getCaseReport, sendCaseReport } from "../api/caseReports";
import { HttpError, NetworkError, toApiError } from "../api/client";
import { EvidenceFlags, IncidentPanel } from "../components/IncidentPanel";
import { LiveReadings, SnapshotReadings } from "../components/AssessmentReadings";
import { Panel } from "../components/Panel";
import { StateIcon } from "../components/StatusPill";
import { usePolling } from "../hooks/usePolling";
import { formatUtcDateTime, formatUtcTime } from "../lib/format";
import {
  CAUSE_STATUS_LABELS,
  STEP_GROUPS,
  SYMPTOM_LABELS,
  SYMPTOM_STATUS_LABELS,
  TRANSMISSION_LABELS,
  assessmentOf,
  buildRequest,
  explanation,
  isNearBottom,
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

/** Crew-reviewed report: preview, copy, and an explicit send to base with its delivery state. */
function CaseReportBox({ report, sentBy }: { report: CaseReport; sentBy: string | null }) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState<"idle" | "copied" | "failed">("idle");
  const [status, setStatus] = useState<CaseReportStatus | null>(null);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const id = report.id ?? null;
  const transmission = status?.status ?? report.transmission;
  const poll = usePolling(
    id && transmission === "queued" ? `case-report:${id}` : null,
    (signal) => getCaseReport(id as string, signal),
    3000,
  );
  useEffect(() => {
    if (poll.data) setStatus(poll.data);
  }, [poll.data]);

  const copy = () =>
    navigator.clipboard.writeText(report.text).then(
      () => setCopied("copied"),
      () => setCopied("failed"),
    );
  const send = async () => {
    if (!id) return;
    setSending(true);
    setSendError(null);
    try {
      setStatus(await sendCaseReport(id, sentBy));
    } catch (err) {
      const e = toApiError(err);
      setSendError(e instanceof HttpError ? `Error ${e.status}: ${e.detail}` : "Onboard service unreachable: not sent.");
    } finally {
      setSending(false);
    }
  };

  return (
    <section className="report">
      <div className="report__head">
        <button type="button" className="btn btn--ghost" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          Review &amp; send to base
        </button>
        <span className={`msg__tag report__status report__status--${transmission}`}>
          {TRANSMISSION_LABELS[transmission]}
        </span>
      </div>
      {transmission === "received" && status?.received_at ? (
        <p className="caption">Received by base at {formatUtcDateTime(status.received_at)} UTC</p>
      ) : null}
      {transmission === "failed" ? (
        <p className="caption report__error">Base rejected the report: {status?.error ?? "unknown reason"}</p>
      ) : null}
      {sendError ? <p className="caption report__error">{sendError}</p> : null}
      {open ? (
        <>
          <pre className="report__text">{report.text}</pre>
          <SnapshotReadings readings={report.readings ?? []} title="Readings in this report" />
          <div className="report__head">
            <button type="button" className="btn btn--ghost" onClick={() => void copy()}>
              {copied === "copied" ? "Copied" : "Copy report"}
            </button>
            {id ? (
              <button
                type="button"
                className="btn"
                disabled={sending || transmission === "queued" || transmission === "received"}
                onClick={() => void send()}
              >
                {sending ? "Sending…" : transmission === "failed" ? "Retry send to base" : "Send to base"}
              </button>
            ) : (
              <span className="caption">This onboard service cannot send reports: copy it instead.</span>
            )}
          </div>
          {copied === "failed" ? <p className="caption">Copy failed: select the text and copy it by hand.</p> : null}
        </>
      ) : null}
    </section>
  );
}

/** Glanceable head of a clinical reply: urgency, what was reported, the action, when to escalate. */
function AssessmentCard({
  response,
  headingId,
  sentBy,
}: {
  response: AssistantResponse;
  headingId: string;
  sentBy: string | null;
}) {
  const a = assessmentOf(response);
  if (!a) return null;
  const procedures = response.mission_procedures ?? [];
  return (
    <div className={`triage triage--${a.urgency}`} role={a.urgency === "immediate" ? "alert" : undefined}>
      <h3 id={headingId} tabIndex={-1} className="triage__label">
        {a.urgency === "immediate" ? <StateIcon state="alert" /> : null}
        {a.urgency_label}
      </h3>
      {a.reported ? <p className="triage__reported">{a.reported}</p> : null}
      {a.action ? <p className="triage__action">{a.action}</p> : null}
      {a.escalation.length > 0 ? (
        <ul className="triage__escalation" aria-label="When to escalate">
          {a.escalation.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      ) : null}
      {procedures.map((p) => (
        <p key={p.title} className="triage__procedure">
          <strong>Mission procedure:</strong> {p.title}
          {p.loaded ? null : " — not loaded in the assistant: use the mission's own copy."}
        </p>
      ))}
      {response.notify.length > 0 ? (
        <p className="triage__notify">
          <strong>Tell (nothing is sent automatically):</strong> {response.notify.join(", ")}
        </p>
      ) : null}
      {a.urgency === "immediate" && response.matched_rules.length > 0 ? (
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
      {response.report ? <CaseReportBox report={response.report} sentBy={sentBy} /> : null}
    </div>
  );
}

function Notices({ notices }: { notices: string[] }) {
  return notices.length > 0 ? (
    <ul className="msg__notices" aria-label="Data notices">
      {notices.map((n, i) => (
        <li key={i}>
          <StateIcon state="stale" size={15} />
          {n}
        </li>
      ))}
    </ul>
  ) : null;
}

function Disclaimer({ text }: { text: string | null }) {
  return (
    <div className="msg__disclaimer">
      <StateIcon state="doubtful" />
      {text ?? DISCLAIMER}
    </div>
  );
}

/** Status summary: text and the timestamped readings it used. No assessment card. */
function StatusReply({ response, at, headingId }: { response: AssistantResponse; at: number; headingId: string }) {
  return (
    <article className="msg msg--answer">
      <h3 id={headingId} tabIndex={-1} className="msg__who">
        Status · {formatUtcTime(at)} UTC
      </h3>
      {response.reply ? <p className="msg__text">{response.reply}</p> : null}
      <SnapshotReadings readings={response.readings_snapshot ?? []} assessedAt={response.assessed_at} />
      <Notices notices={response.data_notices} />
      <Disclaimer text={response.disclaimer} />
    </article>
  );
}

/** Card first; causes and the reply below; evidence, checklist and sources folded away. Each once. */
function AssistantReply({
  response,
  at,
  headingId,
  sentBy,
}: {
  response: AssistantResponse;
  at: number;
  headingId: string;
  sentBy: string | null;
}) {
  const clarification = response.needs_clarification;
  const steps = response.steps ?? [];
  const missing = response.missing_guidance ?? [];
  const causes = response.possible_causes;
  const missingInfo = [...new Set(causes.flatMap((c) => c.missing_data))];
  const text = explanation(response);
  const hasCard = assessmentOf(response) !== null;
  const who = `${clarification ? "Clarifying question" : "Assistant"} · ${formatUtcTime(at)} UTC`;
  const sourceIndex = (id: string) => String(response.sources.findIndex((s) => s.id === id) + 1 || "?");
  const hasDetails =
    steps.length > 0 ||
    response.findings.length > 0 ||
    response.sources.length > 0 ||
    missing.length > 0 ||
    response.protocol_id !== null ||
    response.matched_rules.length > 0;
  return (
    <article className={clarification ? "msg msg--clarification" : "msg msg--answer"}>
      {hasCard ? (
        <span className="msg__who">{who}</span>
      ) : (
        <h3 id={headingId} tabIndex={-1} className="msg__who">
          {who}
        </h3>
      )}
      <AssessmentCard response={response} headingId={headingId} sentBy={sentBy} />
      {clarification && response.clarifying_question ? (
        <p className="msg__question">{response.clarifying_question}</p>
      ) : null}
      {causes.length > 0 ? (
        <section className="msg__section">
          <h4>Possible causes (not ranked)</h4>
          <p className="caption">Each could fit what was reported; none is confirmed.</p>
          <ul>
            {causes.map((c) => (
              <li key={c.id}>
                {c.label} · {CAUSE_STATUS_LABELS[c.status]}
                {c.evidence_for.length > 0 ? <div>May be supported by: {c.evidence_for.join(", ")}</div> : null}
              </li>
            ))}
          </ul>
          {missingInfo.length > 0 ? (
            <>
              <h4>Most relevant missing information</h4>
              <ul>
                {missingInfo.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            </>
          ) : null}
        </section>
      ) : null}
      {text ? <p className="msg__text">{text}</p> : null}
      <Notices notices={response.data_notices} />
      {hasDetails ? (
        <details className="msg__rules">
          <summary>Evidence, checklist &amp; sources</summary>
          {STEP_GROUPS.map(({ who: group, label }) => {
            const groupSteps = steps.filter((s) => s.who === group);
            return groupSteps.length > 0 ? (
              <div key={group} className="msg__section">
                <h4>{label}</h4>
                <ol>
                  {groupSteps.map((s) => (
                    <li key={s.text}>
                      {s.text} <span className="msg__source">[{s.source_ids.map(sourceIndex).join(", ")}]</span>
                    </li>
                  ))}
                </ol>
              </div>
            ) : null;
          })}
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
          {response.sources.length > 0 ? (
            <section className="msg__section msg__sources">
              <h4>Sources</h4>
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
          {missing.length > 0 ? (
            <section className="msg__section">
              <h4>Procedure gaps</h4>
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
          {response.matched_rules.length > 0 ? (
            <section className="msg__section">
              <h4>Technical trace</h4>
              <ul>
                {response.matched_rules.map((r) => (
                  <li key={r.rule_id}>
                    {r.rule_id} · {r.protocol_id}@{r.protocol_version} · {r.urgency}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </details>
      ) : null}
      <Disclaimer text={response.disclaimer} />
    </article>
  );
}

const headingIdOf = (entryId: number) => `reply-${entryId}`;
const scrollBehavior = (): ScrollBehavior =>
  window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth";

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
  /** Measured on scroll, i.e. before the next render appends content. */
  const nearBottomRef = useRef(true);
  const lastSeenRef = useRef(0);
  /** Heading id of a reply that arrived while the crew was reading further up. */
  const [jumpTo, setJumpTo] = useState<string | null>(null);

  useEffect(() => {
    inputRef.current?.focus();
    return () => controllerRef.current?.abort();
  }, []);

  useEffect(() => {
    const log = logRef.current;
    const last = entries[entries.length - 1];
    if (!log) return;
    if (last?.role === "assistant" && last.id !== lastSeenRef.current) {
      lastSeenRef.current = last.id;
      const id = headingIdOf(last.id);
      if (nearBottomRef.current) {
        // Start of the reply, so the assessment heading and action are in view.
        document.getElementById(id)?.scrollIntoView({ block: "start", behavior: scrollBehavior() });
        setJumpTo(null);
      } else {
        setJumpTo(id);
      }
    } else if (last?.role === "user" || ((last?.role !== "assistant" || sending) && nearBottomRef.current)) {
      // Own message: always show it. Error or "Sending…": follow the bottom only if already there.
      log.scrollTo({ top: log.scrollHeight, behavior: scrollBehavior() });
    }
  }, [entries, sending]);

  const onLogScroll = () => {
    const log = logRef.current;
    if (log) nearBottomRef.current = isNearBottom(log.scrollTop, log.scrollHeight, log.clientHeight);
  };

  const jump = () => {
    const heading = jumpTo ? document.getElementById(jumpTo) : null;
    heading?.scrollIntoView({ block: "start", behavior: scrollBehavior() });
    heading?.focus({ preventScroll: true });
    setJumpTo(null);
  };

  const latestReply = [...entries].reverse().find((e) => e.role === "assistant")?.response;
  const snapshot = latestReply?.readings_snapshot ?? [];

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
      // A status reply answers a side question: the open case and the chips stay as they were.
      if (response.workflow !== "status") {
        setPending(response.needs_clarification ? { ...request, clarification: response.clarification ?? null } : null);
        if (!fresh) setSymptoms([]);
      }
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
        <div className="chat__log" ref={logRef} aria-live="polite" onScroll={onLogScroll}>
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
              entry.response.workflow === "status" ? (
                <StatusReply key={entry.id} response={entry.response} at={entry.at} headingId={headingIdOf(entry.id)} />
              ) : (
                <AssistantReply
                  key={entry.id}
                  response={entry.response}
                  at={entry.at}
                  headingId={headingIdOf(entry.id)}
                  sentBy={astronautId}
                />
              )
            ) : (
              <div key={entry.id} className="msg msg--error" role="alert">
                <StateIcon state="alert" />
                {entry.text}
              </div>
            ),
          )}
          {sending ? <div className="chat__hint">Sending…</div> : null}
        </div>
        {jumpTo ? (
          <button type="button" className="btn chat__jump" onClick={jump}>
            Jump to latest assessment
          </button>
        ) : null}
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
      <Panel title="What the assistant can see" className="asistente__side">
        <LiveReadings status={status} updatedAt={statusUpdatedAt} />
        {snapshot.length > 0 ? (
          <SnapshotReadings readings={snapshot} assessedAt={latestReply?.assessed_at} />
        ) : null}
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
