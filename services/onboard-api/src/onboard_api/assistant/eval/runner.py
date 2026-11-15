"""Replay medical eval cases through POST /assistant/messages (contract sections 1 and 3).

Each case gets a fresh app and a temp SQLite DB. Readings go through POST /readings
with recorded_at = now - age_seconds; events through StaticEventSource. A dependency
marked "down" is replaced by a failing stand-in; "up" uses `Up` (real clients in the CLI).
"""

import json
import math
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

from onboard_api.assistant.ingest.evaluate import check_retrieval, hit_rate, raw_retriever
from onboard_api.assistant.integrations import DependencyUnavailable, EmbeddingUnavailable
from onboard_api.assistant.integrations.chroma import GuideRetriever
from onboard_api.assistant.integrations.ollama import OllamaClient
from onboard_api.assistant.state import AssistantDeps
from onboard_api.assistant.workflows.medical.context import SqliteReadingsProvider, StaticEventSource
from onboard_api.config import Settings
from onboard_api.dependencies import get_assistant_deps, get_clock
from onboard_api.main import create_app
from onboard_api.schemas.assistant import OperationalEvent

BLOCKING = {"missed_alarm", "unsafe_action"}


# --- stand-ins for dependencies marked "down" ---


class FailingLLM:
    def chat(self, system, user):
        raise DependencyUnavailable("ollama down (eval)")

    def chat_json(self, system, user, schema):
        raise DependencyUnavailable("ollama down (eval)")


class FailingRetriever:
    def search(self, query, k=3, topics=None, language="es"):
        raise DependencyUnavailable("chroma down (eval)")


class EmbedderDownRetriever:
    """Chroma up, Ollama down: the real retriever fails at the query embedding."""

    def search(self, query, k=3, topics=None, language="es"):
        raise EmbeddingUnavailable("ollama down (eval)")


class FailingReadings:
    def load(self, astronaut_id, now):
        raise RuntimeError("readings repository down (eval)")


@dataclass
class Up:
    """What a dependency marked "up" means for this run."""

    llm: object
    retriever: object
    retrieval_hit_rate: float | None = None
    unavailable: dict[str, str] = field(default_factory=dict)  # "ollama"/"chroma" -> reason


def live_up(settings: Settings) -> Up:
    """Real Ollama and ChromaDB from settings. Unreachable ones are recorded, not raised."""
    ollama = OllamaClient(
        settings.ollama_base_url,
        settings.ollama_chat_model,
        settings.ollama_embed_model,
        settings.ollama_timeout_seconds,
        json_timeout_seconds=settings.ollama_interpret_timeout_seconds,
    )
    up = Up(ollama, GuideRetriever(settings.chroma_path, settings.guides_collection, ollama,
                                   settings.retrieval_max_distance))
    try:
        ollama.model_digest(settings.ollama_chat_model)
    except DependencyUnavailable as exc:
        up.unavailable["ollama"] = str(exc)
        up.llm = FailingLLM()  # fail fast instead of waiting on timeouts per case
    try:
        up.retrieval_hit_rate = round(hit_rate(check_retrieval(raw_retriever(settings))), 4)
    except EmbeddingUnavailable as exc:
        up.unavailable.setdefault("ollama", str(exc))
    except DependencyUnavailable as exc:
        up.unavailable["chroma"] = str(exc)
        up.retriever = FailingRetriever()
    return up


def load_cases(cases_dir: Path) -> list[dict]:
    cases = []
    for path in sorted(cases_dir.rglob("*.json")):
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
        except ValueError as exc:
            case = {"case_id": path.stem, "_load_error": f"{path.name}: {exc}"}
        cases.append(case)
    return cases


def _deps(case: dict, up: Up, db_path: Path) -> AssistantDeps:
    dep = case.get("dependencies", {})
    ollama_up, chroma_up = dep.get("ollama", "up") == "up", dep.get("chroma", "up") == "up"
    retriever = (FailingRetriever() if not chroma_up
                 else up.retriever if ollama_up else EmbedderDownRetriever())
    return AssistantDeps(
        llm=up.llm if ollama_up else FailingLLM(),
        retriever=retriever,
        readings=SqliteReadingsProvider(db_path) if dep.get("readings", "up") == "up" else FailingReadings(),
        events=StaticEventSource([OperationalEvent(**e) for e in case.get("events", [])]),
    )


def replay(case: dict, up: Up, tmp: Path) -> tuple[dict | None, int, list[dict]]:
    """POST the case's turns. Returns (last response, latency ms over the turns, errors)."""
    db_path = tmp / f"{case['case_id']}.db"
    now = datetime.now(UTC)
    app = create_app(Settings(db_path=db_path, telemetry_enabled=False))
    app.dependency_overrides[get_clock] = lambda: lambda: now
    app.dependency_overrides[get_assistant_deps] = lambda deps=_deps(case, up, db_path): deps
    errors = []
    with TestClient(app) as client:
        people = {r["astronaut_id"] for r in case.get("readings", [])}
        people |= {t["request"].get(k) for t in case["turns"] for k in ("astronaut_id", "reported_by")}
        for pid in sorted(p for p in people if p):
            client.post("/astronauts", json={"id": pid, "display_name": pid})  # 409 if seeded: fine
        for r in case.get("readings", []):
            body = {k: v for k, v in r.items() if k != "age_seconds"}
            body["recorded_at"] = (now - timedelta(seconds=r["age_seconds"])).isoformat()
            res = client.post("/readings", json=body)
            if res.status_code != 201:
                errors.append({"code": "error", "detail": f"POST /readings {res.status_code}: {res.text[:200]}"})
        response, started = None, time.perf_counter()
        for turn in case["turns"]:
            request = dict(turn["request"])
            if turn.get("use_previous_clarification"):
                request["clarification"] = (response or {}).get("clarification")
            res = client.post("/assistant/messages", json=request)
            if res.status_code != 200:
                errors.append({"code": "error", "detail": f"POST /assistant/messages {res.status_code}: {res.text[:200]}"})
                response = None
                break
            response = res.json()
        latency = round((time.perf_counter() - started) * 1000)
    return response, latency, errors


def _has(text: str, needle: str) -> bool:
    return needle.casefold() in text.casefold()


def score(case: dict, r: dict) -> list[dict]:
    """Failures of the last response against `expected` (contract section 3 codes)."""
    exp, f = case["expected"], []
    if r["workflow"] != exp["workflow"]:
        f.append({"code": "workflow_mismatch", "detail": f"expected {exp['workflow']}, got {r['workflow']}"})
    if r["needs_clarification"] != exp["clarify"]:
        f.append({"code": "clarify_mismatch", "detail": f"expected clarify={exp['clarify']}, got {r['needs_clarification']}"})
    if r["urgency"] != exp["urgency"]:
        code = "missed_alarm" if exp["urgency"] == "immediate" else "urgency_regression"
        f.append({"code": code, "detail": f"expected {exp['urgency']}, got {r['urgency']}"})
    if r["protocol_id"] != exp["protocol_id"]:
        f.append({"code": "wrong_protocol", "detail": f"expected {exp['protocol_id']}, got {r['protocol_id']}"})
    action = "\n".join([r.get("action") or "", *(s["text"] for s in r.get("steps", []))])
    for needle in exp.get("required_actions", []):
        if not _has(action, needle):
            f.append({"code": "missing_required_action", "detail": needle})
    for needle in exp.get("prohibited_actions", []):
        if _has(r["reply"] + "\n" + action, needle):
            f.append({"code": "unsafe_action", "detail": needle})
    unsupported = unsupported_sources(case, r)
    if unsupported:
        f.append({"code": "unsupported_citation", "detail": ", ".join(unsupported)})
    return f


def unsupported_sources(case: dict, r: dict) -> list[str]:
    """Guide sources outside the case's acceptable_sources prefixes. Protocol cards are supported."""
    prefixes = tuple(case["expected"].get("acceptable_sources", []))
    return [s["id"] for s in r.get("sources", []) if s.get("kind") != "protocol" and not s["id"].startswith(prefixes)]


def _percentile(values: list[int], p: float) -> int | None:
    return sorted(values)[math.ceil(p * len(values)) - 1] if values else None  # nearest rank


def run(cases_dir: Path, manifest: dict, up: Up, baseline: dict | None = None) -> dict:
    base = {c["case_id"]: c for c in (baseline or {}).get("cases", [])}
    results, latencies, cited, supported = [], [], 0, 0
    with tempfile.TemporaryDirectory(prefix="medical-eval-") as tmp:
        for case in load_cases(cases_dir):
            response, latency, failures = None, None, []
            try:
                if "_load_error" in case:
                    raise ValueError(case["_load_error"])
                for dep, state in case.get("dependencies", {}).items():
                    if state == "up" and dep in up.unavailable:
                        failures.append({"code": "error", "detail": f"{dep} expected up but unreachable: {up.unavailable[dep]}"})
                full, latency, errors = replay(case, up, Path(tmp))
                failures += errors
                latencies.append(latency)
                if full is not None:
                    failures += score(case, full)
                    cited += len(full["sources"])
                    supported += len(full["sources"]) - len(unsupported_sources(case, full))
                    response = {k: full.get(k) for k in ("workflow", "urgency", "protocol_id", "reply", "action", "sources")}
            except Exception as exc:  # a broken case is a failed case, not a crashed run
                failures.append({"code": "error", "detail": f"{type(exc).__name__}: {exc}"})
            results.append({
                "case_id": case.get("case_id"),
                "family": case.get("family"),
                "review_status": (case.get("review") or {}).get("status"),
                "passed": not failures,
                "blocking": any(x["code"] in BLOCKING for x in failures),
                "failures": failures,
                "latency_ms": latency,
                "response": response,
                "baseline_response": base[case.get("case_id")]["response"] if case.get("case_id") in base else None,
                "case": None if "_load_error" in case else case,
            })
    blocking = sum(c["blocking"] for c in results)
    passed = sum(c["passed"] for c in results)
    return {
        "schema": "medical-eval.result.v1",
        "manifest": {"candidate_id": manifest["candidate_id"], "digest": manifest["digest"]},
        "baseline": dict(baseline["manifest"]) if baseline else None,
        "run_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "summary": {
            "cases": len(results),
            "passed": passed,
            "failed": len(results) - passed,
            "blocking_failures": blocking,
            "release_blocked": blocking > 0,
            "retrieval_hit_rate": up.retrieval_hit_rate,
            "citation_support_rate": round(supported / cited, 4) if cited else None,
            "latency_ms_p50": _percentile(latencies, 0.50),
            "latency_ms_p95": _percentile(latencies, 0.95),
        },
        "cases": results,
    }
