"""Medical eval runner (contracts/medical-eval sections 2 and 3). Fakes only: no Ollama, no Chroma."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from assistant.fakes import FakeLLM, FakeRetriever, chunk
from onboard_api.assistant.eval.__main__ import main
from onboard_api.assistant.eval.manifest import REPO_ROOT, build_manifest, canonical, dir_sha256
from onboard_api.assistant.eval.runner import Up
from onboard_api.assistant.ingest.evaluate import CASES, check_retrieval, hit_rate
from onboard_api.config import Settings

FIXTURES = Path(__file__).parent / "eval_fixtures"
CONTRACT = REPO_ROOT / "contracts" / "medical-eval"


def fake_up(**kw) -> Up:
    return Up(FakeLLM("Draft based on the local guide [1]."), FakeRetriever([chunk(1)]), 0.9, **kw)


def evaluate(tmp_path: Path, cases: Path = FIXTURES, *extra: str, up: Up | None = None, out: str = "out"):
    code = main(["--cases", str(cases), "--out", str(tmp_path / out), *extra], up_factory=lambda s: up or fake_up())
    read = lambda name: json.loads((tmp_path / out / name).read_text(encoding="utf-8"))  # noqa: E731
    return code, read("manifest.json"), read("result.json"), (tmp_path / out / "report.md").read_text(encoding="utf-8")


def copy_fixtures(tmp_path: Path, edit=None) -> Path:
    """Fixtures copied to tmp; edit(case) may change each case in place."""
    cases = tmp_path / "cases"
    shutil.copytree(FIXTURES, cases)
    for path in cases.rglob("*.json"):
        case = json.loads(path.read_text(encoding="utf-8"))
        edit and edit(case)
        path.write_text(json.dumps(case), encoding="utf-8")
    return cases


def by_id(result: dict) -> dict:
    return {c["case_id"]: c for c in result["cases"]}


def codes(case_result: dict) -> set[str]:
    return {f["code"] for f in case_result["failures"]}


def test_fixtures_pass_and_match_contract(tmp_path: Path) -> None:
    code, manifest, result, report = evaluate(tmp_path)
    assert code == 0
    s = result["summary"]
    assert (s["cases"], s["passed"], s["blocking_failures"], s["release_blocked"]) == (3, 3, 0, False)
    assert s["retrieval_hit_rate"] == 0.9 and s["citation_support_rate"] == 1.0
    assert 0 <= s["latency_ms_p50"] <= s["latency_ms_p95"]
    assert result["manifest"] == {"candidate_id": manifest["candidate_id"], "digest": manifest["digest"]}
    assert result["baseline"] is None
    for c in result["cases"]:
        assert c["case"]["case_id"] == c["case_id"] and c["baseline_response"] is None
        assert all(set(s) == {"id", "title", "section", "url", "kind"} for s in c["response"]["sources"])
    cases = by_id(result)
    # Follow-up turn carried the clarification and reached the alarm.
    assert cases["breathing.follow_up.001"]["response"]["urgency"] == "immediate"
    # Ollama, Chroma and readings down: offline answer still follows the card.
    offline = cases["fever.dependency_down.001"]["response"]
    assert offline["protocol_id"] == "fever_or_respiratory_illness"
    assert all(s["kind"] == "protocol" for s in offline["sources"])
    assert "No blocking failures." in report and "| chest_pain.alarm.001 |" in report

    jsonschema = pytest.importorskip("jsonschema")
    for name, doc in (("manifest", manifest), ("result", result)):
        schema = json.loads((CONTRACT / f"{name}.schema.json").read_text(encoding="utf-8"))
        jsonschema.validate(doc, schema)


def test_manifest_digest_follows_contract(tmp_path: Path) -> None:
    m = build_manifest(FIXTURES, Settings())
    assert m["digest"] == hashlib.sha256(canonical(m["components"])).hexdigest()
    assert [c["kind"] for c in m["components"]] == [
        "protocols", "rules", "prompts", "corpus", "model_config", "cases"]
    rules = next(c for c in m["components"] if c["kind"] == "rules")
    assert rules["path"] == "services/onboard-api/src/onboard_api/assistant/workflows/medical"
    model = next(c for c in m["components"] if c["kind"] == "model_config")
    assert model["path"] == "inline" and model["value"]["chat_model"] == Settings().ollama_chat_model
    # Directory hash = sha256 of sorted "<rel path>\t<file sha>\n" lines; file sha over
    # CRLF -> LF bytes; __pycache__/, *.pyc and excluded top-level entries skipped.
    d = tmp_path / "d"
    (d / "b").mkdir(parents=True)
    (d / "__pycache__").mkdir()
    (d / "a.txt").write_bytes(b"x\r\n")
    (d / "b" / "c.txt").write_bytes(b"y\n")
    (d / "b" / "c.pyc").write_bytes(b"skipped")
    (d / "__pycache__" / "m.py").write_bytes(b"skipped")
    (d / "prompts.py").write_bytes(b"excluded")
    sx, sy = hashlib.sha256(b"x\n").hexdigest(), hashlib.sha256(b"y\n").hexdigest()
    expected = hashlib.sha256(f"a.txt\t{sx}\nb/c.txt\t{sy}\n".encode()).hexdigest()
    assert dir_sha256(d, exclude=("prompts.py",)) == expected
    (d / "a.txt").write_bytes(b"x\n")  # LF checkout of the same file
    assert dir_sha256(d, exclude=("prompts.py",)) == expected
    # Any case change changes the digest.
    edited = copy_fixtures(tmp_path, lambda c: c["review"].update(notes="changed"))
    assert build_manifest(edited, Settings())["digest"] != build_manifest(copy_fixtures(tmp_path / "x"), Settings())["digest"]


def test_missed_alarm_and_unsafe_action_block_release(tmp_path: Path) -> None:
    def edit(case):
        if case["case_id"] == "fever.dependency_down.001":
            case["expected"]["urgency"] = "immediate"  # the runner sees review_required
        if case["case_id"] == "chest_pain.alarm.001":
            case["expected"]["prohibited_actions"] = ["call for help"]  # present in the action

    code, _, result, report = evaluate(tmp_path, copy_fixtures(tmp_path, edit))
    assert code == 1
    cases = by_id(result)
    assert codes(cases["fever.dependency_down.001"]) == {"missed_alarm"}
    assert codes(cases["chest_pain.alarm.001"]) == {"unsafe_action"}
    assert all(cases[i]["blocking"] for i in ("fever.dependency_down.001", "chest_pain.alarm.001"))
    s = result["summary"]
    assert s["blocking_failures"] == 2 and s["release_blocked"] and s["failed"] == 2
    assert "RELEASE BLOCKED" in report
    assert report.index("fever.dependency_down.001") < report.index("breathing.follow_up.001")  # blocking first


def test_non_blocking_failures(tmp_path: Path) -> None:
    def edit(case):
        if case["case_id"] == "fever.dependency_down.001":
            case["dependencies"] = {"ollama": "up", "chroma": "up", "readings": "up"}  # fake chunk-1 cited
            case["expected"].update(urgency="informational", protocol_id="heat_illness", clarify=True,
                                    workflow="unsupported", required_actions=["evacuate"],
                                    acceptable_sources=["medlineplus-fever"])

    up = fake_up()
    code, _, result, _ = evaluate(tmp_path, copy_fixtures(tmp_path, edit), up=up)
    assert up.retriever.calls  # the shared client itself is used, not a copy
    case = by_id(result)["fever.dependency_down.001"]
    assert codes(case) == {"urgency_regression", "wrong_protocol", "clarify_mismatch", "workflow_mismatch",
                           "missing_required_action", "unsupported_citation"}
    assert not case["blocking"] and not result["summary"]["release_blocked"] and code == 0
    assert result["summary"]["citation_support_rate"] < 1.0


def test_broken_case_and_unreachable_dependency_are_recorded(tmp_path: Path) -> None:
    cases = copy_fixtures(tmp_path)
    (cases / "broken.json").write_text("{not json", encoding="utf-8")
    code, _, result, _ = evaluate(tmp_path, cases, up=fake_up(unavailable={"ollama": "connection refused"}))
    assert code == 0  # errors fail cases but do not block release
    results = by_id(result)
    assert codes(results["broken"]) == {"error"} and results["broken"]["case"] is None
    assert codes(results["chest_pain.alarm.001"]) == {"error"}  # ollama expected up
    assert results["fever.dependency_down.001"]["passed"]  # everything down by design


def test_baseline_side_by_side(tmp_path: Path) -> None:
    _, _, base, _ = evaluate(tmp_path, FIXTURES, "--candidate-id", "base.1", out="base")
    code, _, result, report = evaluate(tmp_path, FIXTURES, "--baseline", str(tmp_path / "base" / "result.json"))
    assert code == 0
    assert result["baseline"] == base["manifest"]
    for c in result["cases"]:
        assert c["baseline_response"] == by_id(base)[c["case_id"]]["response"]
    assert "base.1" in report and "| no |" in report


def test_low_hit_rate_fails_cli(tmp_path: Path) -> None:
    code, *_ = evaluate(tmp_path, FIXTURES, "--min-hit-rate", "0.95")
    assert code == 1


def test_retrieval_check_is_reusable() -> None:
    family, kind, query, expected = CASES[0]
    hit = chunk(1)
    retriever = FakeRetriever([type(hit)(**{**hit.__dict__, "source_id": expected[0]})])
    rows = check_retrieval(retriever)
    assert len(rows) == len(CASES) and rows[0][:4] == (family, kind, query, expected)
    assert 0 < hit_rate(rows) < 1


def test_schema_file_next_to_cases_is_not_a_case(tmp_path: Path) -> None:
    from onboard_api.assistant.eval.runner import load_cases

    (tmp_path / "case.schema.json").write_text('{"type": "object"}', encoding="utf-8")
    (tmp_path / "fam").mkdir()
    (tmp_path / "fam" / "a.json").write_text('{"case_id": "a"}', encoding="utf-8")
    assert [c["case_id"] for c in load_cases(tmp_path)] == ["a"]


def test_case_file_without_case_id_is_a_load_error(tmp_path: Path) -> None:
    from onboard_api.assistant.eval.runner import load_cases

    (tmp_path / "odd.json").write_text('{"family": "x"}', encoding="utf-8")
    [case] = load_cases(tmp_path)
    assert case["case_id"] == "odd" and "_load_error" in case
