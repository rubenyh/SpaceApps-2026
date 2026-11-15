"""Local Ollama client: chat (LLM) and embeddings (Embedder) over its HTTP API."""

import httpx

from onboard_api.assistant.integrations import DependencyUnavailable


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        chat_model: str,
        embed_model: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,  # tests pass httpx.MockTransport
        json_timeout_seconds: float | None = None,  # chat_json (interpreter) wait
    ) -> None:
        self.chat_model = chat_model
        self.embed_model = embed_model
        self.json_timeout_seconds = json_timeout_seconds or timeout_seconds
        self._http = httpx.Client(
            base_url=base_url, timeout=timeout_seconds, transport=transport
        )

    def _post(self, path: str, payload: dict, timeout: float | None = None) -> dict:
        try:
            kwargs = {"timeout": timeout} if timeout else {}
            response = self._http.post(path, json=payload, **kwargs)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise DependencyUnavailable(f"Ollama {path} failed: {exc!r}") from exc

    def chat(self, system: str, user: str) -> str:
        data = self._post(
            "/api/chat",
            {
                "model": self.chat_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "options": {"temperature": 0.1},
            },
        )
        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise DependencyUnavailable(f"Unexpected Ollama chat reply: {data!r}") from exc

    def chat_json(self, system: str, user: str, schema: dict) -> str:
        data = self._post(
            "/api/chat",
            {
                "model": self.chat_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "stream": False,
                "format": schema,  # Ollama structured output
                "options": {"temperature": 0, "num_predict": 256},  # cap a runaway JSON
            },
            timeout=self.json_timeout_seconds,
        )
        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise DependencyUnavailable(f"Unexpected Ollama chat reply: {data!r}") from exc

    def embed(self, texts: list[str]) -> list[list[float]]:
        data = self._post("/api/embed", {"model": self.embed_model, "input": texts})
        embeddings = data.get("embeddings") if isinstance(data, dict) else None
        if not isinstance(embeddings, list) or len(embeddings) != len(texts):
            raise DependencyUnavailable("Unexpected Ollama embed reply")
        return embeddings

    def model_digest(self, model: str) -> str:
        """Digest of a local model from /api/tags, used to pin the embedding version."""
        try:
            response = self._http.get("/api/tags")
            response.raise_for_status()
            models = response.json()["models"]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise DependencyUnavailable(f"Ollama /api/tags failed: {exc!r}") from exc
        names = {model, f"{model}:latest"}
        for entry in models:
            if entry.get("name") in names or entry.get("model") in names:
                return entry["digest"]
        raise DependencyUnavailable(f"Model {model} not found in Ollama")
