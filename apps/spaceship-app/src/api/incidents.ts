import { apiRequest, buildPath } from "./client";
import type { Incident } from "./types";

export function listIncidents(status: Incident["status"] | undefined, signal?: AbortSignal): Promise<Incident[]> {
  return apiRequest<Incident[]>(buildPath("/incidents", { status }), { signal });
}

/** 201 first acknowledgment, 200 when this person already acknowledged. Both return the incident. */
export function acknowledgeIncident(id: string, acknowledgedBy: string): Promise<Incident> {
  return apiRequest<Incident>(`/incidents/${encodeURIComponent(id)}/acknowledgments`, {
    method: "POST",
    body: { acknowledged_by: acknowledgedBy },
  });
}

/** 409 when already closed. */
export function closeIncident(id: string): Promise<Incident> {
  return apiRequest<Incident>(`/incidents/${encodeURIComponent(id)}/close`, { method: "POST" });
}
