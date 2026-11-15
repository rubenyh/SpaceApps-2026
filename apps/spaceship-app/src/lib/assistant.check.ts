// Self-check for lib/assistant.ts. Run: node src/lib/assistant.check.ts
import { buildRequest, explanation, mergeSymptoms } from "./assistant.ts";

function eq(actual: unknown, expected: unknown, what: string): void {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${what}: ${JSON.stringify(actual)} != ${JSON.stringify(expected)}`);
  }
}

const first = buildRequest(null, "Me duele la cabeza", "ana", "luis", []);
eq(first, { message: "Me duele la cabeza", astronaut_id: "ana", reported_by: "luis", reported_symptoms: [] }, "first");

// Follow-up keeps the original case even if the screen's selectors changed.
const followUp = buildRequest(first, "empezó de golpe", "bob", null, [
  { symptom: "sudden_severe_headache", status: "present", onset: "sudden", severity: "severe" },
]);
eq(followUp.message, "Me duele la cabeza\nempezó de golpe", "follow-up message");
eq([followUp.astronaut_id, followUp.reported_by], ["ana", "luis"], "follow-up people");
eq(followUp.reported_symptoms?.length, 1, "follow-up symptoms");

// A newer answer about the same code replaces the older one.
eq(
  mergeSymptoms([{ symptom: "fever", status: "present" }, { symptom: "cough" }], [{ symptom: "fever", status: "absent" }]),
  [{ symptom: "cough" }, { symptom: "fever", status: "absent" }],
  "merge",
);

// With a server case, only the answer is sent and the case is echoed unchanged.
const clarification = { question_id: "q", question: "¿De golpe?", astronaut_id: "ana", observations: [] };
const echoed = buildRequest({ ...first, clarification }, "sí", "bob", null, []);
eq([echoed.message, echoed.astronaut_id, echoed.clarification], ["sí", "ana", clarification], "echo case");

eq(buildRequest({ message: "x".repeat(3999) }, "abc", null, null, []).message.length, 4000, "max length");

// Action and clarifying question are rendered once: the explanation drops both.
eq(explanation({ reply: "Act.\n\nWhy it matters.", action: "Act.", clarifying_question: null }), "Why it matters.", "drop action");
eq(explanation({ reply: "¿Qué sientes?", action: null, clarifying_question: "¿Qué sientes?" }), "", "drop question");
eq(explanation({ reply: "Card text.\n\n¿Desde cuándo?", action: "Other.", clarifying_question: "¿Desde cuándo?" }), "Card text.", "keep card text");

console.log("assistant.check: ok");
