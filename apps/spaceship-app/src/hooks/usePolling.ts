import { useCallback, useEffect, useRef, useState } from "react";
import { AbortedError, NetworkError, toApiError, type ApiError } from "../api/client";
import { useConnectionReporter } from "./connection";

export interface PollState<T> {
  /** Last successful result. Kept when a later poll fails (last known data). */
  data: T | null;
  /** Error of the most recent attempt, null once a later attempt succeeds. */
  error: ApiError | null;
  /** A request is in flight. */
  loading: boolean;
  /** Date.now() of the last success. */
  updatedAt: number | null;
  /** Run now (ignored while a request is in flight). */
  refresh: () => void;
}

interface InnerState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  updatedAt: number | null;
}

const EMPTY: InnerState<never> = { data: null, error: null, loading: false, updatedAt: null };

/**
 * Poll `fetcher` every `intervalMs` while mounted.
 *
 * - `key` identifies what is being polled; changing it resets the data and
 *   restarts polling. `null` disables polling.
 * - Requests never overlap: the next one is scheduled after the previous ends.
 * - Polling stops and the in-flight request is aborted on unmount / key change.
 */
export function usePolling<T>(
  key: string | null,
  fetcher: (signal: AbortSignal) => Promise<T>,
  intervalMs: number,
): PollState<T> {
  const report = useConnectionReporter();
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const [state, setState] = useState<InnerState<T>>(EMPTY);
  const refreshRef = useRef<() => void>(() => {});

  useEffect(() => {
    setState(EMPTY);
    if (key === null) return;

    let cancelled = false;
    let inFlight = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const controller = new AbortController();

    const run = async () => {
      if (cancelled || inFlight) return;
      inFlight = true;
      clearTimeout(timer);
      setState((s) => ({ ...s, loading: true }));
      try {
        const data = await fetcherRef.current(controller.signal);
        if (cancelled) return;
        setState({ data, error: null, loading: false, updatedAt: Date.now() });
        report(true);
      } catch (err) {
        if (cancelled || err instanceof AbortedError) return;
        const apiError = toApiError(err);
        setState((s) => ({ ...s, error: apiError, loading: false }));
        report(!(apiError instanceof NetworkError));
      } finally {
        inFlight = false;
        if (!cancelled) timer = setTimeout(run, intervalMs);
      }
    };

    refreshRef.current = () => {
      void run();
    };
    void run();

    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller.abort();
      refreshRef.current = () => {};
    };
  }, [key, intervalMs, report]);

  const refresh = useCallback(() => refreshRef.current(), []);

  return { ...state, refresh };
}
