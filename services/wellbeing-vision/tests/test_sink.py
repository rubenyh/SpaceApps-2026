import json
from datetime import UTC, datetime

import httpx

from wellbeing_vision.schemas import Identity, VisionSession
from wellbeing_vision.sink import Sink

ROUTE = "/wellbeing/vision-sessions"


def _session() -> VisionSession:
    now = datetime.now(UTC)
    return VisionSession(
        astronaut_id="ast-01", session_type="bitacora", module_id="modulo-a",
        source="vision:cam0", started_at=now, ended_at=now, quality="good",
        valid_frame_ratio=1.0, identity=Identity(method="manual"),
        neutral_ok=True, fatigue=None, tension=None,
    )


def _sink(tmp_path, handler) -> Sink:
    client = httpx.Client(base_url="http://test", transport=httpx.MockTransport(handler))
    return Sink("http://test", tmp_path / "outbox.jsonl", client=client)


def test_dry_run_writes_file_and_never_posts(tmp_path):
    out = tmp_path / "dry.jsonl"
    sink = Sink("http://unused", tmp_path / "outbox.jsonl", dry_run=True, dry_run_file=out)
    assert sink.send(ROUTE, _session())
    line = json.loads(out.read_text(encoding="utf-8"))
    assert line["route"] == ROUTE and line["body"]["astronaut_id"] == "ast-01"


def test_failure_queues_then_flushes_in_order(tmp_path):
    up = {"ok": False}
    seen = []

    def handler(req):
        if not up["ok"]:
            return httpx.Response(503)
        seen.append(json.loads(req.content)["astronaut_id"])
        return httpx.Response(201)

    sink = _sink(tmp_path, handler)
    assert not sink.send(ROUTE, _session())
    assert not sink.send(ROUTE, _session())
    assert len(sink.outbox_path.read_text().splitlines()) == 2
    up["ok"] = True
    assert sink.send(ROUTE, _session())
    assert seen == ["ast-01"] * 3
    assert not sink.outbox_path.exists()


def test_validation_rejection_is_parked_not_retried(tmp_path):
    sink = _sink(tmp_path, lambda req: httpx.Response(422, json={"detail": "bad"}))
    assert sink.send(ROUTE, _session())
    assert not sink.outbox_path.exists()
    assert (tmp_path / "rejected.jsonl").exists()


def _checked(handler, capsys, tmp_path):
    client = httpx.Client(base_url="http://192.168.1.20:8000", transport=httpx.MockTransport(handler))
    ok = Sink("unused", tmp_path / "outbox" / "pending.jsonl", client=client).check()
    return ok, capsys.readouterr().out


def test_check_reports_the_api_and_never_raises(capsys, tmp_path):
    ok, out = _checked(lambda req: httpx.Response(200, json={"mission_tz": "America/Tijuana"}), capsys, tmp_path)
    assert ok and out.strip() == "API OK at http://192.168.1.20:8000 (mission_tz=America/Tijuana)"

    def down(req):
        raise httpx.ConnectError("connection refused", request=req)

    def slow(req):
        raise httpx.ReadTimeout("timed out", request=req)

    for handler, says in ((down, "not reachable at http://192.168.1.20:8000"), (slow, "timeout"),
                          (lambda req: httpx.Response(404), "HTTP 404"), (lambda req: httpx.Response(200, text="hi"), "not with JSON")):
        ok, out = _checked(handler, capsys, tmp_path)
        assert not ok and says in out and "pending.jsonl" in out


def test_api_url_option_wins_over_the_env_var(monkeypatch):
    import sys

    import wellbeing_vision.ambiente as amb
    from wellbeing_vision import cli

    seen = {}
    monkeypatch.setenv("WELLBEING_VISION_API_URL", "http://127.0.0.1:8000")
    monkeypatch.setattr(Sink, "check", lambda self: seen.setdefault("checked", str(self.client.base_url)))
    monkeypatch.setattr(amb, "run_ambiente", lambda settings, sink, *a: seen.setdefault("url", settings.api_url))
    monkeypatch.setattr(sys, "argv", ["wellbeing-vision", "ambiente", "--api-url", "http://192.168.1.20:8000"])
    cli.main()
    assert seen == {"checked": "http://192.168.1.20:8000", "url": "http://192.168.1.20:8000"}
    monkeypatch.setattr(sys, "argv", ["wellbeing-vision", "ambiente", "--dry-run"])
    seen.clear()
    cli.main()
    assert seen == {"url": "http://127.0.0.1:8000"}  # env var used; no check in dry-run


def test_a_down_api_costs_one_attempt_per_send_not_one_per_queued_entry(tmp_path):
    calls = []

    def down(req):
        calls.append(req)
        raise httpx.ConnectError("refused", request=req)

    client = httpx.Client(base_url="http://x", transport=httpx.MockTransport(down))
    sink = Sink("unused", tmp_path / "pending.jsonl", client=client)
    for _ in range(5):
        sink.send(ROUTE, _session())
    assert len(calls) == 5  # one attempt per send: the outbox retry; the new summary queues behind it
    assert len((tmp_path / "pending.jsonl").read_text().splitlines()) == 5  # nothing lost, order kept
