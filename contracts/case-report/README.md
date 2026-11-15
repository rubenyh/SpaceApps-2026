# Case report contract v1 (ship to ground)

A crew-reviewed medical case report, sent explicitly by the crew from the ship
console. Separate from telemetry v1: the telemetry batch and its
`incident_updates` payload are unchanged.

## Lifecycle onboard

| State | Meaning |
|---|---|
| `draft` | Built with an assistant reply and stored onboard under `id`. Nothing sent. |
| `queued` | Crew pressed send. Stored in the durable queue (SQLite), retried by the telemetry publisher loop until ground acknowledges this id, also after an onboard restart. |
| `received` | Ground answered 200 with `report_id` equal to this id. |
| `failed` | Ground rejected the report permanently (4xx other than 404/408/429). `error` holds the reason. Network errors and 5xx keep it `queued`. |

The demo link pause (`POST /telemetry/pause`) also holds case reports.

## Onboard API (console)

- `POST /assistant/messages`: a clinical reply carries `report: {id, text, knowledge_version, transmission: "draft"}`. The draft is stored onboard with the structured fields below.
- `POST /case-reports/{id}/send` body `{"sent_by": "<astronaut id>" | null}`: queue the draft. Idempotent: a queued or received report returns its current status. 404 for an unknown id.
- `GET /case-reports/{id}`: `CaseReportStatus {id, status, created_at, queued_at, received_at, error}`. `received_at` is ground's receipt time from the acknowledgement.

## Ground API

`POST /case-reports/v1` with body `CaseReportV1`, answers `200 {"report_id": "<id>", "received_at": "<ground receipt time>"}`.
Idempotent on `(ship_id, report_id)`: a resend (for example after a lost acknowledgement) stores nothing new and returns the original `received_at`.

`GET /case-reports` (newest first, optional `astronaut_id`, `incident_id`, `urgency` filters) and `GET /case-reports/{report_id}` return the stored report plus `received_at`.

### `CaseReportV1`

| Field | Type | Notes |
|---|---|---|
| `schema_version` | `1` | |
| `report_id` | string (UUID v4) | Stable id generated onboard. |
| `ship_id` | string | Onboard `ship_id` setting. |
| `astronaut_id` | string or null | Person assessed. |
| `reported_by` | string or null | Crewmate who reported, when not the person assessed. |
| `sent_by` | string or null | Crew member who pressed send. |
| `urgency` | `immediate` / `review_required` / `undetermined` / `informational` | From the rules. |
| `protocol_id` | string or null | |
| `action` | string or null | |
| `assessed_at` | UTC timestamp | Onboard clock when the readings were loaded. |
| `created_at` | UTC timestamp | Draft built. |
| `sent_at` | UTC timestamp | Crew pressed send. |
| `incident_id` | string or null | Onboard incident id when one exists. |
| `text` | string | The report body exactly as previewed. |
| `readings` | list of `SnapshotReading` | `report.readings` from the reply: relevant readings with provenance: `id, kind, value, value_text, unit, recorded_at, received_at, quality, source, simulated, freshness, age_seconds`. |
| `knowledge_version` | `{candidate_id, digest}` or null | |

Never included: the raw chat message, the assistant reply text, wellbeing data, or readings unrelated to the case.
