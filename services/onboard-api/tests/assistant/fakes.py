"""Fakes for the assistant graph. No Ollama, ChromaDB or SQLite needed."""

from datetime import datetime

from onboard_api.assistant.integrations import DependencyUnavailable, GuideChunk
from onboard_api.assistant.workflows.medical.state import ReadingsContext
from onboard_api.schemas.assistant import OperationalEvent


class Forbidden:
    """Any method call is recorded and fails. Assert `calls == []` after the run
    (nodes catch dependency errors, so the raise alone could be swallowed)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[str] = []

    def __getattr__(self, attr: str):
        def call(*args, **kwargs):
            self.calls.append(attr)
            raise AssertionError(f"{self.name}.{attr} must not be called")

        return call


class FakeLLM:
    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.calls: list[tuple[str, str]] = []

    def chat(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.reply


class FailingLLM:
    def chat(self, system: str, user: str) -> str:
        raise DependencyUnavailable("ollama down")


class FakeRetriever:
    def __init__(self, chunks: list[GuideChunk]) -> None:
        self.chunks = chunks
        self.calls: list[dict] = []

    def search(self, query, k=3, topics=None, language="es"):
        self.calls.append({"query": query, "k": k, "topics": topics, "language": language})
        return self.chunks[:k]


class FailingRetriever:
    def search(self, query, k=3, topics=None, language="es"):
        raise DependencyUnavailable("chroma down")


class FakeReadings:
    def __init__(self, ctx: ReadingsContext | None = None) -> None:
        self.ctx = ctx or ReadingsContext(available=True)
        self.calls: list[str | None] = []

    def load(self, astronaut_id: str | None, now: datetime) -> ReadingsContext:
        self.calls.append(astronaut_id)
        return self.ctx


class FailingReadings:
    def load(self, astronaut_id, now):
        raise RuntimeError("database is locked")


class FakeEvents:
    def __init__(self, events: list[OperationalEvent] | None = None) -> None:
        self.events = events or []

    def active_events(self, now: datetime) -> list[OperationalEvent]:
        return [e for e in self.events if e.status == "active"]


def chunk(i: int, topic: str = "breathing_problems") -> GuideChunk:
    return GuideChunk(
        chunk_id=f"chunk-{i}",
        source_id="medlineplus-breathing",
        title="Problemas respiratorios",
        section=f"Sección {i}",
        url="https://medlineplus.gov/spanish/breathingproblems.html",
        topic=topic,
        language="es",
        text=f"Texto de la guía número {i}.",
        distance=0.1,
    )
