"""Status workflow: deterministic, read-only quick questions about the crew member's own
stored readings. No LLM and no retriever, so it works with Ollama and ChromaDB down."""

import re
from datetime import UTC, datetime

from onboard_api.assistant.workflows.medical.context import LABELS, format_age, snapshot
from onboard_api.assistant.workflows.medical.nodes import _safe_load
from onboard_api.assistant.workflows.medical.state import ReadingsContext, ReadingsProvider
from onboard_api.schemas.assistant import AssistantResponse
from onboard_api.schemas.readings import is_simulated_source

_READINGS = re.compile(r"\breadings?\b")
_MISSING = re.compile(r"\bmis+ing\b|\black(ing)?\b")
_SUMMARIZE = re.compile(r"\bsu+m+ar(i[sz]e|y)\b|\boverview\b")
_MY_STATUS = re.compile(r"\bmy status\b|\bstatus today\b")


def status_question(text: str) -> str | None:
    """"summary", "missing" or None, on lowercase accent-free text."""
    if _READINGS.search(text) and _MISSING.search(text):
        return "missing"
    if (_SUMMARIZE.search(text) and "status" in text) or _MY_STATUS.search(text):
        return "summary"
    return None


def _label(kind: str) -> str:
    label = LABELS.get(kind, kind)
    return label[:1].upper() + label[1:]


def _value(r) -> str:
    value = f"{r.value:g}" if r.value is not None else (r.value_text or "")
    return f"{value} {r.unit}".strip()


def _summary(ctx: ReadingsContext, at: datetime, who: str) -> str:
    lines = [f"Status for {who} on {at:%Y-%m-%d}, as of {at:%H:%M} UTC."]
    for kind, r in ctx.latest.items():
        rec = r.recorded_at.astimezone(UTC)
        if rec.date() < at.date():
            line = f"- {_label(kind)}: Last known {_value(r)} ({rec:%Y-%m-%d %H:%M} UTC)"
        else:
            line = f"- {_label(kind)}: {_value(r)} ({rec:%H:%M} UTC)"
        if r.freshness == "future":
            line += " · capture time ahead of the onboard clock, not current"
        elif r.freshness == "stale":
            line += f" · stale ({format_age(r.age_seconds)} old)"
        if r.quality != "good":
            line += f" · quality {r.quality}"
        if is_simulated_source(r.source):
            line += f" · Simulated · {r.source}"
        lines.append(line + ".")
    never = [LABELS[k] for k in LABELS if k not in ctx.latest]
    if not ctx.latest:
        lines.append(f"No readings recorded for {who}.")
    elif never:
        lines.append(f"No readings yet: {', '.join(never)}.")
    return "\n".join(lines)


def _missing(ctx: ReadingsContext, at: datetime, who: str) -> str:
    groups: dict[str, list[str]] = {
        "Never measured": [LABELS[k] for k in LABELS if k not in ctx.latest],
        "Stale": [], "Future-dated (clock warning, not used)": [], "Poor quality": [],
    }
    available = []
    for kind, r in ctx.latest.items():
        label = LABELS.get(kind, kind)
        if r.freshness == "future":
            ahead = int((r.recorded_at - at).total_seconds())
            groups["Future-dated (clock warning, not used)"].append(f"{label} ({ahead} s ahead)")
        elif r.freshness == "stale":
            groups["Stale"].append(f"{label} ({format_age(r.age_seconds)} old)")
        elif r.quality != "good":
            groups["Poor quality"].append(f"{label} ({r.quality})")
        else:  # fresh simulated and no-range readings count as available
            available.append(label + (" (simulated)" if is_simulated_source(r.source) else ""))
    lines = [f"Readings check for {who} as of {at:%H:%M} UTC on {at:%Y-%m-%d}:"]
    lines += [f"- {name}: {', '.join(items)}." for name, items in groups.items() if items]
    if available:
        lines.append(f"- Available: {', '.join(available)}.")
    if not any(groups.values()):
        lines.append("Nothing is missing: every reading is current.")
    return "\n".join(lines)


def respond_status(state, readings: ReadingsProvider) -> dict:
    request = state["request"]
    ctx, at = _safe_load(readings, state)  # onboard clock read now, as in medical
    at = at.astimezone(UTC)
    who = request.astronaut_id or "the crew member"
    if not ctx.available:
        reply = "Readings unavailable: " + " ".join(ctx.warnings)
    elif state.get("status_question") == "missing":
        reply = _missing(ctx, at, who)
    else:
        reply = _summary(ctx, at, who)
    return {
        "response": AssistantResponse(
            reply=reply,
            workflow="status",
            needs_clarification=False,
            data_notices=list(ctx.warnings),
            assessed_at=at,
            readings_snapshot=snapshot(ctx),
            # A pending medical follow-up stays available to the console.
            clarification=request.clarification,
        )
    }
