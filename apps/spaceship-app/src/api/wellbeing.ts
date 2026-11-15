// Wellbeing endpoints (docs/wellbeing-contract.md). Crew view must only call getCrewWellbeing.
import { apiRequest, buildPath } from "./client";
import type {
  Checkin,
  CheckinForm,
  CheckinUpsert,
  CrewWellbeing,
  GroundPackage,
  GroundPackageContent,
  GroundPackageCreate,
  WellbeingAssessment,
  WellbeingParameters,
  WellbeingTimeline,
} from "./types";

const astronaut = (id: string) => `/astronauts/${encodeURIComponent(id)}/wellbeing`;
const pkg = (id: string) => `/wellbeing/ground-packages/${encodeURIComponent(id)}`;

export const getCrewWellbeing = (signal?: AbortSignal) =>
  apiRequest<CrewWellbeing>("/wellbeing/crew", { signal });

export const getWellbeing = (astronautId: string, signal?: AbortSignal) =>
  apiRequest<WellbeingAssessment>(astronaut(astronautId), { signal });

export const getWellbeingTimeline = (astronautId: string, days: number, signal?: AbortSignal) =>
  apiRequest<WellbeingTimeline>(buildPath(`${astronaut(astronautId)}/timeline`, { days }), { signal });

export const getWellbeingParameters = (signal?: AbortSignal) =>
  apiRequest<WellbeingParameters>("/wellbeing/parameters", { signal });

export const getCheckinForm = (signal?: AbortSignal) =>
  apiRequest<CheckinForm>("/wellbeing/checkin-form", { signal });

export const listCheckins = (
  astronautId: string,
  range: { since?: string; until?: string },
  signal?: AbortSignal,
) => apiRequest<Checkin[]>(buildPath(`${astronaut(astronautId)}/checkins`, range), { signal });

export const putCheckin = (astronautId: string, day: string, body: CheckinUpsert) =>
  apiRequest<Checkin>(`${astronaut(astronautId)}/checkins/${encodeURIComponent(day)}`, {
    method: "PUT",
    body,
  });

export const createGroundPackage = (body: GroundPackageCreate) =>
  apiRequest<GroundPackage>("/wellbeing/ground-packages", { method: "POST", body });

export const listGroundPackages = (astronautId: string, signal?: AbortSignal) =>
  apiRequest<GroundPackage[]>(buildPath("/wellbeing/ground-packages", { astronaut_id: astronautId }), {
    signal,
  });

export const getGroundPackageContent = (id: string, signal?: AbortSignal) =>
  apiRequest<GroundPackageContent>(`${pkg(id)}/content`, { signal });

export const withdrawGroundPackage = (id: string) =>
  apiRequest<GroundPackage>(`${pkg(id)}/withdraw`, { method: "POST" });
