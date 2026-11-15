import { apiGet, buildPath } from "./client";
import type { Alert, CrewMember, GroundIncident, GroundReading, Link, SensorKind } from "./types";

export const getLink = (signal?: AbortSignal) => apiGet<Link>("/link", signal);

export const getCrew = (signal?: AbortSignal) => apiGet<CrewMember[]>("/crew", signal);

/** Newest first. Max limit 1000. 404 for an unknown astronaut. */
export function getReadings(
  astronautId: string,
  query: { kind?: SensorKind; since?: string; limit?: number },
  signal?: AbortSignal,
): Promise<GroundReading[]> {
  return apiGet<GroundReading[]>(
    buildPath(`/astronauts/${encodeURIComponent(astronautId)}/readings`, query),
    signal,
  );
}

/** Newest first. Max limit 500. */
export const getAlerts = (limit: number, signal?: AbortSignal) =>
  apiGet<Alert[]>(buildPath("/alerts", { limit }), signal);

/** Newest began_at first. */
export const getIncidents = (signal?: AbortSignal) => apiGet<GroundIncident[]>("/incidents", signal);

/** 404 for an unknown incident. */
export const getIncident = (id: string, signal?: AbortSignal) =>
  apiGet<GroundIncident>(`/incidents/${encodeURIComponent(id)}`, signal);
