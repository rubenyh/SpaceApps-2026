import type {
  CandidateStatus,
  DecisionBody,
  EvalCaseResult,
  EvalFinding,
  FindingKind,
  ReviewRole,
} from "../api/types";

export const SIMULATED_APPROVAL = "Simulated approval (no clinician)";

export const FINDING_KINDS: { key: FindingKind; label: string }[] = [
  { key: "possible_cause", label: "Possible cause" },
  { key: "warning_sign", label: "Warning sign" },
  { key: "question", label: "Question" },
  { key: "action", label: "Action" },
];

export const findingKindLabel = (kind: string) => FINDING_KINDS.find((k) => k.key === kind)?.label ?? kind;

/** First 12 hex characters, enough to tell versions apart on screen. */
export const shortDigest = (digest: string) => digest.slice(0, 12);

/** "Approved by clinician", "Rejected by simulated reviewer", or the simulated-approval label. */
export function decisionLabel(d: Pick<DecisionBody, "decision" | "role">): string {
  if (d.role === "simulated") return d.decision === "approved" ? SIMULATED_APPROVAL : "Rejected (simulated review, no clinician)";
  return d.decision === "approved" ? "Approved by clinician" : "Rejected by clinician";
}

/** Candidate status; a simulated approval is never shown as a plain "Approved". */
export function statusLabel(status: CandidateStatus, decision: Pick<DecisionBody, "decision" | "role"> | null | undefined): string {
  if (status === "pending_review") return "Pending review";
  if (decision) return decisionLabel(decision);
  return status === "approved" ? "Approved (reviewer role unknown)" : "Rejected";
}

/** Why Approve is disabled, or null when it can be pressed. */
export function approveBlockedReason(status: CandidateStatus, releaseBlocked: boolean): string | null {
  if (status !== "pending_review") return "This version already has a decision.";
  if (releaseBlocked) return "Release blocked: blocking test failures (missed alarm or unsafe action). Only rejection is possible.";
  return null;
}

export const approveButtonLabel = (role: ReviewRole) => (role === "simulated" ? SIMULATED_APPROVAL : "Approve this version");

/** "86 %"; "--" for a missing value. */
export const percent = (rate: number | null | undefined) =>
  typeof rate === "number" && Number.isFinite(rate) ? `${Math.round(rate * 100)} %` : "--";

/** Failed cases first (blocking before non-blocking), then by case id. */
export function sortCases(cases: EvalCaseResult[]): EvalCaseResult[] {
  const rank = (c: EvalCaseResult) => (c.passed ? 2 : c.blocking ? 0 : 1);
  return [...cases].sort((a, b) => rank(a) - rank(b) || a.case_id.localeCompare(b.case_id));
}

export function findingsByCase(findings: EvalFinding[]): Map<string, EvalFinding[]> {
  const map = new Map<string, EvalFinding[]>();
  for (const f of findings) map.set(f.case_id, [...(map.get(f.case_id) ?? []), f]);
  return map;
}

/** File name for a downloaded draft case, safe on Windows. */
export const safeFileName = (name: string) => name.replace(/[^A-Za-z0-9._-]+/g, "_");

export const draftFileName = (caseId: string, findingId: string) => safeFileName(`draft-${caseId}-${findingId}.json`);

/** Error shape of api/client.ts (kept structural so this file runs under plain node). */
type ApiErrorLike = { kind: "network" } | { kind: "http"; status: number; detail: string };

/** 404: ground does not know the version; 409: ground refused the decision. */
export function apiErrorText(e: ApiErrorLike): string {
  if (e.kind === "network") return "Ground service unreachable.";
  if (e.status === 404) return `Ground does not know this version or finding (404: ${e.detail}).`;
  if (e.status === 409) return `Refused by ground (409: ${e.detail}).`;
  return `Ground service error (HTTP ${e.status}: ${e.detail}).`;
}
