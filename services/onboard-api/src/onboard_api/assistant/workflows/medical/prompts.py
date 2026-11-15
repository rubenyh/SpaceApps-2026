"""Prompt and fixed Spanish texts of the medical workflow."""

from onboard_api.assistant.integrations import GuideChunk
from onboard_api.services.assistant import DISCLAIMER

__all__ = ["DISCLAIMER"]

# No clinician is on board and the ground link may be down: nothing here refers to an
# onboard medical officer, and nothing claims that anyone was notified.
NOTIFY_EMERGENCY = ("tripulación", "control de misión (si hay enlace)")
NOTIFY_GROUND = ("control de misión (si hay enlace)",)
EMERGENCY_PROCEDURE = "Procedimiento de emergencia médica de la misión"
MEDICAL_PROCEDURE = "Procedimientos médicos de la misión"

ALARM_NOTICE = (
    "Alarma inmediata: la decisión usa solo fichas locales, sin esperar a las guías ni al"
    " modelo local. Las lecturas solo se añaden como evidencia y nunca rebajan la alarma."
)
OUT_OF_COVERAGE_ACTION = (
    "Este síntoma no está cubierto por las fichas: busca la sección que corresponda en los"
    " procedimientos médicos de la misión, anota lo que observas y copia el informe para"
    " control de misión cuando haya enlace. Si aparece una señal de alarma (falta de aire"
    " intensa, dolor en el pecho, desmayo, sangrado que no para), trátalo como emergencia."
)
OUT_OF_COVERAGE_REPLY = (
    "Las fichas locales del asistente no cubren este caso, así que no puedo darte pasos"
    " específicos con fuente."
)
OUT_OF_COVERAGE_MISSING = "No hay ficha local para este síntoma: no hay pasos con fuente."
EDUCATIONAL_ABSTAIN = (
    "No encontré una fuente local que respalde una respuesta a esta consulta, así que"
    " no voy a responder sin respaldo. Si tienes síntomas, descríbelos."
)
NOTICE_READINGS_FAILED = "Repositorio de lecturas no disponible: no se consultaron lecturas."
NOTICE_GUIDES_FAILED = "No se pudieron consultar las guías locales (ChromaDB)."
NOTICE_EMBEDDING_FAILED = (
    "El modelo de embeddings (Ollama) no respondió: no se consultaron las guías locales."
)
NOTICE_NO_GUIDES = "No se encontró una guía local pertinente."
NOTICE_LLM_FAILED = (
    "El modelo local (Ollama) no respondió: se muestra el texto conservado de la ficha"
    " o de la guía."
)
NOTICE_DRAFT_REJECTED = (
    "La explicación generada no pasó las comprobaciones (citas, cifras o afirmaciones no"
    " permitidas) y se descartó: se muestra el texto conservado de la ficha o de la guía."
)
# About the assistant's own dependencies, not the case: kept out of the report.
ASSISTANT_NOTICES = frozenset({
    ALARM_NOTICE, NOTICE_GUIDES_FAILED, NOTICE_EMBEDDING_FAILED, NOTICE_NO_GUIDES,
    NOTICE_LLM_FAILED, NOTICE_DRAFT_REJECTED,
})
EXCERPT_CHARS = 600

SYSTEM = """Eres el asistente médico informativo de una nave. Escribe SIEMPRE en español.
Redacta una explicación breve (máximo 80 palabras, 2 a 4 frases) para la tripulación.
Reglas obligatorias:
1. Usa solo el texto de la ficha, los hallazgos, los avisos de datos y los fragmentos numerados. Si algo no está escrito ahí, no lo digas.
   No añadas ejemplos, situaciones, objetos, vehículos ni comparaciones que no aparezcan en esos textos.
2. No añadas causas, diagnósticos, tratamientos, dosis ni probabilidades.
3. No escribas ningún número que no aparezca en el contexto.
4. Cita los fragmentos como [n], solo con los números dados. Nunca inventes una cita.
5. No repitas la acción indicada: ya se muestra antes de tu texto. No la contradigas.
6. Si falta un dato o una lectura es vieja o dudosa, dilo.
7. No digas que se envió, avisó o informó a nadie: nada se transmite.
8. No des un diagnóstico. No hay médico a bordo: no menciones médicos ni personal clínico.
9. Un dato "desconocido" sigue desconocido: no digas que un síntoma falta o se descarta salvo que el informe diga "ausente"."""


def number_chunks(chunks: list[GuideChunk]) -> str:
    return "\n\n".join(
        f"[{i}] {c.title} — {c.section}\n{c.text}" for i, c in enumerate(chunks, 1)
    ) or "(ninguno)"


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
        return "\n".join(f"- {x}" for x in items) or "- (ninguno)"

    return (
        f"Tema:\n{topic or '(consulta general de salud)'}\n\n"
        f"Acción indicada por la ficha:\n{action or '(ninguna; consulta informativa)'}\n\n"
        f"Resumen de la ficha:\n{card_summary or '(sin ficha)'}\n\n"
        f"Hallazgos:\n{bullets(findings)}\n\n"
        f"Avisos de datos:\n{bullets(notices)}\n\n"
        f"Informe del caso:\n{report or '(sin informe)'}\n\n"
        f"Fragmentos de guías:\n{number_chunks(chunks)}\n\n"
        "Escribe la explicación en español siguiendo las reglas."
    )


def guide_excerpt(chunk: GuideChunk) -> str:
    text = chunk.text if len(chunk.text) <= EXCERPT_CHARS else chunk.text[:EXCERPT_CHARS] + "…"
    return f"Según la guía local [1] ({chunk.title}, {chunk.section}): {text}"


SOS_ACTION = (
    "SOS: sigue ahora el procedimiento de emergencia de la misión y pide ayuda con la alarma"
    " de la nave (tripulación, control de misión si hay enlace)."
)
SOS_FINDING = "Petición de ayuda urgente (SOS) escrita en la consola."

INTERPRET_SYSTEM = """Lees el mensaje de un tripulante y extraes síntomas. Responde solo con JSON.
- observations: cada síntoma o evento que el MENSAJE NUEVO afirma, niega o deja en duda.
  symptom: un código de la lista. status: "present" (lo tiene), "absent" (lo niega) o "unknown" (no lo sabe).
  evidence: las palabras exactas del MENSAJE NUEVO que lo respaldan, copiadas sin cambios.
- Si el mensaje solo contesta la PREGUNTA PENDIENTE ("sí", "no", "un poco"), aplica esa respuesta
  a los síntomas por los que pregunta y usa esas palabras como evidence.
- No inventes síntomas. Si el mensaje no nombra ninguno, observations es [].
- other_complaint: un síntoma concreto que no está en la lista, copiado del mensaje; si no hay, null.
- Como máximo 3 observaciones. Nunca copies textos de la lista de códigos como evidence.
Ejemplos:
PREGUNTA PENDIENTE: ¿Tiene ahora falta de aire? MENSAJE NUEVO: sí, me cuesta un poco
{"observations": [{"symptom": "shortness_of_breath", "status": "present", "evidence": "sí, me cuesta un poco"}], "other_complaint": null}
PREGUNTA PENDIENTE: (ninguna) MENSAJE NUEVO: me duele el oído
{"observations": [], "other_complaint": "me duele el oído"}
PREGUNTA PENDIENTE: (ninguna) MENSAJE NUEVO: malestar físico
{"observations": [], "other_complaint": null}
Códigos:
"""


def interpret_user_prompt(message: str, question: str | None, known: list[str]) -> str:
    known_text = "\n".join(f"- {k}" for k in known) or "- (ninguno)"
    return (
        f"PREGUNTA PENDIENTE:\n{question or '(ninguna)'}\n\n"
        f"DATOS YA REPORTADOS:\n{known_text}\n\n"
        f"MENSAJE NUEVO:\n{message}"
    )
