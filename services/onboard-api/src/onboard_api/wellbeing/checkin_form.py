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
            prompt="How many hours did you sleep last night?",
            kind="hours",
            min=0,
            max=24,
            step=0.5,
            min_label="0 h",
            max_label="24 h",
            higher_is_better=True,
        ),
        _scale("sleep_quality", "How well did you sleep?", "Very poorly", "Very well"),
        _scale("energy", "How much energy do you have today?", "Exhausted", "Full of energy"),
        _scale("mood", "How is your mood today?", "Very low", "Very good"),
        _scale(
            "interest", "Did you enjoy or feel interested in what you did today?", "Not at all", "A lot"
        ),
        _scale(
            "stress",
            "How much tension or worry did you feel today?",
            "None",
            "A lot",
            better=False,
        ),
        _scale(
            "crew_connection",
            "How connected did you feel with the crew?",
            "Isolated",
            "Very connected",
        ),
        CheckinFormItem(
            key="comment",
            prompt="Anything you want to add? (optional, private)",
            kind="text",
            max_length=500,
            optional=True,
        ),
    ],
)
