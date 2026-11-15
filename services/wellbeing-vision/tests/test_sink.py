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
