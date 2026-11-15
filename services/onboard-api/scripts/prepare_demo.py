"""One-shot demo setup: wait for Ollama, pull missing models, load them into memory,
ingest guides if stale.

Safe to rerun. The index is rebuilt only when the stamp next to it does not match
the current corpus files, chunker and embedding model digest.

    uv run python scripts/prepare_demo.py
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import httpx

from onboard_api.assistant import ingest
from onboard_api.assistant.ingest import __main__ as ingest_cli
from onboard_api.assistant.ingest import medlineplus
from onboard_api.config import Settings

WAIT_SECONDS = 300


def log(message: str) -> None:
    print(f"[prepare-demo] {message}", flush=True)


def wait_for_ollama(http: httpx.Client) -> None:
    deadline = time.monotonic() + WAIT_SECONDS
    while True:
        try:
            http.get("/api/tags").raise_for_status()
            return
        except httpx.HTTPError as exc:
            if time.monotonic() > deadline:
                raise SystemExit(f"Ollama not reachable after {WAIT_SECONDS}s: {exc!r}")
            time.sleep(2)


def local_models(http: httpx.Client) -> dict[str, str]:
    """name -> digest. Bare names also match their ':latest' tag."""
    models = {}
    for entry in http.get("/api/tags").raise_for_status().json().get("models", []):
        models[entry["name"]] = entry["digest"]
        models.setdefault(entry["name"].removesuffix(":latest"), entry["digest"])
    return models


def pull(http: httpx.Client, model: str) -> None:
    log(f"pulling {model} (first run downloads it into the ollama volume)")
    last = ""
    with http.stream("POST", "/api/pull", json={"model": model}, timeout=None) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            event = json.loads(line) if line else {}
            if "error" in event:
                raise SystemExit(f"pull {model} failed: {event['error']}")
            status = event.get("status", "")
            if status != last:  # one log line per phase, not per progress tick
                log(f"{model}: {status}")
                last = status


def index_stamp(embed_digest: str, settings: Settings) -> str:
    digest = hashlib.sha256()
    for path in sorted(ingest.CORPUS_DIR.glob("*.json")) + [Path(medlineplus.__file__)]:
        digest.update(path.read_bytes())
    digest.update(f"{settings.ollama_embed_model}@{embed_digest}".encode())
    digest.update(settings.guides_collection.encode())
    return digest.hexdigest()


def main() -> int:
    settings = Settings()
    with httpx.Client(base_url=settings.ollama_base_url, timeout=30) as http:
        log(f"waiting for Ollama at {settings.ollama_base_url}")
        wait_for_ollama(http)
        for model in (settings.ollama_chat_model, settings.ollama_embed_model):
            if model in local_models(http):
                log(f"{model} already installed")
            else:
                pull(http, model)
        embed_digest = local_models(http)[settings.ollama_embed_model]
        # Load both models now: a cold load on CPU takes longer than the API's timeouts,
        # and an aborted load leaves the model unused (the ollama service keeps them loaded).
        log(f"loading {settings.ollama_chat_model} and {settings.ollama_embed_model} into memory")
        http.post("/api/chat", json={"model": settings.ollama_chat_model, "messages": []},
                  timeout=None).raise_for_status()
        http.post("/api/embed", json={"model": settings.ollama_embed_model, "input": "warm-up"},
                  timeout=None).raise_for_status()

    stamp_file = settings.chroma_path / "ingest-stamp.txt"
    stamp = index_stamp(embed_digest, settings)
    if stamp_file.exists() and stamp_file.read_text().strip() == stamp:
        log(f"guide index at {settings.chroma_path} is up to date")
        return 0
    log("guide index missing or outdated, running ingest")
    code = ingest_cli.main([])
    if code:
        log(f"ingest failed with exit code {code}")
        return code
    stamp_file.write_text(stamp)
    log("setup complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
