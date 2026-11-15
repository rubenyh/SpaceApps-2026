import { apiRequest } from "./client";
import type { AssistantRequest, AssistantResponse } from "./types";

// Server worst case is three sequential Ollama calls: interpret (8 s) + embed (20 s)
// + answer (20 s), see onboard-api config.py. Keep this above their sum.
const ASSISTANT_TIMEOUT_MS = 60_000;

export function sendAssistantMessage(
  request: AssistantRequest,
  signal?: AbortSignal,
): Promise<AssistantResponse> {
  return apiRequest<AssistantResponse>("/assistant/messages", {
    method: "POST",
    body: request,
    signal,
    timeoutMs: ASSISTANT_TIMEOUT_MS,
  });
}
