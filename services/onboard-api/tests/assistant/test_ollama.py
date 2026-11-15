import json

import httpx
import pytest

from onboard_api.assistant.integrations import DependencyUnavailable
from onboard_api.assistant.integrations.ollama import OllamaClient


def client(handler) -> OllamaClient:
    return OllamaClient(
        "http://ollama.test", "chat-model", "embed-model", 5.0,
        transport=httpx.MockTransport(handler),
    )


def test_chat_ok() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "hola"}})

    assert client(handler).chat("sistema", "pregunta") == "hola"
    body = seen["body"]
    assert seen["path"] == "/api/chat"
    assert body["model"] == "chat-model"
    assert body["stream"] is False
    assert body["options"]["temperature"] <= 0.2
    assert body["messages"] == [
        {"role": "system", "content": "sistema"},
        {"role": "user", "content": "pregunta"},
    ]


@pytest.mark.parametrize(
    "handler",
    [
        pytest.param(lambda r: (_ for _ in ()).throw(httpx.ReadTimeout("slow", request=r)), id="timeout"),
        pytest.param(lambda r: (_ for _ in ()).throw(httpx.ConnectError("down", request=r)), id="down"),
        pytest.param(lambda r: httpx.Response(404, json={"error": "model not found"}), id="http-error"),
        pytest.param(lambda r: httpx.Response(200, json={"unexpected": True}), id="bad-shape"),
    ],
)
def test_chat_failures_raise_dependency_unavailable(handler) -> None:
    with pytest.raises(DependencyUnavailable):
        client(handler).chat("s", "u")


def test_embed_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/api/embed"
        assert body == {"model": "embed-model", "input": ["a", "b"]}
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2], [0.3, 0.4]]})

    assert client(handler).embed(["a", "b"]) == [[0.1, 0.2], [0.3, 0.4]]


def test_embed_count_mismatch_raises() -> None:
    handler = lambda r: httpx.Response(200, json={"embeddings": [[0.1]]})
    with pytest.raises(DependencyUnavailable):
        client(handler).embed(["a", "b"])


def test_model_digest() -> None:
    tags = {"models": [{"name": "embed-model:latest", "model": "embed-model:latest", "digest": "abc"}]}
    handler = lambda r: httpx.Response(200, json=tags)
    assert client(handler).model_digest("embed-model") == "abc"
    with pytest.raises(DependencyUnavailable):
        client(handler).model_digest("missing")


def test_chat_json_sends_schema_and_uses_the_short_timeout() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["timeout"] = request.extensions["timeout"]["read"]
        return httpx.Response(200, json={"message": {"content": '{"observations": []}'}})

    llm = OllamaClient("http://ollama.test", "chat-model", "embed-model", 20.0,
                       transport=httpx.MockTransport(handler), json_timeout_seconds=3.0)
    schema = {"type": "object"}
    assert llm.chat_json("s", "u", schema) == '{"observations": []}'
    assert seen["body"]["format"] == schema and seen["timeout"] == 3.0
