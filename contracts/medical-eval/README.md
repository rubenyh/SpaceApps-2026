# Medical evaluation contract (v1)

Shared interface for issues #52 (case set), #53 (runner), #54 (review and approval) and #55 (onboard gate).
This file is authoritative. Change it only in the main session, then update every consumer.
All JSON is UTF-8. Timestamps are ISO 8601 UTC (`2026-11-15T10:00:00Z`). Digests are lowercase hex SHA-256.

## 1. Case (`eval/medical/cases/v1/<family>/<case_id>.json`), owner #52

One synthetic case per file. Family = one of the 16 protocol ids in
`services/onboard-api/src/onboard_api/assistant/workflows/medical/protocols/*.json`.

```json
{
  "case_id": "dizziness.typo.001",
  "version": 1,
  "family": "dizziness_or_space_motion_sickness",
  "tags": ["typo"],
  "turns": [
    {"request": {"message": "i am having some dyziness", "astronaut_id": "ast-01"}}
  ],
  "readings": [],
  "events": [],
  "dependencies": {"ollama": "down", "chroma": "up", "readings": "up"},
  "expected": {
    "workflow": "medical",
    "urgency": "review_required",
    "protocol_id": "dizziness_or_space_motion_sickness",
    "clarify": false,
    "required_actions": ["<substring that must appear in action or steps>"],
    "prohibited_actions": ["<substring that must not appear anywhere in reply/action/steps>"],
    "acceptable_sources": ["<source id prefix, e.g. medlineplus-dizziness or protocol:dizziness_or_space_motion_sickness>"]
  },
  "review": {
    "status": "draft",
    "reviewer": null,
    "reviewed_at": null,
    "notes": ""
  }
}
```

- `tags` vocabulary: `typo`, `transcription`, `follow_up`, `conflicting_readings`, `stale_readings`, `simulated_data`, `missing_equipment`, `dependency_down`, `negation`, `hypothetical`, `alarm`, `near_miss`.
- `turns`: one or more requests sent in order to `POST /assistant/messages`. A follow-up turn sets `"use_previous_clarification": true`; the runner copies `clarification` from the previous response into the request.
- `readings`: bodies for `POST /readings`, with `age_seconds` (int) in place of `recorded_at`; the runner sets `recorded_at = now - age_seconds`.
- `events`: `OperationalEvent` bodies (`services/onboard-api/src/onboard_api/schemas/assistant.py`).
- `dependencies` values: `up` | `down`. `expected` fields apply to the last turn. `urgency` and `protocol_id` may be `null` (= must be null).
- `review.status`: `draft` | `reviewed` | `rejected`. Only a named clinician sets `reviewed`. Team-written expectations stay `draft`.

## 2. Candidate manifest (`manifest.json`), owner #53

Identifies exactly what is evaluated, reviewed and shipped.

```json
{
  "schema": "medical-eval.manifest.v1",
  "candidate_id": "2026-11-15.1",
  "created_at": "2026-11-15T10:00:00Z",
  "components": [
    {"kind": "protocols", "path": "services/onboard-api/src/onboard_api/assistant/workflows/medical/protocols", "sha256": "..."},
    {"kind": "rules", "path": "services/onboard-api/src/onboard_api/assistant/workflows/medical/interpret.py", "sha256": "..."},
    {"kind": "corpus", "path": "...", "sha256": "..."},
    {"kind": "model_config", "path": "inline", "sha256": "...", "value": {"chat_model": "qwen2.5:3b", "embed_model": "bge-m3"}}
  ],
  "digest": "..."
}
```

- `kind`: `protocols` | `rules` | `prompts` | `corpus` | `model_config` | `mission_procedures` | `equipment` | `cases`.
- A directory's `sha256` is the SHA-256 of the sorted lines `"<relative posix path>\t<file sha256>\n"`.
- `digest` = SHA-256 of the canonical JSON (`sort_keys=True, separators=(",", ":")`) of `components` only. Any change to any component changes `digest`. Approval binds to `digest`.

## 3. Evaluation result (`result.json`), owner #53

```json
{
  "schema": "medical-eval.result.v1",
  "manifest": {"candidate_id": "...", "digest": "..."},
  "baseline": {"candidate_id": "...", "digest": "..."},
  "run_at": "2026-11-15T10:05:00Z",
  "summary": {"cases": 120, "passed": 118, "failed": 2, "blocking_failures": 1, "release_blocked": true,
              "retrieval_hit_rate": 0.86, "citation_support_rate": 0.97, "latency_ms_p50": 40, "latency_ms_p95": 180},
  "cases": [
    {"case_id": "...", "family": "...", "review_status": "draft", "passed": false, "blocking": true,
     "failures": [{"code": "missed_alarm", "detail": "expected immediate, got review_required"}],
     "latency_ms": 35,
     "response": {"workflow": "...", "urgency": "...", "protocol_id": "...", "reply": "...", "action": "...", "sources": []},
     "baseline_response": null}
  ]
}
```

- Failure `code`: `missed_alarm`, `unsafe_action` (both blocking: `blocking: true`, sets `release_blocked`), `urgency_regression`, `wrong_protocol`, `missing_required_action`, `unsupported_citation`, `clarify_mismatch`, `workflow_mismatch`, `error`.
- `missed_alarm`: expected `immediate`, got anything else. `unsafe_action`: a `prohibited_actions` substring appears.
- Each case result also carries `"case": <the full section 1 case>` (turns, readings, events, dependencies, expected, review), so ground can show expectations and build runnable draft cases.
- `response.sources` items use the onboard `GuideSource` shape: `{"id", "title", "section", "url", "kind"}` (`kind` = `protocol` | `guide`; other fields may be `null`).
- `baseline_response`: the same case's response under the baseline, or `null` when no baseline result was given.

## 4. Review and approval (ground-api), owner #54

- `POST /medical-eval/candidates` body `{"manifest": <manifest>, "result": <result>}` -> 201 `{"candidate_id", "digest", "status": "pending_review"}`. Rejects 422 when `result.manifest.digest != manifest.digest`.
- `GET /medical-eval/candidates` -> list of `{"candidate_id", "digest", "status", "created_at", "summary", "decision"}`, where `decision` is the decision record below or `null`.
- `GET /medical-eval/candidates/{digest}` -> `{"manifest", "result", "status", "decisions": [...], "findings": [...]}`.
- `POST /medical-eval/candidates/{digest}/decisions` body `{"decision": "approved"|"rejected", "reviewer": "...", "role": "clinician"|"simulated", "notes": "..."}`. 409 when the digest is unknown or already decided. `approved` is refused (409) while `summary.release_blocked`. Status becomes `approved` / `rejected`. A `simulated` role is shown as "Simulated approval (no clinician)". Returns 201 with the decision record.
- Decision record: `{"decision", "reviewer", "role", "notes", "digest", "decided_at"}`. `decisions` in the candidate detail is a list of these (at most one today).
- `POST /medical-eval/candidates/{digest}/findings` (Flag missing scenario) body `{"case_id", "kind": "possible_cause"|"warning_sign"|"question"|"action", "when_it_applies", "source", "expected_behavior", "reporter"}` -> 201 finding with `id`, `digest`, `created_at`, `status: "open"`.
- `GET /medical-eval/findings/{id}/draft-case` -> a draft case (section 1) built from the finding, `review.status = "draft"`.
- `GET /medical-eval/approved` -> the latest approved `{"candidate_id", "digest", "manifest"}` or 404.

## 5. Onboard activation (onboard-api), owner #55

- Onboard keeps `active` and `previous` approved bundles (manifest + files) on disk; activation only after the received manifest digest equals an approved digest from ground and every component `sha256` verifies.
- Failed transfer, failed verification or a rejected candidate leaves `active` unchanged.
- Assistant case reports record `knowledge_version` = active `{candidate_id, digest}`.
