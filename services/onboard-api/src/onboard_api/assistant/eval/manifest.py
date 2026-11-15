"""Candidate manifest (contracts/medical-eval/README.md section 2)."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from onboard_api.assistant.ingest import CORPUS_DIR, SERVICE_ROOT
from onboard_api.config import Settings

REPO_ROOT = SERVICE_ROOT.parents[1]
MEDICAL_DIR = Path(__file__).resolve().parents[1] / "workflows" / "medical"


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def file_sha256(path: Path) -> str:
    """CRLF -> LF first, so Windows and LF checkouts of one commit hash the same."""
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def dir_sha256(path: Path, exclude: tuple[str, ...] = ()) -> str:
    """SHA-256 of the sorted lines "<relative posix path>\\t<file sha256>\\n", without
    __pycache__/, *.pyc and the top-level entries named in `exclude`."""
    lines = sorted(
        f"{f.relative_to(path).as_posix()}\t{file_sha256(f)}\n"
        for f in path.rglob("*")
        if f.is_file() and "__pycache__" not in f.parts and f.suffix != ".pyc"
        and f.relative_to(path).parts[0] not in exclude
    )
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def _rel(path: Path) -> str:
    path = path.resolve()
    return path.relative_to(REPO_ROOT).as_posix() if path.is_relative_to(REPO_ROOT) else path.as_posix()


def _component(kind: str, path: Path, exclude: tuple[str, ...] = ()) -> dict:
    sha = dir_sha256(path, exclude) if path.is_dir() else file_sha256(path)
    return {"kind": kind, "path": _rel(path), "sha256": sha}


def build_manifest(
    cases_dir: Path, settings: Settings, candidate_id: str | None = None, now: datetime | None = None
) -> dict:
    model_config = {
        "chat_model": settings.ollama_chat_model,
        "embed_model": settings.ollama_embed_model,
        "retrieval_max_distance": settings.retrieval_max_distance,
    }
    components = [
        _component("protocols", MEDICAL_DIR / "protocols"),
        _component("rules", MEDICAL_DIR, exclude=("prompts.py", "protocols")),
        _component("prompts", MEDICAL_DIR / "prompts.py"),
        _component("corpus", CORPUS_DIR),
        {"kind": "model_config", "path": "inline", "sha256": hashlib.sha256(canonical(model_config)).hexdigest(),
         "value": model_config},
        _component("cases", cases_dir),
    ]
    digest = hashlib.sha256(canonical(components)).hexdigest()
    now = now or datetime.now(UTC)
    return {
        "schema": "medical-eval.manifest.v1",
        "candidate_id": candidate_id or f"{now:%Y-%m-%d}.{digest[:8]}",
        "created_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "components": components,
        "digest": digest,
    }
