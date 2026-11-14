---
name: chromadb-retrieval
description: Index and search onboard guides in a local ChromaDB collection for the assistant. Use when changing integrations/chroma.py, guide ingestion, embeddings, or retrieval thresholds.
---

# ChromaDB retrieval (planned)

Status: not a dependency yet. Add in `services/onboard-api`: `uv add chromadb`. Commit `uv.lock`.

## Where
- Planned client: `services/onboard-api/src/onboard_api/assistant/integrations/chroma.py`.
- Guide sources and the ingestion entry point are not decided. Agree with the user first (for example `services/onboard-api/data/guides/` and `uv run python -m onboard_api.assistant.ingest_guides`). Keep the persisted Chroma directory out of git.

## Do
- `chromadb.PersistentClient(path=settings.chroma_path)`, one collection (for example `onboard_guides`), created once in lifespan.
- Use a local embedding function (Ollama embeddings via `chromadb.utils.embedding_functions.OllamaEmbeddingFunction`). Use the same embedding model for ingest and query; changing it requires re-indexing.
- Chunk guides by section. Store `guide_id`, `title` and `section` in metadata so answers can cite sources.
- Expose `search(question, k) -> list[GuideChunk]`. Filter by a distance threshold from settings. Return `[]` when nothing is relevant; the medical workflow reports that explicitly.
- Make ingestion idempotent: stable ids (`guide_id:section`) with `upsert`.

## Verify
- Test with `chromadb.EphemeralClient()` and a fake embedding function: ingest two chunks, a matching query hits one, an unrelated query returns `[]`.
- Workflow tests use a fake retriever instead of Chroma.

Docs: https://docs.trychroma.com/docs/overview/introduction , https://docs.trychroma.com/docs/embeddings/embedding-functions
