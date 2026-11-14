import { useEffect, useRef, useState, type FormEvent, type MouseEvent } from "react";
import { openUrl } from "@tauri-apps/plugin-opener";
import {
  SYMPTOM_CODES,
  type AssistantRequest,
  type AssistantResponse,
  type Astronaut,
  type AstronautStatus,
  type Finding,
  type ReadingStatus,
  type ReportedSymptom,
  type SymptomCode,
  type SymptomStatus,
} from "../api/types";
import { sendAssistantMessage } from "../api/assistant";
import { HttpError, NetworkError, toApiError } from "../api/client";
import { Panel } from "../components/Panel";
import { StateIcon, type VisualState } from "../components/StatusPill";
import { useNow } from "../hooks/useNow";
import { formatAge, formatUtcTime } from "../lib/format";
import { URINE_KINDS, aggregateUrine, findSensor, liveAge } from "../lib/sensors";
import {
  CAUSE_STATUS_LABELS,
  SYMPTOM_LABELS,
  SYMPTOM_STATUS_LABELS,
  URGENCY_LABELS,
  buildRequest,
  mergeSymptoms,
} from "../lib/assistant";

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

const DISCLAIMER = "Información de apoyo, no es un diagnóstico.";
const SUGGESTIONS = ["Resume mi estado de hoy", "¿Qué datos me faltan por medir?"];
const FINDING_LABELS: Record<Finding["kind"], string> = {
  symptom: "Síntoma",
  reading: "Lectura",
  event: "Evento",
  data_gap: "Dato ausente",
};
const SORTED_CODES = [...SYMPTOM_CODES].sort((a, b) => SYMPTOM_LABELS[a].localeCompare(SYMPTOM_LABELS[b], "es"));

function openExternal(e: MouseEvent<HTMLAnchorElement>, url: string) {
  e.preventDefault();
  // Plain browser (vite dev without Tauri): fall back to a new tab.
  openUrl(url).catch(() => window.open(url, "_blank", "noopener"));
}

function symptomText(s: ReportedSymptom): string {
  return `${SYMPTOM_LABELS[s.symptom]}: ${SYMPTOM_STATUS_LABELS[s.status ?? "present"]}`;
}

/** Fields in the order of docs/assistant-frontend-integration.md ("Qué mostrar y en qué orden"). */
function AssistantReply({ response, at }: { response: AssistantResponse; at: number }) {
  const clarification = response.needs_clarification;
  const urgency = response.urgency;
  return (
    <article className={clarification ? "msg msg--clarification" : "msg msg--answer"}>
      <span className="msg__who">
        {clarification ? "Pregunta de aclaración" : "Asistente"} · {formatUtcTime(at)} UTC
      </span>
      {urgency ? (
        <div className={`triage triage--${urgency}`} role={urgency === "immediate" ? "alert" : undefined}>
          <strong className="triage__label">
            {urgency === "immediate" ? <StateIcon state="alert" /> : null}
            {URGENCY_LABELS[urgency]}
          </strong>
          {response.action ? <p className="triage__action">{response.action}</p> : null}
          {response.notify.length > 0 ? (
            <p className="triage__notify">
              <strong>Avisar a:</strong> {response.notify.join(", ")}
            </p>
          ) : null}
        </div>
      ) : null}
      <p className="msg__text">{response.reply}</p>
      {clarification && response.clarifying_question ? (
        <p className="msg__question">{response.clarifying_question}</p>
      ) : null}
      {response.protocol_id ? (
        <p className="msg__meta">
          <strong>Ficha:</strong> {response.protocol_id}
          {response.additional_protocol_ids.length > 0
            ? ` · Fichas adicionales: ${response.additional_protocol_ids.join(", ")}`
            : null}
        </p>
      ) : null}
      {response.findings.length > 0 ? (
        <section className="msg__section">
          <h4>Evidencia usada</h4>
          <ul>
            {response.findings.map((f, i) => (
              <li key={i}>
                <span className="msg__tag">{FINDING_LABELS[f.kind]}</span> {f.detail}{" "}
                <span className="msg__source">({f.source})</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {response.possible_causes.length > 0 ? (
        <section className="msg__section">
          <h4>Causas a considerar (sin orden de probabilidad)</h4>
          <ul>
            {response.possible_causes.map((c) => (
              <li key={c.id}>
                {c.label} <span className="msg__tag">{CAUSE_STATUS_LABELS[c.status]}</span>
                {c.evidence_for.length > 0 ? <div>A favor: {c.evidence_for.join(", ")}</div> : null}
                {c.missing_data.length > 0 ? <div>Falta: {c.missing_data.join(", ")}</div> : null}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      {response.data_notices.length > 0 ? (
        <ul className="msg__notices" aria-label="Avisos de datos">
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
          <strong>Fuentes:</strong>
          <ul>
            {response.sources.map((s) => (
              <li key={s.id}>
                <span className="msg__tag">{s.kind === "protocol" ? "Ficha revisada" : "Guía"}</span>{" "}
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
          </ul>
        </section>
      ) : null}
      {response.matched_rules.length > 0 ? (
        <details className="msg__rules">
          <summary>Trazabilidad técnica</summary>
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
    { label: "Pulso", ...one("heart_rate") },
    { label: "Oxígeno (SpO₂)", ...one("spo2") },
    {
      label: "Orina",
      state: aggregateUrine(urine),
      age: urineAges.length > 0 ? Math.min(...urineAges) : null,
    },
    { label: "Músculo", ...one("muscle_density") },
    {
      label: "Radiación",
      state: radiation?.latest ? "doubtful" : "no_data",
      age: liveAge(radiation, updatedAt, now),
    },
  ];
  return (
    <ul className="visible">
      {rows.map((r) => (
        <li key={r.label}>
          <span className={`visible__name visible__name--${r.state}`}>
            <StateIcon state={r.state} />
            {r.label}
          </span>
          <span className={r.state === "stale" ? "visible__age visible__age--stale" : "visible__age"}>
            {status === null ? "…" : r.age === null ? "nunca medido" : formatAge(r.age)}
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
      setPending(response.needs_clarification ? request : null);
      if (!fresh) setSymptoms([]);
    } catch (err) {
      if (controller.signal.aborted) return;
      const apiError = toApiError(err);
      const errorText =
        apiError instanceof HttpError
          ? `Error ${apiError.status}: ${apiError.detail}`
          : apiError instanceof NetworkError
            ? "SERVICIO ONBOARD NO DISPONIBLE: el mensaje no se ha enviado."
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
        <div className="chat__log" ref={logRef} aria-live="polite">
          {entries.length === 0 ? (
            <p className="chat__hint">
              Escribe una pregunta sobre tus lecturas. El historial se borra al salir de esta pestaña.
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
                <span className="msg__when">Tú · {formatUtcTime(entry.at)} UTC</span>
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
          {sending ? <div className="chat__hint">Enviando…</div> : null}
        </div>
        <div className="chat__report">
          {pending ? (
            <p className="chat__pending">
              Respondiendo a la pregunta de aclaración: se reenvía el reporte original.{" "}
              <button type="button" className="btn btn--ghost" onClick={() => setPending(null)}>
                Nuevo reporte
              </button>
            </p>
          ) : (
            <label>
              Informa
              <select value={reportedBy} onChange={(e) => setReportedBy(e.target.value)}>
                <option value="">La persona evaluada</option>
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
            Síntoma
            <select value={code} onChange={(e) => setCode(e.target.value as SymptomCode)}>
              {SORTED_CODES.map((c) => (
                <option key={c} value={c}>
                  {SYMPTOM_LABELS[c]}
                </option>
              ))}
            </select>
          </label>
          <select
            aria-label="¿Presente?"
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
            Añadir
          </button>
          {symptoms.length > 0 ? (
            <ul className="chat__chips" aria-label="Síntomas que se enviarán">
              {symptoms.map((s) => (
                <li key={s.symptom}>
                  {symptomText(s)}
                  <button
                    type="button"
                    aria-label={`Quitar ${SYMPTOM_LABELS[s.symptom]}`}
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
            placeholder="Escribe tu pregunta…"
            aria-label="Escribe tu pregunta"
            autoComplete="off"
          />
          <button type="submit" className="btn" disabled={sending || draft.trim() === ""}>
            {sending ? "Enviando…" : "Enviar"}
          </button>
        </form>
      </section>
      <Panel title="Lo que el asistente puede ver">
        <VisibleData status={status} updatedAt={statusUpdatedAt} />
        <p className="caption">
          El asistente solo usa las lecturas de esta consola. Avisa cuando un dato falta o es viejo y
          nunca diagnostica.
        </p>
        <div className="suggestions">
          <span className="caption">Prueba a preguntar</span>
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
