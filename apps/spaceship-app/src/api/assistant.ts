import { apiRequest } from "./client";
import type { AssistantRequest, AssistantResponse } from "./types";

export function sendAssistantMessage(
  request: AssistantRequest,
  signal?: AbortSignal,
): Promise<AssistantResponse> {
  return apiRequest<AssistantResponse>("/assistant/messages", {
    method: "POST",
    body: request,
    signal,
  });
}
