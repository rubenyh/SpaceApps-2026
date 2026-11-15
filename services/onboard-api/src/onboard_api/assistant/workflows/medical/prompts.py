"""Prompt and fixed English texts of the medical workflow."""

from onboard_api.assistant.integrations import GuideChunk
from onboard_api.services.assistant import DISCLAIMER

__all__ = ["DISCLAIMER"]

# No clinician is on board and the ground link may be down: nothing here refers to an
# onboard medical officer, and nothing claims that anyone was notified.
NOTIFY_EMERGENCY = ("crew", "mission control (if the link is up)")
NOTIFY_GROUND = ("mission control (if the link is up)",)
EMERGENCY_PROCEDURE = "Mission medical emergency procedure"
MEDICAL_PROCEDURE = "Mission medical procedures"

ALARM_NOTICE = (
    "Immediate alarm: the decision uses only local cards, without waiting for the guides or"
    " the local model. Readings are only added as evidence and never lower the alarm."
)
OUT_OF_COVERAGE_ACTION = (
    "This symptom is not covered by the cards: look up the matching section in the mission"
    " medical procedures, write down what you observe, and copy the report for mission"
    " control when the link is up. If a red flag appears (severe shortness of breath, chest"
    " pain, fainting, bleeding that does not stop), treat it as an emergency."
)
OUT_OF_COVERAGE_REPLY = (
    "The assistant's local cards do not cover this case, so I cannot give you specific"
    " sourced steps."
)
OUT_OF_COVERAGE_MISSING = "No local card for this symptom: no sourced steps."
EDUCATIONAL_ABSTAIN = (
    "I did not find a local source that supports an answer to this question, so I will not"
    " answer without one. If you have symptoms, describe them."
)
NOTICE_READINGS_FAILED = "Readings repository unavailable: no readings were checked."
NOTICE_GUIDES_FAILED = "The local guides (ChromaDB) could not be searched."
NOTICE_EMBEDDING_FAILED = (
    "The embedding model (Ollama) did not respond: the local guides were not searched."
)
NOTICE_NO_GUIDES = "No relevant local guide in English was found."
NOTICE_LLM_FAILED = (
    "The local model (Ollama) did not respond: showing the preserved card or guide text."
)
NOTICE_DRAFT_REJECTED = (
    "The generated explanation failed the checks (citations, numbers or disallowed claims)"
    " and was discarded: showing the preserved card or guide text."
)
# About the assistant's own dependencies, not the case: kept out of the report.
ASSISTANT_NOTICES = frozenset({
    ALARM_NOTICE, NOTICE_GUIDES_FAILED, NOTICE_EMBEDDING_FAILED, NOTICE_NO_GUIDES,
    NOTICE_LLM_FAILED, NOTICE_DRAFT_REJECTED,
})
EXCERPT_CHARS = 600

SYSTEM = """You are the informational medical assistant of a spacecraft. ALWAYS write in English.
Write a short explanation (at most 80 words, 2 to 4 sentences) for the crew.
Mandatory rules:
1. Use only the card text, the findings, the data notices and the numbered excerpts. If something is not written there, do not say it.
   Do not add examples, situations, objects, vehicles or comparisons that do not appear in those texts.
2. Do not add causes, diagnoses, treatments, doses or probabilities.
3. Do not write any number that does not appear in the context.
4. Cite the excerpts as [n], only with the numbers given. Never invent a citation.
5. Do not repeat the indicated action: it is already shown before your text. Do not contradict it.
6. If a datum is missing or a reading is old or doubtful, say so.
7. Do not say that anything was sent, reported or that anyone was notified: nothing is transmitted.
8. Do not give a diagnosis. There is no doctor on board: do not mention doctors or clinical staff.
9. An "unknown" datum stays unknown: do not say a symptom is missing or ruled out unless the report says "absent"."""


def number_chunks(chunks: list[GuideChunk]) -> str:
    return "\n\n".join(
        f"[{i}] {c.title} — {c.section}\n{c.text}" for i, c in enumerate(chunks, 1)
    ) or "(none)"


def build_user_prompt(
    topic: str | None,
    action: str | None,
    card_summary: str | None,
    findings: list[str],
    notices: list[str],
    chunks: list[GuideChunk],
    report: str | None = None,
) -> str:
    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {x}" for x in items) or "- (none)"

    return (
        f"Topic:\n{topic or '(general health question)'}\n\n"
        f"Action indicated by the card:\n{action or '(none; informational question)'}\n\n"
        f"Card summary:\n{card_summary or '(no card)'}\n\n"
        f"Findings:\n{bullets(findings)}\n\n"
        f"Data notices:\n{bullets(notices)}\n\n"
        f"Case report:\n{report or '(no report)'}\n\n"
        f"Guide excerpts:\n{number_chunks(chunks)}\n\n"
        "Write the explanation in English following the rules."
    )


def guide_excerpt(chunk: GuideChunk) -> str:
    text = chunk.text if len(chunk.text) <= EXCERPT_CHARS else chunk.text[:EXCERPT_CHARS] + "…"
    return f"According to the local guide [1] ({chunk.title}, {chunk.section}): {text}"


SOS_ACTION = (
    "SOS: follow the mission emergency procedure now and call for help with the ship"
    " alarm (crew, mission control if the link is up)."
)
SOS_FINDING = "Urgent call for help (SOS) typed in the console."

INTERPRET_SYSTEM = """You read a crew member's message and extract symptoms. Reply with JSON only.
The message may be in English or Spanish.
- observations: each symptom or event that the NEW MESSAGE affirms, denies or leaves in doubt.
  symptom: one code from the list. status: "present" (has it), "absent" (denies it) or "unknown" (does not know).
  evidence: the exact words of the NEW MESSAGE that support it, copied unchanged (same language).
- If the message only answers the PENDING QUESTION ("yes", "no", "a little", "sí", "un poco"), apply that
  answer to the symptoms the question asks about and use those words as evidence.
- Do not invent symptoms. If the message names none, observations is [].
- other_complaint: a concrete symptom that is not in the list, copied from the message; null if none.
- At most 3 observations. Never copy text from the code list as evidence.
Examples:
PENDING QUESTION: Are you short of breath now? NEW MESSAGE: yes, a little
{"observations": [{"symptom": "shortness_of_breath", "status": "present", "evidence": "yes, a little"}], "other_complaint": null}
PENDING QUESTION: Are you short of breath now? NEW MESSAGE: sí, me cuesta un poco
{"observations": [{"symptom": "shortness_of_breath", "status": "present", "evidence": "sí, me cuesta un poco"}], "other_complaint": null}
PENDING QUESTION: (none) NEW MESSAGE: my ear hurts
{"observations": [], "other_complaint": "my ear hurts"}
PENDING QUESTION: (none) NEW MESSAGE: malestar físico
{"observations": [], "other_complaint": null}
Codes:
"""


def interpret_user_prompt(message: str, question: str | None, known: list[str]) -> str:
    known_text = "\n".join(f"- {k}" for k in known) or "- (none)"
    return (
        f"PENDING QUESTION:\n{question or '(none)'}\n\n"
        f"ALREADY REPORTED:\n{known_text}\n\n"
        f"NEW MESSAGE:\n{message}"
    )
