"""Ingest the corpus manifest into ChromaDB.

    uv run python -m onboard_api.assistant.ingest [--xml PATH] [--dry-run]

Without --xml, discovers the newest mplus_topics_YYYY-MM-DD.xml on
https://medlineplus.gov/xml.html and caches it in data/corpus_cache/.
Re-ingest upserts by chunk_id and deletes chunks no longer produced.
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import httpx

from onboard_api.assistant.ingest import CACHE_DIR, CORPUS_DIR, TOPICS
from onboard_api.assistant.ingest.medlineplus import build_chunks, estimate_tokens, load_xml
from onboard_api.assistant.integrations import DependencyUnavailable
from onboard_api.assistant.integrations.chroma import CHUNK_FIELDS, GuideRetriever
from onboard_api.assistant.integrations.ollama import OllamaClient
from onboard_api.config import Settings

_XML_NAME = re.compile(r"mplus_topics_(\d{4}-\d{2}-\d{2})\.xml")


def load_manifest() -> dict[str, Any]:
    return json.loads((CORPUS_DIR / "manifest.json").read_text(encoding="utf-8"))


def load_curated(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    path = CORPUS_DIR / manifest["curated_file"]
    return json.loads(path.read_text(encoding="utf-8"))


def validate(chunks: list[dict[str, Any]]) -> list[str]:
    problems = []
    ids = Counter(c.get("chunk_id") for c in chunks)
    problems += [f"duplicate chunk_id {i}" for i, n in ids.items() if n > 1]
    for c in chunks:
        missing = [f for f in (*CHUNK_FIELDS, "text") if not c.get(f)]
        if missing:
            problems.append(f"{c.get('chunk_id')}: missing {missing}")
        if c.get("topic") not in TOPICS:
            problems.append(f"{c.get('chunk_id')}: unknown topic {c.get('topic')!r}")
        if c.get("language") not in ("es", "en"):
            problems.append(f"{c.get('chunk_id')}: bad language {c.get('language')!r}")
    return problems


def fetch_latest_xml(index_url: str) -> Path:
    with httpx.Client(timeout=60, follow_redirects=True) as http:
        page = http.get(index_url)
        page.raise_for_status()
        dates = sorted(set(_XML_NAME.findall(page.text)))
        if not dates:
            raise SystemExit(f"No mplus_topics_*.xml link found on {index_url}")
        name = f"mplus_topics_{dates[-1]}.xml"
        target = CACHE_DIR / name
        if target.exists():
            print(f"Using cached {target}")
            return target
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Downloading https://medlineplus.gov/xml/{name}")
        partial = target.with_suffix(".part")
        with http.stream("GET", f"https://medlineplus.gov/xml/{name}") as response:
            response.raise_for_status()
            with partial.open("wb") as out:
                for block in response.iter_bytes():
                    out.write(block)
        partial.replace(target)
        return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m onboard_api.assistant.ingest")
    parser.add_argument("--xml", type=Path, help="Reuse a local MedlinePlus Health Topic XML")
    parser.add_argument("--dry-run", action="store_true", help="Parse and chunk only")
    args = parser.parse_args(argv)

    settings = Settings()
    manifest = load_manifest()
    if manifest["embedding_model"] != settings.ollama_embed_model:
        print(
            f"Manifest embedding_model {manifest['embedding_model']!r} != "
            f"ONBOARD_OLLAMA_EMBED_MODEL {settings.ollama_embed_model!r}; aborting."
        )
        return 2
    if manifest["collection"] != settings.guides_collection:
        print("Manifest collection != settings.guides_collection; aborting.")
        return 2

    mplus = manifest["medlineplus"]
    xml_path = args.xml or fetch_latest_xml(mplus["index_url"])
    chunks, problems = build_chunks(load_xml(xml_path), mplus["topics"], mplus["reuse_basis"])
    chunks += load_curated(manifest)
    problems += validate(chunks)
    for problem in problems:
        print(f"PROBLEM: {problem}")
    if any("duplicate" in p or "missing" in p or "unknown" in p for p in problems):
        return 1

    tokens = sorted(estimate_tokens(c["text"]) for c in chunks)
    print(
        f"{len(chunks)} chunks from {xml_path.name} + {manifest['curated_file']}; "
        f"est. tokens min {tokens[0]} median {tokens[len(tokens) // 2]} max {tokens[-1]}"
    )
    if args.dry_run:
        for (source, lang), n in sorted(Counter((c["source_id"], c["language"]) for c in chunks).items()):
            print(f"  {source:38} {lang} {n}")
        return 0

    ollama = OllamaClient(
        settings.ollama_base_url,
        settings.ollama_chat_model,
        settings.ollama_embed_model,
        # Batch embedding of long chunks is slower than a chat turn.
        max(settings.ollama_timeout_seconds, 120.0),
    )
    retriever = GuideRetriever(
        settings.chroma_path, settings.guides_collection, ollama, settings.retrieval_max_distance
    )
    try:
        digest = ollama.model_digest(settings.ollama_embed_model)
        embed_model = f"{settings.ollama_embed_model}@{digest}"
        retriever.upsert_chunks(chunks, embed_model=embed_model)
        deleted = retriever.delete_missing(c["chunk_id"] for c in chunks)
        counts = retriever.count_by("source_id", "language")
    except DependencyUnavailable as exc:
        print(f"Ingest failed: {exc}")
        return 1

    print(f"Upserted {len(chunks)} chunks with {embed_model} into {settings.chroma_path}")
    print(f"Deleted {len(deleted)} stale chunks{': ' + ', '.join(deleted) if deleted else ''}")
    for (source, lang), n in sorted(counts.items()):
        print(f"  {source:38} {lang} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
