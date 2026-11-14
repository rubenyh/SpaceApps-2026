import { apiRequest, buildPath } from "./client";
import type { Reading, ReadingsQuery } from "./types";

/** Newest first. */
export function listReadings(query: ReadingsQuery, signal?: AbortSignal): Promise<Reading[]> {
  return apiRequest<Reading[]>(
    buildPath("/readings", {
      astronaut_id: query.astronaut_id,
      kind: query.kind,
      since: query.since,
      until: query.until,
      limit: query.limit,
    }),
    { signal },
  );
}
