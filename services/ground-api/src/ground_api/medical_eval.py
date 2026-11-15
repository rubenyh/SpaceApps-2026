"""Clinician review and version-bound approval, contracts/medical-eval section 4 (issue #54)."""

import base64
import hashlib
import json
import uuid
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from ground_api import storage
from ground_api.telemetry import ClockDep, Connection

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
NonEmpty = Annotated[str, Field(min_length=1)]


class Loose(BaseModel):
    """Contract payloads: required fields are checked, everything else is kept verbatim."""

    model_config = ConfigDict(extra="allow")


class Component(Loose):
    kind: Literal[
        "protocols", "rules", "prompts", "corpus", "model_config", "mission_procedures", "equipment", "cases"
    ]
    path: str
    sha256: Digest


class Manifest(Loose):
    schema_: Literal["medical-eval.manifest.v1"] = Field(alias="schema")
    candidate_id: NonEmpty
    created_at: AwareDatetime
    components: list[Component]
    digest: Digest


class CandidateRef(Loose):
    candidate_id: str
    digest: Digest


class Summary(Loose):
    release_blocked: bool


class CaseResult(Loose):
    case_id: str
    family: str
    passed: bool
    blocking: bool = False
    case: dict[str, Any] | None = None  # the full section 1 case
    response: dict[str, Any] | None = None
    baseline_response: dict[str, Any] | None = None


class Result(Loose):
    schema_: Literal["medical-eval.result.v1"] = Field(alias="schema")
    manifest: CandidateRef
    baseline: CandidateRef | None = None
    run_at: AwareDatetime
    summary: Summary
    cases: list[CaseResult]


class CandidateIn(BaseModel):
    manifest: Manifest
    result: Result


class DecisionIn(BaseModel):
    decision: Literal["approved", "rejected"]
    reviewer: NonEmpty
    role: Literal["clinician", "simulated"]
    notes: str = ""


class FindingIn(BaseModel):
    case_id: NonEmpty
    kind: Literal["possible_cause", "warning_sign", "question", "action"]
    when_it_applies: NonEmpty
    source: NonEmpty
    expected_behavior: NonEmpty
    reporter: NonEmpty


def manifest_digest(components: list[dict]) -> str:
    canonical = json.dumps(components, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _dump(model: BaseModel) -> dict:
    return model.model_dump(mode="json", by_alias=True, exclude_unset=True)


def _label(decision: dict) -> str:
    if decision["role"] == "simulated":
        return f"Simulated {'approval' if decision['decision'] == 'approved' else 'rejection'} (no clinician)"
    return f"Clinician {'approval' if decision['decision'] == 'approved' else 'rejection'}"


def _require(conn: Connection, digest: str) -> dict:
    candidate = storage.get_candidate(conn, digest)
    if candidate is None:
        raise HTTPException(404, "Unknown candidate digest")
    return candidate


router = APIRouter(prefix="/medical-eval", tags=["medical-eval"])


@router.post("/candidates", status_code=201)
def submit_candidate(body: CandidateIn, conn: Connection, clock: ClockDep) -> dict:
    manifest, result = _dump(body.manifest), _dump(body.result)
    if result["manifest"]["digest"] != manifest["digest"]:
        raise HTTPException(422, "result.manifest.digest does not match manifest.digest")
    if manifest_digest(manifest["components"]) != manifest["digest"]:
        raise HTTPException(422, "manifest.digest is not the SHA-256 of the canonical components")
    if not storage.insert_candidate(conn, manifest, result, clock()):
        raise HTTPException(409, "Candidate already submitted; any change needs a new manifest digest")
    return {"candidate_id": manifest["candidate_id"], "digest": manifest["digest"], "status": "pending_review"}


@router.get("/candidates")
def list_candidates(conn: Connection) -> list[dict]:
    return [
        {k: c[k] for k in ("candidate_id", "digest", "status", "created_at")}
        | {"summary": c["result"]["summary"], "decision": next(iter(storage.list_decisions(conn, c["digest"])), None)}
        for c in storage.list_candidates(conn)
    ]


@router.get("/candidates/{digest}")
def get_candidate(digest: str, conn: Connection) -> dict:
    c = _require(conn, digest)
    return {
        "manifest": c["manifest"],
        "result": c["result"],
        "status": c["status"],
        "decisions": storage.list_decisions(conn, digest),
        "findings": storage.list_findings(conn, digest),
    }


@router.post("/candidates/{digest}/decisions", status_code=201)
def decide(digest: str, body: DecisionIn, conn: Connection, clock: ClockDep) -> dict:
    candidate = storage.get_candidate(conn, digest)
    if candidate is None:
        raise HTTPException(409, "Unknown candidate digest; submit the candidate first")
    if body.decision == "approved" and candidate["result"]["summary"]["release_blocked"]:
        raise HTTPException(409, "Release is blocked by a blocking failure; it cannot be approved")
    decision = storage.decide(conn, digest, body.decision, body.reviewer, body.role, body.notes, clock())
    if decision is None:
        raise HTTPException(409, "Candidate already decided; a change needs a new candidate")
    return decision


@router.post("/candidates/{digest}/findings", status_code=201)
def flag_missing_scenario(digest: str, body: FindingIn, conn: Connection, clock: ClockDep) -> dict:
    candidate = _require(conn, digest)
    if not any(case["case_id"] == body.case_id for case in candidate["result"]["cases"]):
        raise HTTPException(422, "case_id is not in this candidate's result")
    return storage.insert_finding(conn, {**body.model_dump(), "id": str(uuid.uuid4()), "digest": digest}, clock())


@router.get("/findings/{finding_id}/draft-case")
def draft_case(finding_id: str, conn: Connection) -> dict:
    finding = storage.get_finding(conn, finding_id)
    if finding is None:
        raise HTTPException(404, "Unknown finding")
    candidate = _require(conn, finding["digest"])
    case = next(c for c in candidate["result"]["cases"] if c["case_id"] == finding["case_id"])
    source_case = case.get("case") or {}
    expected = source_case.get("expected") or {
        "workflow": "medical",
        "urgency": (case.get("response") or {}).get("urgency"),
        "protocol_id": case["family"],
        "clarify": False,
    }
    return {
        "case_id": f"{case['case_id']}.flag-{finding_id[:8]}",
        "version": 1,
        "family": case["family"],
        "tags": source_case.get("tags", []),
        "turns": source_case.get("turns", []),
        "readings": source_case.get("readings", []),
        "events": source_case.get("events", []),
        "dependencies": source_case.get("dependencies", {"ollama": "up", "chroma": "up", "readings": "up"}),
        "expected": {
            **expected,
            "required_actions": list(dict.fromkeys([*expected.get("required_actions", []), finding["expected_behavior"]])),
            "prohibited_actions": expected.get("prohibited_actions", []),
            "acceptable_sources": list(dict.fromkeys([*expected.get("acceptable_sources", []), finding["source"]])),
        },
        "review": {
            "status": "draft",
            "reviewer": None,
            "reviewed_at": None,
            "notes": (
                f"Draft from finding {finding_id} ({finding['kind']}) by {finding['reporter']} on candidate "
                f"{candidate['candidate_id']} ({finding['digest']}), case {case['case_id']}. "
                f"Applies when: {finding['when_it_applies']}."
            ),
        },
    }


@router.get("/approved")
def approved(conn: Connection) -> dict:
    c = storage.latest_approved(conn)
    if c is None:
        raise HTTPException(404, "No approved candidate")
    return {"candidate_id": c["candidate_id"], "digest": c["digest"], "manifest": c["manifest"]}


def _component_files(root: Path, component: dict) -> dict[str, str]:
    """Files of one component as {posix path from root: base64}. Inline components have none."""
    if component["path"] == "inline":
        return {}
    target = (root / component["path"]).resolve()
    if not target.is_relative_to(root):
        raise HTTPException(409, f"Component path leaves the staging root: {component['path']}")
    files = [target] if target.is_file() else sorted(f for f in target.rglob("*") if f.is_file())
    if not files:
        raise HTTPException(409, f"Component not staged on ground: {component['path']}")
    return {f.relative_to(root).as_posix(): base64.b64encode(f.read_bytes()).decode("ascii") for f in files}


@router.get("/approved/bundle")
def approved_bundle(request: Request, conn: Connection) -> dict:
    """Staged bundle for onboard activation (section 5): the latest approved manifest plus
    the bytes of every component. Pending or rejected candidates are never served."""
    c = storage.latest_approved(conn)
    if c is None:
        raise HTTPException(404, "No approved candidate")
    root = request.app.state.settings.bundle_root.resolve()
    files: dict[str, str] = {}
    for component in c["manifest"]["components"]:
        files |= _component_files(root, component)
    return {"candidate_id": c["candidate_id"], "digest": c["digest"], "manifest": c["manifest"], "files": files}


def _entry(x: dict) -> dict:
    return {"kind": x["kind"], "path": x["path"], "sha256": x["sha256"]}


def build_packet(conn: Connection, digest: str) -> dict:
    c = _require(conn, digest)
    previous = storage.latest_approved(conn, before=digest)
    before = {(x["kind"], x["path"]): x for x in previous["manifest"]["components"]} if previous else {}
    after = {(x["kind"], x["path"]): x for x in c["manifest"]["components"]}
    changed_components = {
        "added": [_entry(after[k]) for k in after if k not in before],
        "removed": [_entry(before[k]) for k in before if k not in after],
        "changed": [
            {"kind": k[0], "path": k[1], "before": before[k]["sha256"], "after": after[k]["sha256"]}
            for k in after
            if k in before and before[k]["sha256"] != after[k]["sha256"]
        ],
    }
    # Component hashes are per directory, so families come from case behaviour: a family is
    # affected when any of its cases failed or answered differently from the baseline.
    cases = [
        {**case, "changed": case.get("response") != case.get("baseline_response")}
        for case in c["result"]["cases"]
    ]
    families = sorted({case["family"] for case in cases if case["changed"] or not case["passed"]})
    return {
        "candidate_id": c["candidate_id"],
        "digest": digest,
        "status": c["status"],
        "created_at": c["created_at"],
        "previous_approved": {"candidate_id": previous["candidate_id"], "digest": previous["digest"]}
        if previous else None,
        "baseline": c["result"].get("baseline"),
        "summary": c["result"]["summary"],
        "changed_components": changed_components,
        "affected_families": families,
        "cases": [case for case in cases if case["family"] in families],
        "decisions": storage.list_decisions(conn, digest),
        "findings": storage.list_findings(conn, digest),
    }


def _md_response(title: str, r: dict | None) -> list[str]:
    if r is None:
        return [f"- **{title}:** none"]
    sources = ", ".join(  # GuideSource {"id", "title", "section", "url", "kind"}
        f"{s.get('title') or s.get('id')}" + (f" ({s['section']})" if s.get("section") else "")
        for s in r.get("sources") or []
    )
    return [
        f"- **{title}:** urgency `{r.get('urgency')}`, protocol `{r.get('protocol_id')}`",
        f"  - Action: {r.get('action') or '-'}",
        f"  - Reply: {r.get('reply') or '-'}",
        f"  - Sources: {sources or '-'}",
    ]


def packet_markdown(p: dict) -> str:
    s = p["summary"]
    prev = p["previous_approved"]
    prev_text = f"{prev['candidate_id']} (`{prev['digest']}`)" if prev else "none"
    lines = [
        f"# Medical evaluation review packet: {p['candidate_id']}",
        "",
        f"- Digest: `{p['digest']}`",
        f"- Status: {p['status']}",
        f"- Previous approved: {prev_text}",
        "",
        "## Automated results",
        "",
        "| Metric | Value |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in s.items()],
        "",
    ]
    if s.get("release_blocked"):
        lines += ["**Release blocked:** a blocking failure means this candidate cannot be approved.", ""]
    lines += ["## Changed components", ""]
    cc = p["changed_components"]
    lines += [f"- Added {x['kind']}: `{x['path']}`" for x in cc["added"]]
    lines += [f"- Removed {x['kind']}: `{x['path']}`" for x in cc["removed"]]
    lines += [f"- Changed {x['kind']}: `{x['path']}`" for x in cc["changed"]]
    if not any(cc.values()):
        lines.append("- None")
    lines += ["", "## Affected protocol families", ""]
    lines += [f"- {f}" for f in p["affected_families"]] or ["- None"]
    lines += ["", "## Cases", ""]
    for case in p["cases"]:
        verdict = "passed" if case["passed"] else ("FAILED (blocking)" if case.get("blocking") else "failed")
        lines += [f"### {case['case_id']} ({case['family']}): {verdict}", ""]
        lines += [f"- Failure `{f.get('code')}`: {f.get('detail', '')}" for f in case.get("failures") or []]
        expected = (case.get("case") or {}).get("expected")
        if expected:
            lines += [
                f"- **Expected:** urgency `{expected.get('urgency')}`, protocol `{expected.get('protocol_id')}`",
                f"  - Required actions: {'; '.join(expected.get('required_actions') or []) or '-'}",
                f"  - Prohibited actions: {'; '.join(expected.get('prohibited_actions') or []) or '-'}",
            ]
        lines += _md_response("Candidate", case.get("response"))
        lines += _md_response("Baseline", case.get("baseline_response"))
        lines.append("")
    lines += ["## Decisions", ""]
    lines += [
        f"- {_label(d)}: {d['decision']} by {d['reviewer']} at {d['decided_at'].isoformat()}. {d['notes']}"
        for d in p["decisions"]
    ] or ["- Pending review"]
    lines += ["", "## Flagged missing scenarios", ""]
    lines += [
        f"- {f['case_id']} [{f['kind']}] {f['expected_behavior']} (when: {f['when_it_applies']}; source: {f['source']})"
        for f in p["findings"]
    ] or ["- None"]
    return "\n".join(lines) + "\n"


@router.get("/candidates/{digest}/packet", response_model=None)
def packet(
    digest: str, conn: Connection, format: Annotated[Literal["json", "md"], Query()] = "json"
) -> dict | PlainTextResponse:
    p = build_packet(conn, digest)
    if format == "md":
        return PlainTextResponse(packet_markdown(p), media_type="text/markdown; charset=utf-8")
    return p
