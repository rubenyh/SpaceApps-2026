"""Onboard knowledge gate, contracts/medical-eval section 5 (issue #55).

Ground stages the approved bundle (manifest + component files). Onboard activates it only
when the manifest digest is the canonical digest of its components, equals the digest
ground approved, and every component sha256 verifies. Any failure leaves `active` as is.

Layout under Settings.knowledge_dir: active/ and previous/ (manifest.json, index.json,
files/<short key>), .stage/ while writing,
last_sync.json. Ordinary telemetry does not go through here.

CLI (from services/onboard-api): uv run python -m onboard_api.knowledge sync|rollback|active
"""

import base64
import hashlib
import json
import shutil
import sys
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException

from onboard_api.config import Settings
from onboard_api.dependencies import get_settings
from onboard_api.schemas.assistant import KnowledgeVersion

MANIFEST = "manifest.json"
LAST_SYNC = "last_sync.json"
INDEX = "index.json"


class GateError(Exception):
    """The bundle is not activated; the message is the recorded reason."""


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def file_sha(data: bytes) -> str:
    """Section 2: CRLF -> LF first, so Windows and LF checkouts of one commit agree."""
    return _sha(data.replace(b"\r\n", b"\n"))


def _excluded(kind: str, rel: str) -> bool:
    """Section 2 directory exclusions: __pycache__/ and *.pyc everywhere; the rules
    directory also leaves out prompts.py and protocols/ (their own components)."""
    if "__pycache__" in rel.split("/") or rel.endswith(".pyc"):
        return True
    return kind == "rules" and (rel == "prompts.py" or rel.startswith("protocols/"))


def component_sha(component: dict, files: dict[str, bytes]) -> str:
    """Section 2: a file hashes its LF-normalised bytes; a directory hashes the sorted lines
    "<relative posix path>\\t<file sha256>\\n". Inline components (no files) hash the
    canonical JSON of `value` (same as the #53 runner; the contract does not say)."""
    path, kind = component["path"], component["kind"]
    if path == "inline":
        return _sha(_canonical(component.get("value")))
    if path in files:
        return file_sha(files[path])
    prefix = path + "/"
    lines = sorted(
        f"{rel}\t{file_sha(v)}\n"
        for k, v in files.items()
        if k.startswith(prefix) and not _excluded(kind, rel := k[len(prefix):])
    )
    if not lines:
        raise GateError(f"component {path} is missing from the bundle")
    return _sha("".join(lines).encode("utf-8"))


def _safe(path: str) -> bool:
    p = PurePosixPath(path)
    return bool(path) and not p.is_absolute() and ":" not in path and ".." not in p.parts


def verify(bundle: dict, approved_digest: str) -> tuple[dict, dict[str, bytes]]:
    """Return (manifest, files) only for the exact approved bundle, else raise GateError."""
    manifest = bundle["manifest"]
    if manifest.get("schema") != "medical-eval.manifest.v1":
        raise GateError(f"unknown manifest schema {manifest.get('schema')!r}")
    components = manifest["components"]
    if _sha(_canonical(components)) != manifest["digest"]:
        raise GateError("manifest digest is not the SHA-256 of its components")
    if manifest["digest"] != approved_digest:
        raise GateError(f"bundle digest {manifest['digest']} is not the approved digest {approved_digest}")
    files = {path: base64.b64decode(data, validate=True) for path, data in bundle["files"].items()}
    def hashed(path: str, c: dict) -> bool:  # the file's bytes count in c's sha256
        root = c["path"]
        return path == root or (path.startswith(root + "/") and not _excluded(c["kind"], path[len(root) + 1:]))

    for path in files:  # every byte written to disk is covered by a verified hash
        if not _safe(path) or not any(hashed(path, c) for c in components if c["path"] != "inline"):
            raise GateError(f"file {path} is not part of any component")
    for c in components:
        if component_sha(c, files) != c["sha256"]:
            raise GateError(f"sha256 mismatch for {c['kind']} component {c['path']}")
    return manifest, files


def _write_bundle(target: Path, manifest: dict, files: dict[str, bytes]) -> None:
    """Files are stored flat as files/<16 hex of their raw sha256>, with index.json mapping
    repo path -> key, so deep repo paths never hit the Windows 260-character limit."""
    (target / "files").mkdir(parents=True)
    index = {}
    for path, data in files.items():
        index[path] = key = _sha(data)[:16]
        (target / "files" / key).write_bytes(data)
    (target / INDEX).write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")
    (target / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def bundle_file(bundle_dir: Path, path: str) -> Path:
    """On-disk location of a component file (repo posix path) inside active/ or previous/."""
    return bundle_dir / "files" / json.loads((bundle_dir / INDEX).read_text(encoding="utf-8"))[path]


def _activate(root: Path, manifest: dict, files: dict[str, bytes]) -> None:
    staging, active, previous = root / ".stage", root / "active", root / "previous"
    if staging.exists():  # left over from an interrupted sync
        shutil.rmtree(staging)
    try:
        _write_bundle(staging, manifest, files)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    # ponytail: two renames, not one atomic swap; a crash between them leaves only
    # previous/. Use a symlink flip if that window ever matters.
    if active.exists():
        if previous.exists():
            shutil.rmtree(previous)
        active.rename(previous)
    try:
        staging.rename(active)
    except BaseException:
        if previous.exists() and not active.exists():
            previous.rename(active)  # put the old active back
        raise


def _version(bundle_dir: Path) -> dict | None:
    try:
        m = json.loads((bundle_dir / MANIFEST).read_text(encoding="utf-8"))
        return {"candidate_id": m["candidate_id"], "digest": m["digest"]}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def active_version(root: Path) -> KnowledgeVersion | None:
    v = _version(root / "active")
    return KnowledgeVersion(**v) if v else None


def state(root: Path) -> dict:
    try:
        last = json.loads((root / LAST_SYNC).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        last = None
    return {"active": _version(root / "active"), "previous": _version(root / "previous"), "last_sync": last}


def sync(root: Path, ground: httpx.Client) -> dict:
    """Pull the approved bundle from ground and activate it if it verifies."""
    record: dict = {"at": datetime.now(UTC).isoformat(), "ok": False, "outcome": None, "error": None, "digest": None}
    try:
        root.mkdir(parents=True, exist_ok=True)
        r = ground.get("/medical-eval/approved")
        if r.status_code == 404:
            raise GateError("ground has no approved candidate")
        r.raise_for_status()
        approved = r.json()["digest"]
        record["digest"] = approved
        b = ground.get("/medical-eval/approved/bundle")
        b.raise_for_status()
        manifest, files = verify(b.json(), approved)
        if (_version(root / "active") or {}).get("digest") == approved:
            record["outcome"] = "already_active"
        else:
            _activate(root, manifest, files)
            record["outcome"] = "activated"
        record["ok"] = True
    except Exception as exc:  # any failure (link, verification, disk) leaves active as is
        record["error"] = f"{type(exc).__name__}: {exc}"
    try:
        (root / LAST_SYNC).write_text(json.dumps(record), encoding="utf-8")
    except OSError as exc:
        record["error"] = f"{record['error'] or ''} (last_sync not saved: {exc})".lstrip()
    return {**state(root), "last_sync": record}


def rollback(root: Path) -> dict:
    """Swap active and previous (a second rollback rolls forward again)."""
    active, previous, tmp = root / "active", root / "previous", root / ".rb"
    if not previous.exists():
        raise GateError("no previous bundle to roll back to")
    if active.exists():
        active.rename(tmp)
    previous.rename(active)
    if tmp.exists():
        tmp.rename(previous)
    return state(root)


def get_ground_client(settings: Annotated[Settings, Depends(get_settings)]) -> Iterator[httpx.Client]:
    with httpx.Client(base_url=settings.ground_api_url, timeout=10.0) as client:
        yield client


SettingsDep = Annotated[Settings, Depends(get_settings)]
router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("/active")
def get_active(settings: SettingsDep) -> dict:
    return state(settings.knowledge_dir)


@router.post("/sync")
def post_sync(settings: SettingsDep, ground: Annotated[httpx.Client, Depends(get_ground_client)]) -> dict:
    """200 with the store state; `last_sync.ok` false means active was left unchanged."""
    return sync(settings.knowledge_dir, ground)


@router.post("/rollback")
def post_rollback(settings: SettingsDep) -> dict:
    try:
        return rollback(settings.knowledge_dir)
    except GateError as exc:
        raise HTTPException(409, str(exc)) from exc
    except OSError as exc:
        raise HTTPException(500, f"rollback failed: {exc}") from exc


def main(argv: list[str]) -> int:
    command = argv[0] if argv else "active"
    settings = Settings()
    if command == "sync":
        with httpx.Client(base_url=settings.ground_api_url, timeout=10.0) as ground:
            result = sync(settings.knowledge_dir, ground)
        print(json.dumps(result, indent=2))
        return 0 if result["last_sync"]["ok"] else 1
    if command == "rollback":
        try:
            print(json.dumps(rollback(settings.knowledge_dir), indent=2))
        except (GateError, OSError) as exc:
            print(exc, file=sys.stderr)
            return 1
        return 0
    if command == "active":
        print(json.dumps(state(settings.knowledge_dir), indent=2))
        return 0
    print("usage: python -m onboard_api.knowledge sync|rollback|active", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
