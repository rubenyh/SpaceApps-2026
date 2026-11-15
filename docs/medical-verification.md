# Medical assistant verification

Run date: 2026-11-15. Code commit measured: `698a7ef` (branch `agent/rubenyh/medical-traceability`).
Environment: Windows 11, Python 3.12.7, `uv sync --locked`, `PYTHONUTF8=1`, run from `services/onboard-api`.
All assistant tests use a fake LLM, a fake retriever and fake or temporary SQLite readings. No live Ollama or ChromaDB server was used.

## Results (one run each)

| Command | Collected | Passed | Failed | Skipped | Time |
|---|---|---|---|---|---|
| `uv run pytest tests/assistant` | 296 | 296 | 0 | 0 | 77.96 s |
| `uv run pytest --durations=15` (full suite) | 397 | 396 | 0 | 1 | 129.96 s |

The skipped test is `tests/test_migrations.py:139` ("no local data/onboard.db"). It is not part of the assistant tests.

Slowest 15 (full-suite run):

| Time | Phase | Test |
|---|---|---|
| 6.98 s | call | `tests/test_wellbeing_simulator.py::test_simulated_crew_tells_the_demo_story` |
| 2.48 s | call | `tests/assistant/test_retrieval.py::test_index_built_by_another_process_is_seen_after_empty_search` |
| 1.78 s | setup | `tests/assistant/test_retrieval.py::test_matching_query_hits_best_first` |
| 1.24 s | call | `tests/assistant/test_no_clinician.py::test_no_ground_link` |
| 1.20 s | call | `tests/test_readings.py::test_persistence_across_app_instances` |
| 1.14 s | setup | `tests/assistant/test_post_cases.py::test_all_dependencies_down_alarm_still_immediate` |
| 1.10 s | setup | `tests/assistant/test_post_cases.py::test_ollama_down_states_missing_mission_guidance[review]` |
| 1.05 s | setup | `tests/assistant/test_post_cases.py::test_educational_abstains_without_chunks[failing]` |
| 1.04 s | setup | `tests/assistant/test_post_cases.py::test_ollama_failing_falls_back_to_card` |
| 0.92 s | setup | `tests/assistant/test_clarification.py::test_follow_up_qualifies_the_open_symptom` |
| 0.89 s | setup | `tests/assistant/test_post_cases.py::test_headache_clarification_round_trip[structured]` |
| 0.83 s | setup | `tests/assistant/test_post_cases.py::test_ollama_down_states_missing_mission_guidance[immediate]` |
| 0.83 s | setup | `tests/assistant/test_clarification.py::test_sos_keeps_the_card_alarms_of_the_case` |
| 0.82 s | setup | `tests/assistant/test_clarification.py::test_bare_answers_work_with_the_interpreter_down[sí, un poco]` |
| 0.79 s | setup | `tests/test_astronauts_sensors.py::test_invalid_astronaut_id_is_422` |

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
