// Self-check for lib/medicalEval.ts. Run: node src/lib/medicalEval.check.ts
import type { EvalCaseResult, EvalFinding } from "../api/types";
import {
  apiErrorText,
  approveBlockedReason,
  approveButtonLabel,
  decisionLabel,
  draftFileName,
  findingsByCase,
  percent,
  SIMULATED_APPROVAL,
  sortCases,
  statusLabel,
} from "./medicalEval.ts";

function eq(actual: unknown, expected: unknown, what: string): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${what}: ${JSON.stringify(actual)} != ${JSON.stringify(expected)}`);
  }
}

// Simulated approvals are always labelled as such.
const sim = { decision: "approved", reviewer: "team", role: "simulated", notes: "" } as const;
const doc = { decision: "approved", reviewer: "Dr. A", role: "clinician", notes: "" } as const;
eq(decisionLabel(sim), SIMULATED_APPROVAL, "simulated approval");
eq(decisionLabel(doc), "Approved by clinician", "clinician approval");
eq(statusLabel("approved", sim), SIMULATED_APPROVAL, "status uses decision role");
eq(statusLabel("approved", null), "Approved (reviewer role unknown)", "no decision record");
eq(statusLabel("pending_review", sim), "Pending review", "pending");
eq(approveButtonLabel("simulated"), SIMULATED_APPROVAL, "button label");

// Approve is refused while blocked or decided.
eq(approveBlockedReason("pending_review", false), null, "approvable");
eq(approveBlockedReason("pending_review", true)?.startsWith("Release blocked"), true, "blocked");
eq(approveBlockedReason("rejected", false) !== null, true, "decided");

eq(percent(0.856), "86 %", "percent");
eq(percent(null), "--", "missing percent");

const c = (case_id: string, passed: boolean, blocking: boolean) => ({ case_id, passed, blocking }) as EvalCaseResult;
eq(sortCases([c("a", true, false), c("b", false, false), c("c", false, true)]).map((x) => x.case_id), ["c", "b", "a"], "failed first");

const f = (id: string, case_id: string) => ({ id, case_id }) as EvalFinding;
eq([...findingsByCase([f("1", "x"), f("2", "y"), f("3", "x")]).get("x")!].map((x) => x.id), ["1", "3"], "grouped");

eq(draftFileName("dizziness.typo.001", "ab/c d"), "draft-dizziness.typo.001-ab_c_d.json", "file name");

eq(apiErrorText({ kind: "http", status: 404, detail: "unknown digest" }), "Ground does not know this version or finding (404: unknown digest).", "404");
eq(apiErrorText({ kind: "http", status: 409, detail: "release blocked" }), "Refused by ground (409: release blocked).", "409");
eq(apiErrorText({ kind: "network" }), "Ground service unreachable.", "network");

console.log("medicalEval checks passed");
