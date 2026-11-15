# Medical assistant verification

Run date: 2026-11-15. Code commit measured: `d0eeb78` (branch `agent/rubenyh/incident-outage-flow`).
Environment: Windows 11, Python 3.12.7, `uv sync --locked`, `PYTHONUTF8=1`, run from `services/onboard-api`.
All assistant tests use a fake LLM, a fake retriever and fake or temporary SQLite readings. No live Ollama or ChromaDB server was used.

## Results (one run each)

| Command | Collected | Passed | Failed | Skipped | Time |
|---|---|---|---|---|---|
| `uv run pytest tests/assistant` | 296 | 296 | 0 | 0 | 71.72 s |
| `uv run pytest -q --durations=10` (full suite) | 418 | 417 | 0 | 1 | 125.34 s |

The skipped test is `tests/test_migrations.py:156` ("no local data/onboard.db"). It is not part of the assistant tests.

Slowest 10 (full-suite run):

| Time | Phase | Test |
|---|---|---|
| 6.06 s | call | `tests/test_wellbeing_simulator.py::test_simulated_crew_tells_the_demo_story` |
| 2.44 s | setup | `tests/assistant/test_retrieval.py::test_matching_query_hits_best_first` |
| 2.22 s | call | `tests/assistant/test_retrieval.py::test_index_built_by_another_process_is_seen_after_empty_search` |
| 1.27 s | call | `tests/test_readings.py::test_persistence_across_app_instances` |
| 1.14 s | call | `tests/test_telemetry.py::test_queued_update_survives_restart` |
| 1.04 s | call | `tests/test_incidents.py::test_incident_survives_restart` |
| 0.93 s | call | `tests/assistant/test_no_clinician.py::test_no_ground_link` |
| 0.89 s | setup | `tests/assistant/test_post_cases.py::test_evidence_flags_on_reading_findings[demo-review]` |
| 0.86 s | setup | `tests/assistant/test_post_cases.py::test_evidence_flags_on_reading_findings[demo-immediate]` |
| 0.80 s | setup | `tests/assistant/test_post_cases.py::test_simultaneous_alarms` |

## What the fixtures cover

- Every card has a positive (activating) case and a near case that must not activate it. Each card also has a negated-symptom case (`tests/assistant/medical_cases.py`).
- Evidence flags on reading findings, on the immediate path and the review path: fresh (none), `simulated` (`simulated:*` and `demo`), `stale` (old or future-dated), `poor_quality`, and `missing` (no reading, or the repository is unavailable). Flags never change the card or the urgency.
- Ollama unavailable, on the immediate path and the review path. The card still answers, `mission_procedures` are all `loaded: false`, and `missing_guidance` is stated in the response and the case report.
- Wellbeing isolation (`tests/assistant/test_wellbeing_isolation.py`): no module in `onboard_api.assistant` imports `onboard_api.wellbeing`. The response is identical with and without a vision session, a check-in and a wellbeing signal in the database.

## Protocol card review

All cards are showcased: each one has an activating case in the fixtures. No card has been reviewed by qualified medical personnel yet.

| Card id | Version | Reviewer qualification | Date | Result |
|---|---|---|---|---|
| `abdominal_pain_or_gi_bleeding` | 2.1.0 | | | Pending qualified review |
| `breathing_difficulty` | 2.1.0 | | | Pending qualified review |
| `cabin_environment_alert` | 2.1.0 | | | Pending qualified review |
| `chest_pain` | 2.1.0 | | | Pending qualified review |
| `dizziness_or_space_motion_sickness` | 2.1.0 | | | Pending qualified review |
| `fever_or_respiratory_illness` | 2.1.0 | | | Pending qualified review |
| `heat_illness` | 2.1.0 | | | Pending qualified review |
| `injury_bleeding_or_burn` | 2.1.0 | | | Pending qualified review |
| `loss_of_consciousness_or_seizure` | 2.1.0 | | | Pending qualified review |
| `muscle_symptoms` | 2.1.0 | | | Pending qualified review |
| `neurologic_red_flags` | 2.1.0 | | | Pending qualified review |
| `palpitations` | 2.1.0 | | | Pending qualified review |
| `radiation_alert` | 2.1.0 | | | Pending qualified review |
| `severe_allergic_reaction` | 2.1.0 | | | Pending qualified review |
| `urinary_symptoms` | 2.1.0 | | | Pending qualified review |
| `vomiting_diarrhea_or_dehydration` | 2.1.0 | | | Pending qualified review |
