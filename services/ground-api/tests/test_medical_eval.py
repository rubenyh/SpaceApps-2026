import copy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ground_api.config import Settings
from ground_api.main import create_app
from ground_api.medical_eval import manifest_digest

PROTOCOLS = "services/onboard-api/src/onboard_api/assistant/workflows/medical/protocols"
RULES = "services/onboard-api/src/onboard_api/assistant/workflows/medical/interpret.py"


@pytest.fixture
def client(tmp_path: Path):
    with TestClient(create_app(Settings(db_path=tmp_path / "ground.db"))) as c:
        yield c


def response(urgency: str, action: str) -> dict:
    return {"workflow": "medical", "urgency": urgency, "protocol_id": "dizziness_or_space_motion_sickness",
            "reply": "Sit down.", "action": action, "sources": [{"id": "medlineplus-dizziness"}]}


def candidate(candidate_id: str, rules_sha: str = "b" * 64, blocked: bool = False,
              changed_answer: bool = False) -> dict:
    components = [
        {"kind": "protocols", "path": PROTOCOLS, "sha256": "a" * 64},
        {"kind": "rules", "path": RULES, "sha256": rules_sha},
        {"kind": "model_config", "path": "inline", "sha256": "c" * 64, "value": {"chat_model": "qwen2.5:3b"}},
    ]
    digest = manifest_digest(components)
    same = response("review_required", "Sit or lie down.")
    cases = [
        {"case_id": "dizziness.typo.001", "family": "dizziness_or_space_motion_sickness",
         "review_status": "draft", "passed": not blocked, "blocking": blocked,
         "failures": [{"code": "missed_alarm", "detail": "expected immediate"}] if blocked else [],
         "latency_ms": 35,
         "response": response("immediate", "Call the CMO now.") if changed_answer else same,
         "baseline_response": same},
        {"case_id": "headache.plain.001", "family": "headache", "review_status": "draft", "passed": True,
         "blocking": False, "failures": [], "latency_ms": 20, "response": same, "baseline_response": same},
    ]
    return {
        "manifest": {"schema": "medical-eval.manifest.v1", "candidate_id": candidate_id,
                     "created_at": "2026-11-15T10:00:00Z", "components": components, "digest": digest},
        "result": {"schema": "medical-eval.result.v1", "manifest": {"candidate_id": candidate_id, "digest": digest},
                   "baseline": None, "run_at": "2026-11-15T10:05:00Z",
                   "summary": {"cases": 2, "passed": 2 - blocked, "failed": int(blocked),
                               "blocking_failures": int(blocked), "release_blocked": blocked},
                   "cases": cases},
    }


def submit(client: TestClient, body: dict) -> str:
    r = client.post("/medical-eval/candidates", json=body)
    assert r.status_code == 201, r.text
    assert r.json() == {"candidate_id": body["manifest"]["candidate_id"],
                        "digest": body["manifest"]["digest"], "status": "pending_review"}
    return r.json()["digest"]


def decide(client: TestClient, digest: str, decision: str = "approved", role: str = "clinician"):
    return client.post(f"/medical-eval/candidates/{digest}/decisions",
                       json={"decision": decision, "reviewer": "Dr. Vega", "role": role, "notes": "ok"})


def test_submit_rejects_mismatched_or_forged_digest(client: TestClient) -> None:
    body = candidate("c1")
    bad = copy.deepcopy(body)
    bad["result"]["manifest"]["digest"] = "f" * 64
    assert client.post("/medical-eval/candidates", json=bad).status_code == 422
    forged = copy.deepcopy(body)
    forged["manifest"]["components"][1]["sha256"] = "e" * 64  # component changed, digest not recomputed
    forged["result"]["manifest"]["digest"] = forged["manifest"]["digest"]
    assert client.post("/medical-eval/candidates", json=forged).status_code == 422
    submit(client, body)
    assert client.post("/medical-eval/candidates", json=body).status_code == 409


def test_list_and_detail(client: TestClient) -> None:
    body = candidate("c1")
    digest = submit(client, body)
    assert client.get("/medical-eval/candidates").json() == [{
        "candidate_id": "c1", "digest": digest, "status": "pending_review",
        "created_at": "2026-11-15T10:00:00Z", "summary": body["result"]["summary"]}]
    detail = client.get(f"/medical-eval/candidates/{digest}").json()
    assert detail["manifest"] == body["manifest"]
    assert detail["result"] == body["result"]
    assert (detail["status"], detail["decisions"], detail["findings"]) == ("pending_review", [], [])
    assert client.get(f"/medical-eval/candidates/{'0' * 64}").status_code == 404


def test_decision_binds_to_digest_once(client: TestClient) -> None:
    assert decide(client, "0" * 64).status_code == 409
    assert client.get("/medical-eval/approved").status_code == 404
    digest = submit(client, candidate("c1"))
    r = decide(client, digest, role="simulated")
    assert r.status_code == 201
    assert r.json()["label"] == "Simulated approval (no clinician)"
    assert {k: r.json()[k] for k in ("digest", "decision", "reviewer", "role", "notes")} == {
        "digest": digest, "decision": "approved", "reviewer": "Dr. Vega", "role": "simulated", "notes": "ok"}
    assert r.json()["decided_at"]
    assert decide(client, digest, "rejected").status_code == 409
    detail = client.get(f"/medical-eval/candidates/{digest}").json()
    assert detail["status"] == "approved" and len(detail["decisions"]) == 1
    approved = client.get("/medical-eval/approved").json()
    assert (approved["candidate_id"], approved["digest"]) == ("c1", digest)

    # Any change gives a new digest that needs its own review; the old approval stays the latest.
    d2 = submit(client, candidate("c2", rules_sha="d" * 64))
    assert d2 != digest
    assert client.get("/medical-eval/approved").json()["digest"] == digest
    assert decide(client, d2, "rejected").json()["label"] == "Clinician rejection"
    assert client.get("/medical-eval/approved").json()["digest"] == digest


def test_approval_refused_while_release_blocked(client: TestClient) -> None:
    digest = submit(client, candidate("c1", blocked=True))
    assert decide(client, digest).status_code == 409
    assert client.get(f"/medical-eval/candidates/{digest}").json()["status"] == "pending_review"
    assert decide(client, digest, "rejected").status_code == 201


def test_packet_diffs_against_previous_approved(client: TestClient) -> None:
    first = submit(client, candidate("c1"))
    first_packet = client.get(f"/medical-eval/candidates/{first}/packet").json()
    assert first_packet["previous_approved"] is None
    assert len(first_packet["changed_components"]["added"]) == 3
    decide(client, first)

    second = submit(client, candidate("c2", rules_sha="d" * 64, changed_answer=True))
    p = client.get(f"/medical-eval/candidates/{second}/packet").json()
    assert p["previous_approved"] == {"candidate_id": "c1", "digest": first}
    assert p["changed_components"] == {
        "added": [], "removed": [],
        "changed": [{"kind": "rules", "path": RULES, "before": "b" * 64, "after": "d" * 64}]}
    assert p["affected_families"] == ["dizziness_or_space_motion_sickness"]
    [case] = p["cases"]
    assert case["changed"] and case["response"]["urgency"] == "immediate"
    assert case["baseline_response"]["urgency"] == "review_required"

    md = client.get(f"/medical-eval/candidates/{second}/packet", params={"format": "md"})
    assert md.headers["content-type"].startswith("text/markdown")
    assert "# Medical evaluation review packet: c2" in md.text
    assert f"Previous approved: c1 (`{first}`)" in md.text
    assert "Changed rules" in md.text and "Call the CMO now." in md.text
    assert client.get(f"/medical-eval/candidates/{'0' * 64}/packet").status_code == 404


def test_finding_and_draft_case(client: TestClient) -> None:
    digest = submit(client, candidate("c1"))
    finding = {"case_id": "dizziness.typo.001", "kind": "warning_sign",
               "when_it_applies": "dizziness with chest pain", "source": "medlineplus-dizziness",
               "expected_behavior": "escalate to immediate", "reporter": "Dr. Vega"}
    assert client.post(f"/medical-eval/candidates/{'0' * 64}/findings", json=finding).status_code == 404
    assert client.post(f"/medical-eval/candidates/{digest}/findings",
                       json={**finding, "case_id": "nope"}).status_code == 422
    r = client.post(f"/medical-eval/candidates/{digest}/findings", json=finding)
    assert r.status_code == 201
    stored = r.json()
    assert {k: stored[k] for k in finding} == finding
    assert (stored["digest"], stored["status"]) == (digest, "open")
    assert stored["id"] and stored["created_at"]
    assert client.get(f"/medical-eval/candidates/{digest}").json()["findings"] == [stored]

    draft = client.get(f"/medical-eval/findings/{stored['id']}/draft-case").json()
    assert draft["family"] == "dizziness_or_space_motion_sickness"
    assert draft["case_id"].startswith("dizziness.typo.001.flag-")
    assert draft["expected"]["required_actions"] == ["escalate to immediate"]
    assert draft["expected"]["acceptable_sources"] == ["medlineplus-dizziness"]
    assert draft["review"]["status"] == "draft" and draft["review"]["reviewer"] is None
    assert stored["id"] in draft["review"]["notes"] and digest in draft["review"]["notes"]
    assert client.get("/medical-eval/findings/missing/draft-case").status_code == 404
