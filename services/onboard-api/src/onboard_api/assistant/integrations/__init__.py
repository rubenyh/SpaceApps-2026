"""Shared integration interfaces. One client of each kind, shared by all workflows.

Implementations: ollama.OllamaClient (LLM + Embedder), chroma.GuideRetriever.
Workflows depend only on these Protocols so tests can pass fakes.
"""

from dataclasses import dataclass
from typing import Protocol


class DependencyUnavailable(Exception):
    """A local dependency (Ollama, ChromaDB, SQLite) failed or timed out."""


@dataclass(frozen=True)
class GuideChunk:
    chunk_id: str
    source_id: str
    title: str
    section: str
    url: str
    topic: str
    language: str  # "es" | "en"
    text: str
    distance: float


class LLM(Protocol):
    def chat(self, system: str, user: str) -> str:
        """Return the model text. Raise DependencyUnavailable on error or timeout."""
        ...


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Raise DependencyUnavailable on error or timeout."""
        ...


class Retriever(Protocol):
    def search(
        self, query: str, k: int = 3, topics: list[str] | None = None, language: str = "es"
    ) -> list[GuideChunk]:
        """Chunks within the distance threshold, best first; [] when nothing is relevant.

        Prefers `language`, falls back to the other language when the preferred one
        has no relevant chunk. `topics` filters by chunk topic when given.
        Raise DependencyUnavailable when ChromaDB or the embedder fails.
        """
        ...
