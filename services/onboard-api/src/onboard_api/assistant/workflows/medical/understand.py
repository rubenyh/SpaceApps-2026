"""Case continuity and the local interpreter (Qwen via Ollama) for non-alarm turns.

The console echoes `clarification` (pending question + observations) back; this module
turns it into observations again and merges the new turn. Qwen only reads text: it
proposes (symptom, status, evidence), validated with Pydantic and kept only when the
evidence is in the new message. The rules in triage.py decide everything else.
"""

import re
from collections import Counter
from dataclasses import asdict, replace

from pydantic import BaseModel, Field

from onboard_api.assistant.workflows.medical import prompts
from onboard_api.assistant.workflows.medical.interpret import (
    _P,
    CODE_CARD,
    VAGUE,
    _onset,
    _persistence,
    _severity,
    interpret,
    normalize,
)
from onboard_api.assistant.workflows.medical.state import Interpretation, Observation
from onboard_api.assistant.workflows.medical.triage import LABELS
from onboard_api.schemas.assistant import (
    AssistantRequest,
    CaseObservation,
    Clarification,
    SymptomCode,
    SymptomStatus,
)

# Card questions: (codes asked about, status a "sí" gives them, "or"/"and" between them).
# A bare answer ("sí", "no", "un poco") only applies to these codes.
QUESTIONS: dict[str, tuple[tuple[str, ...], str, str]] = {
    "breathing_difficulty.symptoms_and_repeat": (("shortness_of_breath",), "present", "or"),
    "palpitations.symptoms_and_repeat": (
        ("palpitations", "dizziness", "chest_pain", "shortness_of_breath", "intense_exertion"),
        "present", "or"),
    "neurologic_red_flags.headache_red_flags": (
        ("sudden_severe_headache", "speech_change", "facial_droop", "one_sided_weakness", "vision_loss"),
        "present", "or"),
    "loss_of_consciousness_or_seizure.recovered": (("unresponsive",), "absent", "and"),
    "vomiting_diarrhea_or_dehydration.fluids_urine": (
        ("unable_to_keep_fluids", "low_urine_output"), "absent", "and"),
}
_ANSWER_WORDS = {
    "si", "no", "un", "poco", "poquito", "algo", "mucho", "muy", "nada", "bastante", "claro",
    "creo", "que", "tal", "vez", "quizas", "a", "veces", "ya", "todavia", "aun", "se", "lo",
    # English short replies ("yes, a little", "no", "not sure").
    "yes", "yeah", "yep", "nope", "not", "really", "little", "bit", "lot", "very", "much",
    "slightly", "somewhat", "kind", "of", "i", "think", "maybe", "perhaps", "don", "t", "know",
    "sure", "unsure", "still", "some", "nothing", "none", "at", "all",
}
_UNSURE = {"creo", "tal", "quizas", "think", "maybe", "perhaps", "unsure"}
_NO = {"no", "nada", "nope", "not", "nothing", "none"}


class LlmObservation(BaseModel):
    symptom: SymptomCode
    status: SymptomStatus
    evidence: str = Field(min_length=1, max_length=300)


class LlmReading(BaseModel):
    # Small cap: a small model otherwise lists the whole vocabulary.
    observations: list[LlmObservation] = Field(default_factory=list, max_length=5)
    other_complaint: str | None = Field(default=None, max_length=300)


SCHEMA = LlmReading.model_json_schema()
_SYSTEM = prompts.INTERPRET_SYSTEM + "\n".join(f"{c}: {label}" for c, label in LABELS.items())


# --- case <-> observations ---


def case_for(request: AssistantRequest) -> Clarification | None:
    """The echoed case, only for the same assessed person."""
    case = request.clarification
    return case if case and case.astronaut_id == request.astronaut_id else None


def to_observation(o: CaseObservation) -> Observation:
    return Observation(**o.model_dump())


def to_case(o: Observation) -> CaseObservation:
    return CaseObservation(**asdict(o))


def subject_of(request: AssistantRequest, observations) -> str:
    other = any(o.subject == "other" for o in observations) or bool(
        request.reported_by and request.reported_by != request.astronaut_id
    )
    return "other" if other else "self"


def _words(text: str) -> str:
    return " ".join(re.findall(r"\w+", normalize(text)))


# --- rules for answers to the pending question (run before the alarm check) ---


def bare_answer(message: str, question_id: str, subject: str) -> list[Observation]:
    """'sí, un poco' / 'no' / 'no sé' to a card question, when its meaning is certain."""
    words = set(_words(message).split())
    if not words or not words <= _ANSWER_WORDS or question_id not in QUESTIONS:
        return []
    codes, yes_status, joiner = QUESTIONS[question_id]
    no_status = "absent" if yes_status == "present" else "present"
    if {"no", "se"} <= words or {"don", "know"} <= words or {"not", "sure"} <= words or words & _UNSURE:
        status = "unknown"
    elif words & _NO:
        if joiner == "and" and len(codes) > 1:
            return []  # "no" to "A and B?": which one is unknown
        status = no_status
    else:
        if joiner == "or" and len(codes) > 1:
            return []  # "sí" to "A or B?": which one is unknown
        status = yes_status
    text = " ".join(sorted(words))
    present = status == "present"
    return [
        Observation(
            symptom=code, status=status, origin="text", evidence=message.strip()[:300],
            subject=subject, severity=_severity(text) if present else None,
        )
        for code in codes
    ]


def qualify(previous: list[Observation], message: str, question_id: str) -> list[Observation]:
    """'Empezó de repente y es muy intenso' after 'me duele la cabeza' describes the
    open symptoms of the asked card (onset, severity, persistence), as a follow-up
    sentence does inside one message."""
    text = _words(message)
    onset, severity, persistence = _onset(text), _severity(text), _persistence(text)
    card = question_id.split(".")[0]
    if not (onset or severity or persistence):
        return []
    out = [
        replace(o, onset=o.onset or onset, severity=o.severity or severity,
                persistence=o.persistence or persistence)
        for o in previous
        if o.status == "present" and o.temporality == "current" and CODE_CARD.get(o.symptom) == card
    ]
    out += [replace(o, symptom="sudden_severe_headache") for o in out
            if o.symptom == "headache" and o.onset == "sudden" and o.severity == "severe"]
    return out


def answer_turn(
    base: Interpretation,
    message: str,
    case: Clarification,
    previous: list[Observation],
    subject: str,
) -> Interpretation:
    """Rules-only reading of an answer that names no symptom by itself."""
    if base.observations:
        return base
    found = bare_answer(message, case.question_id, subject) or qualify(
        previous, message, case.question_id
    )
    return replace(base, observations=tuple(found)) if found else base


def _finish(
    base: Interpretation, observations: dict[str, Observation], uncovered: str | None
) -> Interpretation:
    final = tuple(observations.values())
    reported = any(o.status == "present" and o.temporality in ("current", "resolved") for o in final)
    topic = base.topic_hint or next(
        (CODE_CARD[o.symptom] for o in final if o.status == "present"), None
    )
    return replace(
        base,
        observations=final,
        request_kind="report" if reported else base.request_kind,
        medical_signal=base.medical_signal or bool(final),
        topic_hint=topic,
        uncovered=None if reported else uncovered,
    )


def merge_case(base: Interpretation, previous: list[Observation]) -> Interpretation:
    """New-turn observations (rules, structured) replace the case's, except that an
    'unknown' never overwrites a known value."""
    best = {o.symptom: o for o in previous}
    for o in base.observations:
        old = best.get(o.symptom)
        if old is None or o.status != "unknown" or old.status == "unknown":
            best[o.symptom] = o
    return _finish(base, best, base.uncovered)


def add_llm(base: Interpretation, extra: list[Observation], uncovered: str | None) -> Interpretation:
    """Interpreter observations only fill codes that are missing or unknown: a
    confirmed datum changes only through explicit text (rules) or structured input."""
    best = {o.symptom: o for o in base.observations}
    for o in extra:
        old = best.get(o.symptom)
        if old is None or (old.status == "unknown" and o.status != "unknown"):
            best[o.symptom] = o
    return _finish(base, best, base.uncovered or uncovered)


# --- interpreter ---


def _stems(text: str) -> set[str]:
    return {w[:5] for w in _words(text).split() if len(w) >= 4}


# Words the rules and the label use for each code ("respi", "cuest", "estom", ...).
# Stems shared by 3+ codes ("duele", "dolor", "mucho") tell nothing apart and are dropped.
_CODE_STEMS: dict[str, set[str]] = {}
for _code, _rx, _ in _P:
    _CODE_STEMS.setdefault(_code, _stems(LABELS[_code])).update(
        w[:5] for w in re.findall(r"[a-z]{4,}", _rx)
    )
_SHARED = Counter(w for stems in _CODE_STEMS.values() for w in stems)
_GENERIC = {w for w, n in _SHARED.items() if n >= 3} | {"poco", "para", "puede", "puedo", "podia", "basta"}
_CODE_STEMS = {code: stems - _GENERIC for code, stems in _CODE_STEMS.items()}


def read_turn(
    llm, message: str, question: str | None, known: tuple[Observation, ...]
) -> LlmReading | None:
    """Qwen's reading of the new message, or None on any failure or invalid output."""
    known_lines = [f"{o.symptom} ({LABELS[o.symptom]}): {o.status}" for o in known]
    user = prompts.interpret_user_prompt(message, question, known_lines)
    try:
        return LlmReading.model_validate_json(llm.chat_json(_SYSTEM, user, SCHEMA))
    except Exception:  # invalid JSON/schema, Ollama down or slow, client without chat_json
        return None


# "no tengo síntomas" / "I have no symptoms" (normalized words): the interpreter may not add a
# present symptom; only explicit rule text can (urinary.simulated.001: a reddish sample).
_NO_SYMPTOMS = re.compile(
    r"\b(no (tengo|siento|presento|hay) (ningun |otros? )?sintomas?|sin sintomas|asintomatic\w*|asymptomatic"
    r"|no symptoms|(don t|do not) have (any )?symptoms)\b"
)


def accept(
    reading: LlmReading, request: AssistantRequest, question_id: str | None, subject: str
) -> tuple[list[Observation], str | None]:
    """Keep only observations backed by the new message and coherent with the rules."""
    message = f" {_words(request.message)} "
    asked = QUESTIONS[question_id][0] if question_id in QUESTIONS else ()
    denied = bool(_NO_SYMPTOMS.search(message))
    kept: list[Observation] = []
    for o in reading.observations:
        if denied and o.status == "present":
            continue
        evidence = _words(o.evidence)
        if not evidence or f" {evidence} " not in message:
            continue  # not the user's words
        bare = set(evidence.split()) <= _ANSWER_WORDS
        if bare and o.symptom not in asked:
            continue  # a bare "sí"/"no" only answers the pending question
        if not bare:
            ruled = {x.symptom for x in interpret(AssistantRequest(message=o.evidence)).observations}
            if ruled and o.symptom not in ruled:
                continue  # the rules read these words as another symptom
            if not ruled and (VAGUE.search(evidence) or not _stems(evidence) & _CODE_STEMS[o.symptom]):
                # ponytail: word-stem overlap with the code's rule words, not a semantic check;
                # it stops a small model mapping "hola" or "malestar físico" to a symptom.
                continue
        present = o.status == "present"
        kept.append(Observation(
            symptom=o.symptom,
            status=o.status,
            origin="llm",
            evidence=o.evidence.strip(),
            subject=subject,
            onset=_onset(evidence) if present else None,
            severity=_severity(evidence) if present else None,
        ))
    complaint = _words(reading.other_complaint or "")
    backed = complaint and f" {complaint} " in message and not VAGUE.search(complaint)
    uncovered = reading.other_complaint.strip() if backed else None
    return kept, uncovered
