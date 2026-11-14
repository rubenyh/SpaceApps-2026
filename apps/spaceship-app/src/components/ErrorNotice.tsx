import { HttpError, type ApiError } from "../api/client";

interface Props {
  error: ApiError | null;
  /** Data from a previous successful poll is still on screen. */
  hasData: boolean;
}

/** Inline notice for a failed request. Network failures also show the global banner. */
export function ErrorNotice({ error, hasData }: Props) {
  if (!error) return null;
  if (error instanceof HttpError) {
    return (
      <div className="notice notice--error" role="alert">
        ERROR {error.status}: {error.detail}
      </div>
    );
  }
  return (
    <div className="notice notice--error" role="status">
      {hasData
        ? "SIN CONEXIÓN · se muestran los últimos datos recibidos (atenuados)."
        : "SIN CONEXIÓN · no hay datos previos que mostrar."}
    </div>
  );
}
