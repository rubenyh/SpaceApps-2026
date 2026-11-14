import { useEffect, useRef, useState, type FormEvent } from "react";
import type { AssistantResponse } from "../api/types";
import { sendAssistantMessage } from "../api/assistant";
import { HttpError, NetworkError, toApiError } from "../api/client";

interface Props {
  astronautId: string | null;
}

type Entry =
  | { id: number; role: "user"; text: string }
  | { id: number; role: "assistant"; response: AssistantResponse }
  | { id: number; role: "error"; text: string };

type WithoutId<T> = T extends unknown ? Omit<T, "id"> : never;
type NewEntry = WithoutId<Entry>;

function AssistantReply({ response }: { response: AssistantResponse }) {
  return (
    <div className="chat__entry chat__entry--assistant">
      <div className="chat__who">
        {response.needs_clarification ? "< PREGUNTA DEL ASISTENTE" : "< ASISTENTE"}
      </div>
      <div className="chat__text">{response.reply}</div>
      {response.data_notices.length > 0 ? (
        <div className="notices" role="note">
          <div className="notices__title">AVISOS DE DATOS</div>
          <ul>
            {response.data_notices.map((n, i) => (
              <li key={i}>! {n}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="chat__sources">
        FUENTES:{" "}
        {response.sources.length > 0
          ? response.sources.map((s) => s.title).join(" · ")
          : "(ninguna)"}
      </div>
      {response.disclaimer ? <div className="disclaimer">{response.disclaimer}</div> : null}
    </div>
  );
}

export function AsistenteScreen({ astronautId }: Props) {
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
    setEntries((prev) => [...prev, { ...entry, id } as Entry]);
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    const message = draft.trim();
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
      const text =
        apiError instanceof HttpError
          ? `ERROR ${apiError.status}: ${apiError.detail}`
          : apiError instanceof NetworkError
            ? "SERVICIO ONBOARD NO DISPONIBLE · el mensaje no se ha enviado."
            : String(apiError);
      push({ role: "error", text });
    } finally {
      if (!controller.signal.aborted) {
        setSending(false);
        // Keep focus in the input, notably after a clarifying question.
        requestAnimationFrame(() => inputRef.current?.focus());
      }
    }
  };

  return (
    <div className="screen chat">
      <div className="chat__log" ref={logRef} aria-live="polite">
        {entries.length === 0 ? (
          <p className="muted">
            Escriba una consulta sobre las lecturas del tripulante
            {astronautId ? ` ${astronautId}` : " (ninguno seleccionado)"}. El historial se borra al
            salir de esta pestaña.
          </p>
        ) : null}
        {entries.map((entry) =>
          entry.role === "user" ? (
            <div key={entry.id} className="chat__entry chat__entry--user">
              <span className="chat__who">&gt; TÚ</span> <span className="chat__text">{entry.text}</span>
            </div>
          ) : entry.role === "assistant" ? (
            <AssistantReply key={entry.id} response={entry.response} />
          ) : (
            <div key={entry.id} className="notice notice--error" role="alert">
              {entry.text}
            </div>
          ),
        )}
        {sending ? <div className="chat__sending">TRANSMITIENDO…</div> : null}
      </div>
      <form className="chat__form" onSubmit={onSubmit}>
        <span aria-hidden="true">&gt;</span>
        <input
          ref={inputRef}
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Escriba su mensaje"
          aria-label="Mensaje para el asistente"
          autoComplete="off"
        />
        <button type="submit" className="btn" disabled={sending || draft.trim() === ""}>
          {sending ? "[ENVIANDO…]" : "[ENVIAR]"}
        </button>
      </form>
    </div>
  );
}
