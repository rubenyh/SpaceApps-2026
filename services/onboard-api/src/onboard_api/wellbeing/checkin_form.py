"""Daily check-in questions. Written by the team; not copied from any
standardised questionnaire. Inspired by short screening scales (mood,
anxiety, sleep, stress) but adapted to daily use, which is not clinically
validated.
"""

from onboard_api.wellbeing.schemas import CheckinForm, CheckinFormItem


def _scale(key: str, prompt: str, low: str, high: str, *, better: bool = True) -> CheckinFormItem:
    return CheckinFormItem(
        key=key,
        prompt=prompt,
        kind="scale",
        min=0,
        max=4,
        step=1,
        min_label=low,
        max_label=high,
        higher_is_better=better,
    )


CHECKIN_FORM = CheckinForm(
    version="v1",
    estimated_seconds=45,
    items=[
        CheckinFormItem(
            key="sleep_hours",
            prompt="¿Cuántas horas dormiste anoche?",
            kind="hours",
            min=0,
            max=24,
            step=0.5,
            min_label="0 h",
            max_label="24 h",
            higher_is_better=True,
        ),
        _scale("sleep_quality", "¿Qué tan bien dormiste?", "Muy mal", "Muy bien"),
        _scale("energy", "¿Cuánta energía tienes hoy?", "Agotado/a", "Mucha energía"),
        _scale("mood", "¿Cómo está tu ánimo hoy?", "Muy bajo", "Muy bueno"),
        _scale(
            "interest", "¿Disfrutaste o te interesó lo que hiciste hoy?", "Nada", "Mucho"
        ),
        _scale(
            "stress",
            "¿Cuánta tensión o preocupación sentiste hoy?",
            "Nada",
            "Mucha",
            better=False,
        ),
        _scale(
            "crew_connection",
            "¿Qué tan conectado/a te sentiste con la tripulación?",
            "Aislado/a",
            "Muy conectado/a",
        ),
        CheckinFormItem(
            key="comment",
            prompt="¿Algo que quieras comentar? (opcional, privado)",
            kind="text",
            max_length=500,
            optional=True,
        ),
    ],
)
