"""Prompt and fixed Spanish texts of the medical workflow."""

from onboard_api.assistant.integrations import GuideChunk
from onboard_api.services.assistant import DISCLAIMER

__all__ = ["DISCLAIMER"]

MEDICAL_OFFICER = "responsable médico a bordo"

ALARM_NOTICE = (
    "Alarma inmediata: la respuesta usa solo fichas locales; no se esperó a consultar"
    " lecturas, guías ni el modelo local."
)
OUT_OF_COVERAGE_ACTION = (
    "Pide una valoración al responsable médico a bordo y describe lo que observas."
)
OUT_OF_COVERAGE_REPLY = (
    "Este caso no está cubierto por las fichas locales del asistente, así que no puedo"
    " orientarlo. Si aparece una señal de alarma, sigue el procedimiento de emergencia"
    " de la nave."
)
EDUCATIONAL_ABSTAIN = (
    "No encontré una fuente local que respalde una respuesta a esta consulta, así que"
    " no voy a responder sin respaldo. Si tienes síntomas, descríbelos; si tienes dudas,"
    " consulta al responsable médico a bordo."
)
NOTICE_READINGS_FAILED = "Repositorio de lecturas no disponible: no se consultaron lecturas."
NOTICE_GUIDES_FAILED = "No se pudieron consultar las guías locales (ChromaDB)."
NOTICE_NO_GUIDES = "No se encontró una guía local pertinente."
NOTICE_LLM_FAILED = (
    "El modelo local (Ollama) no respondió: se muestra el texto conservado de la ficha"
    " o de la guía."
)
NOTICE_DRAFT_REJECTED = (
    "La explicación generada citaba fuentes o datos no proporcionados y se descartó:"
    " se muestra el texto conservado de la ficha o de la guía."
)
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
7. No digas que se envió ningún aviso.
8. No des un diagnóstico; el diagnóstico y el tratamiento corresponden al responsable médico."""


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
) -> str:
    def bullets(items: list[str]) -> str:
        return "\n".join(f"- {x}" for x in items) or "- (ninguno)"

    return (
        f"Tema:\n{topic or '(consulta general de salud)'}\n\n"
        f"Acción indicada por la ficha:\n{action or '(ninguna; consulta informativa)'}\n\n"
        f"Resumen de la ficha:\n{card_summary or '(sin ficha)'}\n\n"
        f"Hallazgos:\n{bullets(findings)}\n\n"
        f"Avisos de datos:\n{bullets(notices)}\n\n"
        f"Fragmentos de guías:\n{number_chunks(chunks)}\n\n"
        "Escribe la explicación en español siguiendo las reglas."
    )


def guide_excerpt(chunk: GuideChunk) -> str:
    text = chunk.text if len(chunk.text) <= EXCERPT_CHARS else chunk.text[:EXCERPT_CHARS] + "…"
    return f"Según la guía local [1] ({chunk.title}, {chunk.section}): {text}"
