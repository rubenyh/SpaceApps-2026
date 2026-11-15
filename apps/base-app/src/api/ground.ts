import { apiGet, apiPost, buildPath } from "./client";
import type {
  Alert,
  CandidateDetail,
  CandidateListItem,
  CrewMember,
  DecisionBody,
  EvalFinding,
  FindingBody,
  GroundIncident,
  GroundReading,
  Link,
  SensorKind,
} from "./types";

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

// --- Medical evaluation (contracts/medical-eval/README.md section 4) ---------

const digestPath = (digest: string) => `/medical-eval/candidates/${encodeURIComponent(digest)}`;

export const getCandidates = (signal?: AbortSignal) =>
  apiGet<CandidateListItem[]>("/medical-eval/candidates", signal);

export const getCandidate = (digest: string, signal?: AbortSignal) =>
  apiGet<CandidateDetail>(digestPath(digest), signal);

/** 409 when the digest is unknown or already decided, or approving while release_blocked. */
export const postDecision = (digest: string, body: DecisionBody) =>
  apiPost<unknown>(`${digestPath(digest)}/decisions`, body);

export const postFinding = (digest: string, body: FindingBody) =>
  apiPost<EvalFinding>(`${digestPath(digest)}/findings`, body);

/** A section 1 case built from the finding, review.status "draft". */
export const getDraftCase = (findingId: string) =>
  apiGet<unknown>(`/medical-eval/findings/${encodeURIComponent(findingId)}/draft-case`);
