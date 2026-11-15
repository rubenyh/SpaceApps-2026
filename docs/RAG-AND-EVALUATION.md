# RAG and evaluation

How to build the guide index the medical assistant retrieves from, and how to run the two evaluations: the retrieval check and the medical case suite. Run every command from `services/onboard-api` unless a step says otherwise. On Windows, set `PYTHONUTF8=1` first (`$env:PYTHONUTF8 = "1"` in PowerShell).

Where retrieval sits in a request: [ARCHITECTURE.md, flow 3](ARCHITECTURE.md#3-assistant-request-initial-message) and [flow 5](ARCHITECTURE.md#5-guide-ingestion-and-retrieval). Variables: [CONFIGURATION.md](CONFIGURATION.md#onboard-api-onboard_).

## Models

Everything runs on a local Ollama server. No cloud model is called.

| Model | Role | Configured by | Needed for |
|---|---|---|---|
| `bge-m3` | Embeddings for ingest and for each query | `ONBOARD_OLLAMA_EMBED_MODEL`, and `embedding_model` in [`corpus/manifest.json`](../services/onboard-api/corpus/manifest.json) (the two must match) | Ingest, retrieval, both evaluations |
| `qwen2.5:3b` | Local interpreter (JSON) on non-alarm turns, and the drafted explanation | `ONBOARD_OLLAMA_CHAT_MODEL` | Assistant answers with prose, the medical case suite |

```sh
ollama pull bge-m3
ollama pull qwen2.5:3b
ollama list                  # both names must appear
```

In Docker Compose, the `demo-init` service pulls both models into the `ollama` container. The Compose `ollama` container does not publish port 11434, so the native commands in this guide need a native Ollama server on the host.

Without the chat model, alarm and rule decisions still work. The reply then uses protocol card text and says so in `data_notices`.

## The corpus

| Source | File | What |
|---|---|---|
| MedlinePlus Health Topics | [`corpus/manifest.json`](../services/onboard-api/corpus/manifest.json) lists 22 topics, mapped to protocol cards | Public XML from medlineplus.gov, downloaded at ingest time |
| Curated text | [`corpus/curated.json`](../services/onboard-api/corpus/curated.json), 32 entries | Mission-specific text, such as radiation dosimetry, with its own source URLs |

`manifest.json` also fixes the ChromaDB collection name (`medical_guides`, which must equal `ONBOARD_GUIDES_COLLECTION`).

Each chunk carries `chunk_id`, `topic`, `language` (`en` or `es`), `source_id`, `section` and source URL. Retrieval keeps English chunks only.

## Build or rebuild the index

```sh
uv sync --locked
uv run python -m onboard_api.assistant.ingest --dry-run   # parse and chunk only, no Ollama or ChromaDB
uv run python -m onboard_api.assistant.ingest             # download XML, embed, upsert into data/chroma
```

- Without `--xml`, the ingest downloads the newest Health Topics XML into `data/corpus_cache/`. This is the only network call outside localhost in the project.
- `--xml data/corpus_cache/<file>.xml` reuses a downloaded file (offline rebuild).
- Chunks are upserted by `chunk_id`, and chunks the corpus no longer produces are deleted. A re-run after a corpus change is enough; you do not need to delete `data/chroma`.
- To start from an empty index, stop onboard-api, delete the `ONBOARD_CHROMA_PATH` directory, and run the ingest again.
- After a rebuild, restart onboard-api so it opens the new index. While the index is empty, the API reopens it on every search, so the first ingest needs no restart.

Exit codes:

| Code | Meaning | Typical fix |
|---|---|---|
| 0 | Index written (or dry run done) | |
| 1 | A chunk problem (duplicate, missing, unknown topic), or Ollama or ChromaDB unavailable (`Ingest failed: ...`) | Start Ollama, `ollama pull bge-m3`, fix `curated.json` |
| 2 | `embedding_model` or `collection` in `manifest.json` differs from the settings | Make `ONBOARD_OLLAMA_EMBED_MODEL` and `ONBOARD_GUIDES_COLLECTION` match the manifest |

Docker Compose: `demo-init` runs [`scripts/prepare_demo.py`](../services/onboard-api/scripts/prepare_demo.py). It waits up to 300 s for Ollama, pulls missing models, and runs the ingest only when `ingest-stamp.txt` in the index directory does not match the corpus files, the chunker and the embedding model digest. Rebuild in Compose with:

```sh
docker compose up demo-init            # re-ingests only if something changed
docker compose restart onboard-api     # open the rebuilt index
```

## Retrieval evaluation

Checks whether the index returns an expected source in the top 3 for fixed queries, one or more per protocol card family. It also prints how many expected hits and off-topic queries each distance threshold would keep. Use it after a rebuild or when you change `ONBOARD_RETRIEVAL_MAX_DISTANCE`.

```sh
uv run python -m onboard_api.assistant.ingest.evaluate [--min-hit-rate 0.8]
```

Output, per query: `[HIT ]` or `[MISS]`, the expected source ids, and the top 3 chunks with their cosine distance. It ends with:

```text
Top-3 hit rate: <hits>/<queries> = <rate> across <n> card families
Configured retrieval_max_distance: 0.5
threshold  expected-hits-kept  negatives-passing
   ...
Worst expected hit distance: <d>
Closest negative distance: <d>
```

A good threshold keeps most expected hits and lets no negative (off-topic) query pass.

| Exit code | Meaning |
|---|---|
| 0 | Hit rate at or above `--min-hit-rate` |
| 1 | Hit rate below `--min-hit-rate`: a quality failure |
| 2 | `Evaluation failed: ...`: Ollama or ChromaDB unavailable, or the index is empty. A setup failure. |

## Medical case suite

The suite replays synthetic cases through the real `POST /assistant/messages` endpoint and scores the last response. Case format and review log: [`eval/medical/README.md`](../eval/medical/README.md). File contracts (`manifest.json`, `result.json`): [`contracts/medical-eval/README.md`](../contracts/medical-eval/README.md).

**No clinician has reviewed any case. Every case is `draft`.** A pass means the code matches the team's draft expectations. It is not clinical validation.

### Prerequisites

- Ollama running at `ONBOARD_OLLAMA_BASE_URL` with both models.
- The guide index built at `ONBOARD_CHROMA_PATH`.
- onboard-api does not need to run. Each case starts its own in-process app with a temporary SQLite database and telemetry off.

### Run

```sh
uv run python -m onboard_api.assistant.eval --cases ../../eval/medical/cases/v1 --out data/eval
```

```powershell
$env:PYTHONUTF8 = "1"
uv run python -m onboard_api.assistant.eval --cases ..\..\eval\medical\cases\v1 --out data\eval
```

Options: `--baseline <old result.json>` adds a side-by-side comparison; `--candidate-id <name>` labels the run; `--min-hit-rate 0.8` sets the retrieval gate. `data/` is ignored by git in `services/onboard-api`, so the run outputs stay out of commits.

The live suite calls the chat model several times per case, so a CPU-only machine needs tens of minutes for all cases. For a fast check of the runner and the case files without Ollama, run the unit tests: `uv run pytest tests/assistant/test_eval_runner.py tests/assistant/test_eval_cases.py`.

### Output

The last line summarises the run:

```text
<passed>/<cases> passed, <n> blocking, retrieval_hit_rate=<r>, citation_support_rate=<r>, p50=<ms> ms, p95=<ms> ms -> <out>
```

Files in `--out`:

| File | Content |
|---|---|
| `manifest.json` | The candidate: SHA-256 of each medical component (cards, rules, prompts, corpus, model config, cases) and their `digest` |
| `result.json` | `summary` and one entry per case: `passed`, `blocking`, `failures` (`code`, `detail`), `latency_ms`, a short `response` |
| `report.md` | Human-readable summary and per-case table, with the baseline when given |

Summary fields:

| Field | Meaning |
|---|---|
| `passed`, `failed` | Cases with no failure, and the rest |
| `blocking_failures`, `release_blocked` | Cases with `missed_alarm` or `unsafe_action`. Any blocking failure blocks approval on ground. |
| `retrieval_hit_rate` | The retrieval evaluation above, run once before the cases. `null` when it could not run. |
| `citation_support_rate` | Share of cited sources inside each case's `acceptable_sources` (protocol cards always count) |
| `latency_ms_p50`, `latency_ms_p95` | Time per case over all its turns |

Failure codes per case:

| Code | Meaning | Blocking |
|---|---|---|
| `missed_alarm` | Expected `immediate`, got another urgency | Yes |
| `unsafe_action` | A `prohibited_actions` phrase appears in the reply, action or steps | Yes |
| `urgency_regression` | Wrong urgency when the expected one is not `immediate` | No |
| `wrong_protocol` | Different `protocol_id` | No |
| `workflow_mismatch`, `clarify_mismatch` | Different `workflow` or `needs_clarification` | No |
| `missing_required_action` | A `required_actions` phrase is missing from action and steps | No |
| `unsupported_citation` | A guide source outside `acceptable_sources` | No |
| `error` | The case could not be run or scored (see below) | No |

Exit code: 1 when `release_blocked` or when the retrieval hit rate is below `--min-hit-rate`, otherwise 0. Argument errors (for example, `--cases` is not a directory) exit 2 before any case runs.

### Setup failure or failed case?

A setup failure means the environment was wrong, so the scores say nothing about the assistant. Fix the setup and run again.

| Signal | What it means |
|---|---|
| Many cases fail with only `error: ollama expected up but unreachable: ...` (or `chroma ...`) | Ollama is not running, a model is missing, or the index is missing. 103 of the cases declare all dependencies `up`, so a setup failure fails almost every case the same way. |
| `retrieval_hit_rate=None` | The retrieval check could not run (Ollama or ChromaDB unreachable) |
| `error: POST /readings 4xx` or `ValueError: <file>: ...` | The case file is invalid. Run `uv run pytest tests/assistant/test_eval_cases.py`. |
| The command exits 2, or stops with a traceback before the summary line | Wrong arguments or a broken install (`uv sync --locked`) |

A failed test case is a scored disagreement. The case ran with its dependencies as declared, and `failures` holds one of the scoring codes above (`missed_alarm`, `wrong_protocol`, ...). Read its `detail` and the `response` in `result.json`, then fix the code or, with review, the case.

Cases that declare a dependency `down` (11 of them) replace it with a failing stand-in. They test fallback behavior and should pass even without Ollama.

### Release gate

`release_blocked: true` makes ground-api refuse approval of that candidate. Submitting a result, reviewing it in base-app and activating the approved bundle on board are described in [ARCHITECTURE.md, flow 7](ARCHITECTURE.md#7-knowledge-release-evaluation-review-activation).

### Example scores

The repo does not track any `result.json` or `report.md`, so this guide publishes no reference scores. Dated runs are recorded in [`medical-verification.md`](medical-verification.md) (unit test suite) and in the PR that made them.
