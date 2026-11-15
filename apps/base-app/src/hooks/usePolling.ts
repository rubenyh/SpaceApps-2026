import { useCallback, useEffect, useRef, useState } from "react";
import { AbortedError, toApiError, type ApiError } from "../api/client";

export interface PollState<T> {
  /** Last successful result. Kept when a later poll fails (last known data). */
  data: T | null;
  /** Error of the most recent attempt, null once a later attempt succeeds. */
  error: ApiError | null;
  /** Date.now() of the last success. */
  updatedAt: number | null;
  /** Run now (ignored while a request is in flight). */
  refresh: () => void;
}

interface Inner<T> {
  data: T | null;
  error: ApiError | null;
  updatedAt: number | null;
}

const EMPTY: Inner<never> = { data: null, error: null, updatedAt: null };

/**
 * Poll `fetcher` every `intervalMs` while mounted. Changing `key` resets the data and
 * restarts; `null` disables. Requests never overlap and are aborted on unmount.
 */
export function usePolling<T>(
  key: string | null,
  fetcher: (signal: AbortSignal) => Promise<T>,
  intervalMs: number,
): PollState<T> {
  const fetcherRef = useRef(fetcher);
  useEffect(() => {
    fetcherRef.current = fetcher;
  });

  const [state, setState] = useState<Inner<T>>(EMPTY);
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
      try {
        const data = await fetcherRef.current(controller.signal);
        if (!cancelled) setState({ data, error: null, updatedAt: Date.now() });
      } catch (err) {
        if (cancelled || err instanceof AbortedError) return;
        const apiError = toApiError(err);
        setState((s) => ({ ...s, error: apiError }));
      } finally {
        inFlight = false;
        if (!cancelled) timer = setTimeout(run, intervalMs);
      }
    };

    refreshRef.current = () => void run();
    void run();

    return () => {
      cancelled = true;
      clearTimeout(timer);
      controller.abort();
      refreshRef.current = () => {};
    };
  }, [key, intervalMs]);

  const refresh = useCallback(() => refreshRef.current(), []);
  return { ...state, refresh };
}
