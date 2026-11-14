import { apiRequest } from "./client";
import type { Astronaut } from "./types";

export function listAstronauts(signal?: AbortSignal): Promise<Astronaut[]> {
  return apiRequest<Astronaut[]>("/astronauts", { signal });
}
