import { apiRequest } from "./client";
import type { CaseReportStatus } from "./types";

/** Queue a draft report for ground. Idempotent: a queued/received report returns its status. */
export function sendCaseReport(id: string, sentBy: string | null, signal?: AbortSignal): Promise<CaseReportStatus> {
  return apiRequest<CaseReportStatus>(`/case-reports/${encodeURIComponent(id)}/send`, {
    method: "POST",
    body: { sent_by: sentBy },
    signal,
  });
}

export function getCaseReport(id: string, signal?: AbortSignal): Promise<CaseReportStatus> {
  return apiRequest<CaseReportStatus>(`/case-reports/${encodeURIComponent(id)}`, { signal });
}
