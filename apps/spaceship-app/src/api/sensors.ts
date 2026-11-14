import { apiRequest } from "./client";
import type { SensorConfig } from "./types";

export function listSensors(signal?: AbortSignal): Promise<SensorConfig[]> {
  return apiRequest<SensorConfig[]>("/sensors", { signal });
}
