import { useEffect, useRef, useState, type FormEvent } from "react";
import type { AssistantResponse, AstronautStatus, ReadingStatus } from "../api/types";
import { sendAssistantMessage } from "../api/assistant";
import { HttpError, NetworkError, toApiError } from "../api/client";
import { Panel } from "../components/Panel";
import { StateIcon, type VisualState } from "../components/StatusPill";
import { useNow } from "../hooks/useNow";
import { formatAge, formatUtcTime } from "../lib/format";
import { URINE_KINDS, aggregateUrine, findSensor, liveAge } from "../lib/sensors";

interface Props {
  astronautId: string | null;
  /** Latest status of the selected crew member, for the "what the assistant can see" list. */
  status: AstronautStatus | null;
  statusUpdatedAt: number | null;
}

type Entry =
  | { id: number; at: number; role: "user"; text: string }
  | { id: number; at: number; role: "assistant"; response: AssistantResponse }
  | { id: number; at: number; role: "error"; text: string };

type WithoutMeta<T> = T extends unknown ? Omit<T, "id" | "at"> : never;
type NewEntry = WithoutMeta<Entry>;

const DISCLAIMER = "Información de apoyo, no es un diagnóstico.";
const SUGGESTIONS = ["Resume mi estado de hoy", "¿Qué datos me faltan por medir?"];

function AssistantReply({ response, at }: { response: AssistantResponse; at: number }) {
  const clarification = response.needs_clarification;
  return (
    <article className={clarification ? "msg msg--clarification" : "msg msg--answer"}>
      <span className="msg__who">
        {clarification ? "Pregunta de aclaración" : "Asistente"} · {formatUtcTime(at)} UTC
      </span>
      <p className="msg__text">{response.reply}</p>
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
        <span className="msg__sources">
          <strong>Fuentes:</strong> {response.sources.map((s) => s.title).join(" · ")}
        </span>
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

export function AsistenteScreen({ astronautId, status, statusUpdatedAt }: Props) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [draft, setDraft] = useState("");
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

  const send = async (text: string) => {
    const message = text.trim();
    if (!message || sending) return;
    push({ role: "user", text: message });
    setDraft("");
    setSending(true);
    const controller = new AbortController();
    controllerRef.current = controller;
    try {
      const response = await sendAssistantMessage(
        { message, astronaut_id: astronautId },
        controller.signal,
      );
      push({ role: "assistant", response });
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
                <div className="msg__bubble">{entry.text}</div>
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
            <button key={s} type="button" className="btn btn--ghost" disabled={sending} onClick={() => void send(s)}>
              {s}
            </button>
          ))}
        </div>
      </Panel>
    </div>
  );
}
