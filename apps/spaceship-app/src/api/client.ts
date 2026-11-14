// Thin fetch wrapper for the onboard API with typed errors.

const DEFAULT_BASE_URL = "http://127.0.0.1:8000";
const REQUEST_TIMEOUT_MS = 10_000;

export const API_BASE_URL = (
  import.meta.env.VITE_ONBOARD_API_URL || DEFAULT_BASE_URL
).replace(/\/+$/, "");

/** The service could not be reached (connection refused, DNS, timeout). */
export class NetworkError extends Error {
  readonly kind = "network" as const;
  constructor(message: string) {
    super(message);
    this.name = "NetworkError";
  }
}

/** The service answered with a non-2xx status. */
export class HttpError extends Error {
  readonly kind = "http" as const;
  readonly status: number;
  /** Human-readable detail taken from the response body when present. */
  readonly detail: string;
  constructor(status: number, detail: string) {
    super(`HTTP ${status}: ${detail}`);
    this.name = "HttpError";
    this.status = status;
    this.detail = detail;
  }
}

/** The request was cancelled by the caller (unmount, astronaut change). */
export class AbortedError extends Error {
  readonly kind = "aborted" as const;
  constructor() {
    super("aborted");
    this.name = "AbortedError";
  }
}

export type ApiError = NetworkError | HttpError;

export function toApiError(err: unknown): ApiError {
  if (err instanceof NetworkError || err instanceof HttpError) return err;
  const message = err instanceof Error ? err.message : String(err);
  return new NetworkError(message);
}

/**
 * Extract a readable message from an error body.
 * 404/409 bodies are `{ detail: string }`; 422 is FastAPI's validation body
 * where `detail` is an array of `{ loc, msg, ... }`.
 */
function extractDetail(body: unknown, fallback: string): string {
  if (typeof body !== "object" || body === null || !("detail" in body)) {
    return fallback;
  }
  const detail = (body as { detail: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (typeof item !== "object" || item === null) return String(item);
      const rec = item as { loc?: unknown; msg?: unknown };
      const loc = Array.isArray(rec.loc) ? rec.loc.join(".") : "";
      const msg = typeof rec.msg === "string" ? rec.msg : JSON.stringify(item);
      return loc ? `${loc}: ${msg}` : msg;
    });
    if (parts.length > 0) return parts.join("; ");
  }
  return fallback;
}

export type QueryValue = string | number | undefined | null;

export function buildPath(path: string, query?: Record<string, QueryValue>): string {
  if (!query) return path;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${path}?${qs}` : path;
}

export interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  signal?: AbortSignal;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal } = options;

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, REQUEST_TIMEOUT_MS);
  const onOuterAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) controller.abort();
    else signal.addEventListener("abort", onOuterAbort, { once: true });
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (err) {
    if (timedOut) throw new NetworkError("request timed out");
    if (signal?.aborted) throw new AbortedError();
    throw new NetworkError(err instanceof Error ? err.message : String(err));
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", onOuterAbort);
  }

  if (!response.ok) {
    let parsed: unknown = null;
    try {
      parsed = await response.json();
    } catch {
      parsed = null;
    }
    throw new HttpError(response.status, extractDetail(parsed, response.statusText || "error"));
  }

  try {
    return (await response.json()) as T;
  } catch {
    throw new HttpError(response.status, "response is not valid JSON");
  }
}
