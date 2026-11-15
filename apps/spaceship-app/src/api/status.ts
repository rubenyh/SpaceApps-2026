import { apiRequest } from "./client";
import type { AstronautStatus } from "./types";

export function getAstronautStatus(
  astronautId: string,
  signal?: AbortSignal,
): Promise<AstronautStatus> {
  return apiRequest<AstronautStatus>(`/astronauts/${encodeURIComponent(astronautId)}/status`, {
    signal,
  });
}

/** GET /telemetry/link: onboard publisher state (docs/demo-outage.md). */
export interface EarthLink {
  enabled: boolean;
  paused: boolean;
  failures: number;
  batches_sent: number;
}

export function getEarthLink(signal?: AbortSignal): Promise<EarthLink> {
  return apiRequest<EarthLink>("/telemetry/link", { signal });
}
