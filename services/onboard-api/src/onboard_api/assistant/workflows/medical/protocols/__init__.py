"""Versioned protocol cards (<id>.json), validated with the Protocol model."""

from functools import cache
from pathlib import Path

from onboard_api.assistant.workflows.medical.state import Protocol


@cache
def load_catalog() -> dict[str, Protocol]:
    cards = {}
    for path in sorted(Path(__file__).parent.glob("*.json")):
        card = Protocol.model_validate_json(path.read_text(encoding="utf-8"))
        if card.id != path.stem:
            raise ValueError(f"{path.name}: id {card.id!r} does not match the file name")
        cards[card.id] = card
    return cards
