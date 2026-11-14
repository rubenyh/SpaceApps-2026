---
name: ollama-local
description: Connect the onboard assistant to a local Ollama server for chat and embeddings. Use when adding or changing integrations/ollama.py, choosing models, or debugging LLM calls.
---

# Ollama local LLM

Status: Ollama is called with httpx 0.28.1 (`/api/chat`, `/api/embed`); langchain-ollama is not used. Default models: `qwen2.5:0.5b` (chat), `bge-m3` (embeddings).

## Where
- Client: `services/onboard-api/src/onboard_api/assistant/integrations/ollama.py`.

## Do
- Base URL (default `http://127.0.0.1:11434`), chat model, embedding model and timeouts come from settings. Never hard-code model names in nodes.
- Build one client in FastAPI lifespan and pass it into `build_assistant_graph`.
- Use low temperature for routing. Use structured output (`with_structured_output` or JSON format) for intent labels and validate it. Invalid output means fallback, not a crash.
- Ollama down or model missing: return a clear error reply through the shared response contract and log it. Do not retry forever.
- Everything stays local. No cloud fallback.

## Verify
```bash
ollama list                              # model present
curl http://127.0.0.1:11434/api/tags
```
Unit tests use fakes (`langgraph-workflows` skill). A live smoke test is optional and must skip when Ollama is not reachable.

Docs: https://github.com/ollama/ollama/blob/main/docs/api.md , https://python.langchain.com/docs/integrations/chat/ollama/
