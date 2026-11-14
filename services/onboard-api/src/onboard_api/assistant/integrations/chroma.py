"""Guide retrieval over a local ChromaDB collection (cosine space).

Embeddings always come from the injected Embedder (Ollama in production), never from
Chroma's default embedding function, so ingest and query share one pinned model.
"""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from onboard_api.assistant.integrations import DependencyUnavailable, Embedder, GuideChunk

# Metadata keys every stored chunk carries (see corpus manifest / ingest).
CHUNK_FIELDS = (
    "chunk_id",
    "source_id",
    "source_title",
    "source_url",
    "section",
    "topic",
    "language",
    "source_version",
    "reuse_basis",
)
EMBED_BATCH = 16


def embedding_text(chunk: dict[str, Any]) -> str:
    """Text that gets vectorized: title and section in front of the chunk body."""
    return f"{chunk['source_title']} — {chunk['section']}\n\n{chunk['text']}"


class GuideRetriever:
    def __init__(
        self, path: Path | str, collection: str, embedder: Embedder, max_distance: float
    ) -> None:
        self.path = Path(path)
        self.collection_name = collection
        self.embedder = embedder
        self.max_distance = max_distance
        self._collection = None

    def _get_collection(self):
        if self._collection is None:
            try:
                import chromadb

                client = chromadb.PersistentClient(path=str(self.path))
                self._collection = client.get_or_create_collection(
                    self.collection_name,
                    embedding_function=None,
                    configuration={"hnsw": {"space": "cosine"}},
                )
            except Exception as exc:  # chromadb raises many types; all mean "unavailable"
                raise DependencyUnavailable(f"ChromaDB unavailable: {exc!r}") from exc
        return self._collection

    def search(
        self, query: str, k: int = 3, topics: list[str] | None = None, language: str = "es"
    ) -> list[GuideChunk]:
        collection = self._get_collection()
        vector = self.embedder.embed([query])[0]
        other = "en" if language == "es" else "es"
        for lang in (language, other):
            hits = self._query(collection, vector, k, topics, lang)
            if hits:
                return hits
        return []

    def _query(self, collection, vector, k, topics, language) -> list[GuideChunk]:
        where: dict[str, Any] = {"language": language}
        if topics:
            where = {"$and": [where, {"topic": {"$in": list(topics)}}]}
        try:
            result = collection.query(
                query_embeddings=[vector],
                n_results=k,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            raise DependencyUnavailable(f"ChromaDB query failed: {exc!r}") from exc
        hits = [
            GuideChunk(
                chunk_id=chunk_id,
                source_id=meta["source_id"],
                title=meta["source_title"],
                section=meta["section"],
                url=meta["source_url"],
                topic=meta["topic"],
                language=meta["language"],
                text=doc,
                distance=float(dist),
            )
            for chunk_id, doc, meta, dist in zip(
                result["ids"][0],
                result["documents"][0],
                result["metadatas"][0],
                result["distances"][0],
            )
            if dist <= self.max_distance
        ]
        return sorted(hits, key=lambda h: h.distance)

    # Ingest side ---------------------------------------------------------------

    def upsert_chunks(self, chunks: list[dict[str, Any]], embed_model: str = "") -> None:
        """Embed and upsert chunks by their stable chunk_id.

        Each chunk dict has the CHUNK_FIELDS plus `text`. `embed_model` (name@digest)
        is stored on every chunk so a model change is visible in the data.
        """
        collection = self._get_collection()
        for start in range(0, len(chunks), EMBED_BATCH):
            batch = chunks[start : start + EMBED_BATCH]
            vectors = self.embedder.embed([embedding_text(c) for c in batch])
            try:
                collection.upsert(
                    ids=[c["chunk_id"] for c in batch],
                    embeddings=vectors,
                    documents=[c["text"] for c in batch],
                    metadatas=[
                        {**{f: c[f] for f in CHUNK_FIELDS}, "embed_model": embed_model}
                        for c in batch
                    ],
                )
            except Exception as exc:
                raise DependencyUnavailable(f"ChromaDB upsert failed: {exc!r}") from exc

    def delete_missing(self, keep_ids: Iterable[str]) -> list[str]:
        """Delete stored chunks whose id is not in keep_ids. Returns the deleted ids."""
        collection = self._get_collection()
        keep = set(keep_ids)
        try:
            stale = [i for i in collection.get(include=[])["ids"] if i not in keep]
            if stale:
                collection.delete(ids=stale)
        except Exception as exc:
            raise DependencyUnavailable(f"ChromaDB delete failed: {exc!r}") from exc
        return stale

    def count_by(self, *fields: str) -> dict[tuple, int]:
        """Chunk counts grouped by metadata fields (ingest report)."""
        metas = self._get_collection().get(include=["metadatas"])["metadatas"]
        counts: dict[tuple, int] = {}
        for meta in metas:
            key = tuple(meta.get(f) for f in fields)
            counts[key] = counts.get(key, 0) + 1
        return counts
