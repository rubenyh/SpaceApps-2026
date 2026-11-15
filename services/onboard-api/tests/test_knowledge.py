"""Onboard knowledge gate (issue #55, contracts/medical-eval section 5). Ground is faked
with httpx.MockTransport; no network."""

import base64
import copy
import hashlib
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from onboard_api import knowledge
from onboard_api.config import Settings
from onboard_api.dependencies import get_assistant_responder
from onboard_api.main import create_app
from onboard_api.schemas.assistant import AssistantResponse, CaseReport

PROTOCOLS = "services/onboard-api/src/onboard_api/assistant/workflows/medical/protocols"
RULES = "services/onboard-api/src/onboard_api/assistant/workflows/medical/interpret.py"


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def bundle(candidate_id: str, rules: bytes) -> dict:
    """A ground bundle built the section 2 way: directory, file and inline components."""
    protocols = {"headache.json": b'{"id": "headache"}', "sub/fever.json": b'{"id": "fever"}'}
    dir_sha = sha("".join(sorted(f"{k}\t{sha(v)}\n" for k, v in protocols.items())).encode())
    value = {"chat_model": "qwen2.5:3b", "embed_model": "bge-m3"}
    components = [
        {"kind": "protocols", "path": PROTOCOLS, "sha256": dir_sha},
        {"kind": "rules", "path": RULES, "sha256": sha(rules)},
        {"kind": "model_config", "path": "inline", "value": value,
         "sha256": sha(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())},
    ]
    digest = sha(json.dumps(components, sort_keys=True, separators=(",", ":")).encode())
    files = {f"{PROTOCOLS}/{k}": v for k, v in protocols.items()} | {RULES: rules}
    manifest = {"schema": "medical-eval.manifest.v1", "candidate_id": candidate_id,
                "created_at": "2026-11-15T10:00:00Z", "components": components, "digest": digest}
    return {"candidate_id": candidate_id, "digest": digest, "manifest": manifest,
            "files": {k: base64.b64encode(v).decode() for k, v in files.items()}}


class Ground:
    """Fake ground: /approved returns `approved` (None = 404); the bundle route serves `served`."""

    def __init__(self, approved: dict | None, served: dict | None = None) -> None:
        self.approved, self.served = approved, served if served is not None else approved

    def client(self) -> httpx.Client:
        def handle(request: httpx.Request) -> httpx.Response:
            if self.approved is None:
                return httpx.Response(404, json={"detail": "No approved candidate"})
            if request.url.path == "/medical-eval/approved":
                return httpx.Response(200, json={k: self.approved[k] for k in ("candidate_id", "digest", "manifest")})
            if request.url.path == "/medical-eval/approved/bundle":
                return httpx.Response(200, json=self.served)
            return httpx.Response(404)

        return httpx.Client(base_url="http://ground", transport=httpx.MockTransport(handle))


def down() -> httpx.Client:
    def handle(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("link down", request=request)

    return httpx.Client(base_url="http://ground", transport=httpx.MockTransport(handle))


V1, V2 = bundle("c1", b"RULES = 1\n"), bundle("c2", b"RULES = 2\n")


@pytest.fixture
def store(tmp_path: Path) -> Path:
    root = tmp_path / "knowledge"
    assert knowledge.sync(root, Ground(V1).client())["last_sync"]["ok"]
    return root


def test_verify_and_activate(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    s = knowledge.sync(root, Ground(V1).client())
    assert s["active"] == {"candidate_id": "c1", "digest": V1["digest"]} and s["previous"] is None
    assert s["last_sync"]["outcome"] == "activated"
    assert (root / "active" / "files" / RULES).read_bytes() == b"RULES = 1\n"
    assert (root / "active" / "files" / PROTOCOLS / "sub" / "fever.json").exists()
    assert knowledge.sync(root, Ground(V1).client())["last_sync"]["outcome"] == "already_active"
    s = knowledge.sync(root, Ground(V2).client())
    assert (s["active"]["candidate_id"], s["previous"]["candidate_id"]) == ("c2", "c1")
    assert not [p for p in root.iterdir() if p.name.startswith(".")]  # no staging left behind


def failed(root: Path, ground: httpx.Client) -> str:
    s = knowledge.sync(root, ground)
    assert s["last_sync"]["ok"] is False and s["active"]["candidate_id"] == "c1"
    assert (root / "active" / "files" / RULES).read_bytes() == b"RULES = 1\n"
    return s["last_sync"]["error"]


def test_sha_mismatch_keeps_active(store: Path) -> None:
    tampered = copy.deepcopy(V2)
    tampered["files"][RULES] = base64.b64encode(b"RULES = 666\n").decode()
    assert "sha256 mismatch for rules" in failed(store, Ground(V2, tampered).client())
    tampered = copy.deepcopy(V2)
    tampered["files"][f"{PROTOCOLS}/extra.json"] = base64.b64encode(b"{}").decode()
    assert "sha256 mismatch for protocols" in failed(store, Ground(V2, tampered).client())
    tampered = copy.deepcopy(V2)
    tampered["files"]["../../evil.py"] = base64.b64encode(b"x").decode()
    assert "not part of any component" in failed(store, Ground(V2, tampered).client())


def test_digest_mismatch_keeps_active(store: Path) -> None:
    forged = copy.deepcopy(V2)
    forged["manifest"]["components"][1]["sha256"] = "0" * 64  # digest no longer canonical
    assert "not the SHA-256 of its components" in failed(store, Ground(V2, forged).client())


def test_ground_unreachable_keeps_active(store: Path) -> None:
    assert "ConnectError" in failed(store, down())


def test_rejected_candidate_never_activated(store: Path) -> None:
    rejected = bundle("c-rejected", b"RULES = bad\n")
    # Ground has nothing newer approved, or serves a candidate whose digest is not the approved one.
    assert "no approved candidate" in failed(store, Ground(None).client())
    assert "is not the approved digest" in failed(store, Ground(V1, rejected).client())


def test_rollback_swaps_active_and_previous(store: Path, tmp_path: Path) -> None:
    with pytest.raises(knowledge.GateError):
        knowledge.rollback(tmp_path / "empty")
    knowledge.sync(store, Ground(V2).client())
    s = knowledge.rollback(store)
    assert (s["active"]["candidate_id"], s["previous"]["candidate_id"]) == ("c1", "c2")
    assert (store / "active" / "files" / RULES).read_bytes() == b"RULES = 1\n"


def test_routes_and_report_knowledge_version(tmp_path: Path) -> None:
    root = tmp_path / "knowledge"
    app = create_app(Settings(db_path=tmp_path / "onboard.db", telemetry_enabled=False, knowledge_dir=root))
    app.dependency_overrides[knowledge.get_ground_client] = lambda: Ground(V1).client()
    app.dependency_overrides[get_assistant_responder] = lambda: lambda request: AssistantResponse(
        reply="ok", workflow="medical", needs_clarification=False, report=CaseReport(text="REPORT"))
    with TestClient(app) as client:
        ask = lambda: client.post("/assistant/messages", json={"message": "headache"}).json()["report"]  # noqa: E731
        assert ask()["knowledge_version"] is None
        assert client.post("/knowledge/rollback").status_code == 409
        assert client.post("/knowledge/sync").json()["active"]["candidate_id"] == "c1"
        assert client.get("/knowledge/active").json()["active"] == {"candidate_id": "c1", "digest": V1["digest"]}
        report = ask()
    assert report["knowledge_version"] == {"candidate_id": "c1", "digest": V1["digest"]}
    assert f"c1 (digest {V1['digest']})" in report["text"]
