import zipfile
from datetime import date
from pathlib import Path

from onboard_api.wellbeing.health_import import iter_signals, open_export

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "apple_health" / "export.xml"


def read(path: Path, **kwargs):
    with open_export(path) as stream:
        return list(iter_signals(stream, "ast-01", **kwargs))


def test_sample_export_maps_hrv_resting_hr_and_sleep() -> None:
    signals = read(SAMPLE)
    by_kind: dict[str, list] = {}
    for s in signals:
        by_kind.setdefault(s.kind, []).append(s)
    assert [s.value for s in by_kind["hrv_sdnn"]] == [54.2, 49.8, 47.1]
    assert [s.value for s in by_kind["resting_heart_rate"]] == [57, 59]  # count/s skipped
    assert all(s.unit == "bpm" for s in by_kind["resting_heart_rate"])
    # Night 1: core 3 h + deep 1.5 h + REM 2.5 h; the iPhone overlap and InBed/Awake
    # add nothing. Night 2: 4 h + 2 h.
    sleep = by_kind["sleep_hours"]
    assert [(s.recorded_at.date(), s.value) for s in sleep] == [
        (date(2026, 11, 9), 7.0),
        (date(2026, 11, 10), 6.0),
    ]
    assert all(s.source == "apple_watch_export" and s.astronaut_id == "ast-01" for s in signals)


def test_zip_export_streams_without_extracting(tmp_path: Path) -> None:
    archive = tmp_path / "export.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.write(SAMPLE, "apple_health_export/export.xml")
        zf.writestr("apple_health_export/export_cda.xml", "<ClinicalDocument/>")
    assert read(archive) == read(SAMPLE)


def test_since_and_source_filters() -> None:
    signals = read(SAMPLE, since=date(2026, 11, 10), source="simulated:apple_health_sample")
    assert {(s.kind, s.recorded_at.date()) for s in signals} == {
        ("hrv_sdnn", date(2026, 11, 10)),
        ("resting_heart_rate", date(2026, 11, 10)),
        ("sleep_hours", date(2026, 11, 10)),
    }
    assert all(s.source == "simulated:apple_health_sample" for s in signals)
