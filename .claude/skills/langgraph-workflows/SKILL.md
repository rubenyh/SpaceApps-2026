---
name: langgraph-workflows
description: Build or change the onboard assistant LangGraph code - parent graph, intent routing and fallback, workflow subgraphs (medical), state mapping between parent and subgraph, and fake-based graph tests. Use for any work under services/onboard-api/src/onboard_api/assistant.
---

# LangGraph assistant workflows (planned)

Status: no assistant code or LangGraph dependency yet. Add in `services/onboard-api`: `uv add langgraph langchain-core`, commit `uv.lock`. Record the locked versions here once added.

## Layout (implementation guidance)
Under `services/onboard-api/src/onboard_api/`:
```text
assistant/
  graph.py              # Parent graph and workflow assembly
  routing.py            # Intent selection and fallback
  state.py              # State shared at the parent graph boundary
  workflows/
    medical/
      graph.py          # Medical workflow assembly
      state.py          # Medical workflow state
      prompts.py
      nodes/
        retrieve_readings.py
        retrieve_guides.py
        generate_answer.py
  integrations/
    ollama.py           # see ollama-local skill
    chroma.py           # see chromadb-retrieval skill
```
- Graph files only assemble (`add_node`, edges, `compile`). Logic lives in nodes and `routing.py`. Prompt text lives in `prompts.py`.
- Readings come from the shared monitoring repository (`sqlite-storage` skill). Clients in `integrations/` are created once in FastAPI lifespan and shared by all workflows.
- Pass dependencies in: `build_assistant_graph(llm, guide_retriever, repository)` builds nodes with `functools.partial`. This is what makes fakes possible in tests.
- Psychological support: possible future workflow. Do not create `workflows/psych/`, a routing branch, or prompts until the user confirms scope. Until then, route it as `unsupported` (see below).

## Shared API contract (proposed)
One route, planned `POST /assistant/messages`, same shape for every workflow:
```python
class AssistantRequest(BaseModel):
    message: str
    astronaut_id: str | None = None

class AssistantResponse(BaseModel):
    reply: str
    workflow: Literal["medical", "clarify", "unsupported"]
    needs_clarification: bool
    sources: list[GuideSource] = []     # guide id + title actually used
    data_notices: list[str] = []        # e.g. "No heart_rate reading", "spo2 is 42 min old"
    disclaimer: str | None = None       # set for medical replies
```
New workflows add a `workflow` literal value, not new fields or routes. Contract changes need main-session agreement (the console depends on it).

## Parent state and routing
```python
class AssistantState(TypedDict):
    message: str
    astronaut_id: str | None
    intent: Literal["medical", "clarify", "unsupported"] | None
    clarifying_question: str | None
    reply: str
    workflow: str
    sources: list[dict]
    data_notices: list[str]
```
`routing.py`:
- `select_intent(state, llm)` returns `{"intent": ..., "clarifying_question": ...}`. It asks the LLM for a structured label plus confidence. Invalid output, low confidence, or a message that fits several intents gives `clarify` with ONE focused question (for example "Is this about your current vital signs or about a procedure in the onboard guides?").
- Requests outside supported workflows (including psychological support, until approved) give `unsupported`: a fixed reply listing what the assistant can help with. If the message suggests an emergency or distress, the reply tells the astronaut to follow the onboard emergency procedure and contact the crew medical officer or ground flight surgeon. The assistant does not try to handle it.
- `route_after_intent(state)` returns the node name for `add_conditional_edges`.

## Parent-to-subgraph mapping
The medical subgraph has its own state, so call it from a wrapper node that maps inputs and outputs explicitly (LangGraph "call a subgraph inside a node" pattern):
```python
class MedicalState(TypedDict):
    question: str
    astronaut_id: str | None
    readings: list[Reading]
    readings_status: Literal["ok", "missing", "stale"]
    guides: list[GuideChunk]
    answer: str
    notices: list[str]

def run_medical(state: AssistantState, medical_graph) -> dict:
    out = medical_graph.invoke(
        {"question": state["message"], "astronaut_id": state["astronaut_id"]}
    )
    return {
        "workflow": "medical",
        "reply": out["answer"],
        "sources": [{"id": g.id, "title": g.title} for g in out["guides"]],
        "data_notices": out["notices"],
    }
```
- Add a compiled subgraph directly as a node only if it shares the parent's state keys. Do not leak subgraph-only keys into `AssistantState`.
- Persistence: compile the medical subgraph with the default (per-invocation) checkpointer. The parent is stateless for now; add a checkpointer keyed by a conversation id only when multi-turn context is needed.

## Medical workflow rules
- `retrieve_readings`: latest readings from the repository. No rows gives `readings_status="missing"`. Older than the configured max age gives `"stale"` with the age in `notices`.
- `retrieve_guides`: ChromaDB search; drop results under the relevance threshold. No results gives the notice "No matching onboard guide found".
- `generate_answer`: the prompt includes readings with timestamps, guide excerpts with ids, and notices. Prompt rules: never invent values or guide content, say what is missing, give informational support only, and leave diagnosis and treatment decisions to qualified personnel. Set `disclaimer`.

## Test with fakes
Run from `services/onboard-api` after `uv add --dev pytest`: `uv run pytest tests/assistant`.
- LLM: `langchain_core.language_models.fake_chat_models.GenericFakeChatModel(messages=iter([...]))`, or a tiny class with `invoke`. Script the intent output and answer text.
- Retriever: object with `search(question, k)` returning fixed `GuideChunk`s or `[]`.
- Repository: object with `latest_readings(astronaut_id)` returning fresh, old, or no rows.

Cases to keep:
1. Medical question with fresh readings and guides: `workflow == "medical"`, sources match the fake guides, disclaimer set.
2. Ambiguous message: `workflow == "clarify"`, `needs_clarification` true, exactly one question, medical subgraph not called.
3. Unsupported message, and a psychological-support message: `workflow == "unsupported"`, fixed reply.
4. Classifier returns garbage: falls back to `clarify`.
5. No readings: notice says readings missing; the answer prompt contains no invented values.
6. Stale readings: notice includes the age.
7. Empty guide results: notice says no guide found; `sources == []`.

Assert on state and response fields, not exact LLM wording. A live Ollama smoke test is optional and must skip when Ollama is down.

Docs: https://docs.langchain.com/oss/python/langgraph/use-subgraphs , https://docs.langchain.com/oss/python/langgraph/graph-api
