"""Camera-derived and other wellbeing data never feed an emergency (or any medical) decision."""

import ast
import pkgutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import onboard_api.assistant
from assistant.medical_cases import _reading
from assistant.test_post_cases import post
from conftest import T0
from onboard_api.wellbeing.dependencies import get_wellbeing_clock
from onboard_api.wellbeing.settings import WellbeingSettings, get_wellbeing_settings

VISION = {
    "astronaut_id": "ana", "session_type": "bitacora", "module_id": "modulo-a", "source": "vision:cam0",
    "started_at": "2026-11-14T11:00:00Z", "ended_at": "2026-11-14T11:01:30Z", "quality": "good",
    "valid_frame_ratio": 0.94, "identity": {"method": "face", "match_score": 0.71}, "neutral_ok": True,
    "fatigue": {"blink_rate_per_min": 40.0, "perclos": 0.4, "eye_openness_vs_neutral": 0.5,
                "yawn_count": 9, "nod_count": 6},
    "tension": {"brow_lower_delta": 0.6, "lip_press_delta": 0.5}, "motion": None, "provisional": True,
}
CHECKIN = {"sleep_hours": 3.0, "sleep_quality": 1, "energy": 1, "mood": 1, "interest": 1, "stress": 4,
           "crew_connection": 1}
SIGNAL = {"astronaut_id": "ana", "kind": "hrv_sdnn", "value": 12.0, "unit": "ms",
          "recorded_at": "2026-11-14T11:30:00Z", "quality": "good", "source": "apple_watch_export"}


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out |= {f"{node.module}.{a.name}" for a in node.names}
    return out


def test_assistant_package_never_imports_wellbeing() -> None:
    modules = list(pkgutil.walk_packages(onboard_api.assistant.__path__, "onboard_api.assistant."))
    assert len(modules) > 10  # the walk really covers the package
    files = [Path(onboard_api.assistant.__file__)] + [
        Path(m.module_finder.path) / (m.name.rsplit(".", 1)[1] + ("/__init__.py" if m.ispkg else ".py"))
        for m in modules
    ]
    for f in files:
        bad = {i for i in _imports(f) if i == "onboard_api.wellbeing" or i.startswith("onboard_api.wellbeing.")}
        assert not bad, (f, bad)


@pytest.mark.parametrize(
    "message", ["Me falta mucho el aire de repente", "Tengo fiebre y tos desde ayer"], ids=["immediate", "review"]
)
def test_wellbeing_data_does_not_change_triage(
    client: TestClient, astronaut: str, db_path: Path, tmp_path: Path, message: str
) -> None:
    request = {"message": message, "astronaut_id": "ana"}
    readings = [_reading("spo2", 97, "%"), _reading("heart_rate", 80, "bpm")]
    before, *_ = post(client, db_path, request, readings=readings)

    settings = WellbeingSettings(db_path=tmp_path / "wb" / "wellbeing.db", onboard_db_path=db_path)
    client.app.dependency_overrides[get_wellbeing_settings] = lambda: settings
    client.app.dependency_overrides[get_wellbeing_clock] = lambda: lambda: T0
    assert client.post("/wellbeing/vision-sessions", json=VISION).status_code == 201
    assert client.put("/astronauts/ana/wellbeing/checkins/2026-11-14", json=CHECKIN).status_code == 200
    assert client.post("/wellbeing/signals", json=SIGNAL).status_code == 201

    after, *_ = post(client, db_path, request)
    assert after == before
