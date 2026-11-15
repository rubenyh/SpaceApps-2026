# Medical evaluation cases

Synthetic, versioned cases for the onboard medical assistant (issue #52). The case format is
section 1 of [`contracts/medical-eval/README.md`](../../contracts/medical-eval/README.md). Its JSON
Schema is [`cases/v1/case.schema.json`](cases/v1/case.schema.json). The runner (#53) sends each
case to `POST /assistant/messages` and compares the last response with `expected`.

**No clinician has reviewed any of these cases yet. Every case is `draft`.** The team wrote the
expected values from the protocol cards
(`services/onboard-api/src/onboard_api/assistant/workflows/medical/protocols/*.json`) and the rules
in `interpret.py` and `triage.py`. They are not clinical judgements.

All people, messages and readings are synthetic. Astronaut id `ast-01` is a placeholder.

## Layout

```text
eval/medical/cases/v1/
  case.schema.json
  <family>/<case_id>.json     family = protocol card id
```

- `case_id` is `<family short name>.<kind>.<nnn>`, for example `dizziness.typo.001`.
- `version` is the case version. Increase it when `expected` changes. A new case format gets a new directory (`v2/`).
- Messages are mostly English (the console language), with some Spanish.
- A turn with `use_previous_clarification: true` copies `clarification` from the previous response (two-turn follow-ups).
- `readings` use `age_seconds` instead of `recorded_at`. Pulse and SpO₂ older than 300 s are stale.
- `events` have fixed timestamps. The rules use only their `status` and `provenance`.
- `dependencies` marks Ollama, ChromaDB or the readings repository as down for that case.

## Expected values

- `urgency`, `protocol_id` and `clarify` follow the card rules. Alarms are `immediate`. A card question gives `undetermined` with `clarify: true`. Hypothetical and educational questions are `informational` with no card. A symptom without a card gets the out-of-coverage reply (`review_required`, no card, no sources).
- `required_actions` are substrings of the card action text that must appear in `action` or `steps`.
- `prohibited_actions` are substrings that must not appear in `reply`, `action` or `steps` (case-insensitive): medication the card does not give, de-escalation, exposure denial. None of them occurs in any card action or step text, so a negated safe phrase ("do not hold them down") never matches.
- `acceptable_sources` are guide chunk id prefixes only: the English MedlinePlus sources of the expected card's `guide_topics` (`services/onboard-api/corpus/manifest.json`), for example `medlineplus-dizzinessandvertigo`. Protocol card sources always count as supported, so they are not listed. An empty list means no guide chunk is acceptable.
- A dependency that is down never changes urgency or the card. The expected values stay the same and the response states what is missing.

The expectations were checked in process (real endpoint and SQLite, fake LLM and retriever, no
Ollama). Gaps found that way are listed below.

## Coverage

| Family | Cases |
|---|---|
| `abdominal_pain_or_gi_bleeding` | 6 |
| `breathing_difficulty` | 8 |
| `cabin_environment_alert` | 9 |
| `chest_pain` | 7 |
| `dizziness_or_space_motion_sickness` | 7 |
| `fever_or_respiratory_illness` | 8 |
| `heat_illness` | 6 |
| `injury_bleeding_or_burn` | 7 |
| `loss_of_consciousness_or_seizure` | 9 |
| `muscle_symptoms` | 6 |
| `neurologic_red_flags` | 8 |
| `palpitations` | 6 |
| `radiation_alert` | 7 |
| `severe_allergic_reaction` | 6 |
| `urinary_symptoms` | 7 |
| `vomiting_diarrhea_or_dehydration` | 7 |
| **Total** | **114** |

| Tag | Cases |
|---|---|
| `alarm` | 49 |
| `conflicting_readings` | 7 |
| `dependency_down` | 11 |
| `follow_up` | 8 |
| `hypothetical` | 5 |
| `missing_equipment` | 5 |
| `near_miss` | 33 |
| `negation` | 18 |
| `simulated_data` | 9 |
| `stale_readings` | 4 |
| `transcription` | 4 |
| `typo` | 5 |

Every card with an `immediate` action has at least one `alarm` or `near_miss` case. `muscle_symptoms`
has no `immediate` action, so its cases are reviews and near misses.

## Known gaps and dependencies

No case is known to fail on content against `main`. These gaps were found by the set and are fixed:

- Typo and transcription cases (`breathing.transcription.001`, `chest.hypothetical.002`, `dizziness.typo.001`, `fever.typo.001`, `injury.typo.001`, `loc.transcription.001`, `neuro.transcription.001`, `neuro.typo.001`, `vomiting.typo.001`) and `loc.negation.002` (English "didn't"): issue #51.
- `cabin.alarm.005` (English "several of us have …" raised no cabin alarm) and `abdominal.stale.001` (Spanish "me duele mucho el estómago" was out of coverage): issue #73.
- `urinary.simulated.001` (live run only: the LLM interpreter read a reddish sample with "no tengo síntomas" as dark urine and gave the muscle card): issue #78.

Passing these cases means the code matches the team's draft expectations. It is not a clinical review.

## Review log

Only a named clinician may set `reviewed` or `rejected`, with `reviewer` and `reviewed_at` in the
case file and in this table. Team-written expectations stay `draft`.
`services/onboard-api/tests/assistant/test_eval_cases.py` keeps this table in sync with the case files.

Draft: 114. Reviewed: 0. Rejected: 0.

| case_id | status | reviewer | date |
|---|---|---|---|
| `abdominal.alarm.001` | draft | - | - |
| `abdominal.alarm.002` | draft | - | - |
| `abdominal.alarm.003` | draft | - | - |
| `abdominal.negation.001` | draft | - | - |
| `abdominal.review.001` | draft | - | - |
| `abdominal.stale.001` | draft | - | - |
| `breathing.alarm.001` | draft | - | - |
| `breathing.alarm.002` | draft | - | - |
| `breathing.alarm.003` | draft | - | - |
| `breathing.follow_up.001` | draft | - | - |
| `breathing.follow_up.002` | draft | - | - |
| `breathing.missing_equipment.001` | draft | - | - |
| `breathing.negation.001` | draft | - | - |
| `breathing.transcription.001` | draft | - | - |
| `cabin.alarm.001` | draft | - | - |
| `cabin.alarm.002` | draft | - | - |
| `cabin.alarm.003` | draft | - | - |
| `cabin.alarm.004` | draft | - | - |
| `cabin.alarm.005` | draft | - | - |
| `cabin.dependency_down.001` | draft | - | - |
| `cabin.near_miss.001` | draft | - | - |
| `cabin.negation.001` | draft | - | - |
| `cabin.simulated.001` | draft | - | - |
| `chest.alarm.001` | draft | - | - |
| `chest.alarm.002` | draft | - | - |
| `chest.alarm.003` | draft | - | - |
| `chest.hypothetical.001` | draft | - | - |
| `chest.hypothetical.002` | draft | - | - |
| `chest.near_miss.001` | draft | - | - |
| `chest.negation.001` | draft | - | - |
| `dizziness.alarm.001` | draft | - | - |
| `dizziness.follow_up.001` | draft | - | - |
| `dizziness.hypothetical.001` | draft | - | - |
| `dizziness.negation.001` | draft | - | - |
| `dizziness.review.001` | draft | - | - |
| `dizziness.simulated.001` | draft | - | - |
| `dizziness.typo.001` | draft | - | - |
| `fever.alarm.001` | draft | - | - |
| `fever.alarm.002` | draft | - | - |
| `fever.dependency_down.001` | draft | - | - |
| `fever.missing_equipment.001` | draft | - | - |
| `fever.negation.001` | draft | - | - |
| `fever.review.001` | draft | - | - |
| `fever.transcription.001` | draft | - | - |
| `fever.typo.001` | draft | - | - |
| `heat.alarm.001` | draft | - | - |
| `heat.alarm.002` | draft | - | - |
| `heat.dependency_down.001` | draft | - | - |
| `heat.negation.001` | draft | - | - |
| `heat.review.001` | draft | - | - |
| `heat.simulated.001` | draft | - | - |
| `injury.alarm.001` | draft | - | - |
| `injury.alarm.002` | draft | - | - |
| `injury.alarm.003` | draft | - | - |
| `injury.negation.001` | draft | - | - |
| `injury.review.001` | draft | - | - |
| `injury.review.002` | draft | - | - |
| `injury.typo.001` | draft | - | - |
| `loc.alarm.001` | draft | - | - |
| `loc.alarm.002` | draft | - | - |
| `loc.alarm.003` | draft | - | - |
| `loc.follow_up.001` | draft | - | - |
| `loc.near_miss.001` | draft | - | - |
| `loc.negation.001` | draft | - | - |
| `loc.negation.002` | draft | - | - |
| `loc.review.001` | draft | - | - |
| `loc.transcription.001` | draft | - | - |
| `muscle.dependency_down.001` | draft | - | - |
| `muscle.near_miss.001` | draft | - | - |
| `muscle.negation.001` | draft | - | - |
| `muscle.review.001` | draft | - | - |
| `muscle.review.002` | draft | - | - |
| `muscle.simulated.001` | draft | - | - |
| `neuro.alarm.001` | draft | - | - |
| `neuro.alarm.002` | draft | - | - |
| `neuro.alarm.003` | draft | - | - |
| `neuro.follow_up.001` | draft | - | - |
| `neuro.follow_up.002` | draft | - | - |
| `neuro.negation.001` | draft | - | - |
| `neuro.transcription.001` | draft | - | - |
| `neuro.typo.001` | draft | - | - |
| `palpitations.alarm.001` | draft | - | - |
| `palpitations.alarm.002` | draft | - | - |
| `palpitations.follow_up.001` | draft | - | - |
| `palpitations.negation.001` | draft | - | - |
| `palpitations.review.001` | draft | - | - |
| `palpitations.stale.001` | draft | - | - |
| `radiation.alarm.001` | draft | - | - |
| `radiation.alarm.002` | draft | - | - |
| `radiation.dependency_down.001` | draft | - | - |
| `radiation.hypothetical.001` | draft | - | - |
| `radiation.missing_equipment.001` | draft | - | - |
| `radiation.negation.001` | draft | - | - |
| `radiation.simulated.001` | draft | - | - |
| `allergy.alarm.001` | draft | - | - |
| `allergy.alarm.002` | draft | - | - |
| `allergy.alarm.003` | draft | - | - |
| `allergy.hypothetical.001` | draft | - | - |
| `allergy.near_miss.001` | draft | - | - |
| `allergy.negation.001` | draft | - | - |
| `urinary.alarm.001` | draft | - | - |
| `urinary.alarm.002` | draft | - | - |
| `urinary.near_miss.001` | draft | - | - |
| `urinary.negation.001` | draft | - | - |
| `urinary.review.001` | draft | - | - |
| `urinary.review.002` | draft | - | - |
| `urinary.simulated.001` | draft | - | - |
| `vomiting.alarm.001` | draft | - | - |
| `vomiting.alarm.002` | draft | - | - |
| `vomiting.follow_up.001` | draft | - | - |
| `vomiting.missing_equipment.001` | draft | - | - |
| `vomiting.negation.001` | draft | - | - |
| `vomiting.review.001` | draft | - | - |
| `vomiting.typo.001` | draft | - | - |
