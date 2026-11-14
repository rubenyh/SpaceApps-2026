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
