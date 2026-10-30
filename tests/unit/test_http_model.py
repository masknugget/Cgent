from dataclasses import replace

import pytest
import requests
from langchain_core.messages import AIMessage, HumanMessage

from cgent.config import Settings
from cgent.errors import ModelUnavailableError
from cgent.models.factory import ModelFactory
from cgent.models.http_chat import OpenAICompatibleHTTPModel
from cgent.models.openai_chat import OpenAIChatModel


class FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> object:
        return self._payload


def model() -> OpenAICompatibleHTTPModel:
    return OpenAICompatibleHTTPModel(
        api_key="model-secret",
        base_url="https://provider.example/v1/",
        model_name="test-model",
        timeout_seconds=7,
    )


async def test_http_model_sends_openai_compatible_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_post(**kwargs: object) -> FakeResponse:
        captured.update(kwargs)
        return FakeResponse(
            {
                "id": "chat-1",
                "model": "test-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "你好！"},
                    }
                ],
                "usage": {
                    "prompt_tokens": 4,
                    "completion_tokens": 3,
                    "total_tokens": 7,
                },
            }
        )

    monkeypatch.setattr(requests, "post", fake_post)

    message = await model().ainvoke(
        [HumanMessage(content="你好")],
        stop=["END"],
    )

    assert isinstance(message, AIMessage)
    assert message.content == "你好！"
    assert message.usage_metadata == {
        "input_tokens": 4,
        "output_tokens": 3,
        "total_tokens": 7,
    }
    assert captured["url"] == "https://provider.example/v1/chat/completions"
    assert captured["timeout"] == 7
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["Authorization"] == "Bearer model-secret"
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["model"] == "test-model"
    assert payload["stream"] is False
    assert payload["stop"] == ["END"]
    assert payload["messages"] == [{"role": "user", "content": "你好"}]


async def test_http_model_parses_tool_calls_and_tool_choice(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_post(**kwargs: object) -> FakeResponse:
        captured.update(kwargs)
        return FakeResponse(
            {
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call-write",
                                    "type": "function",
                                    "function": {
                                        "name": "write_file",
                                        "arguments": '{"file_path":"/a.txt","content":"x"}',
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        )

    monkeypatch.setattr(requests, "post", fake_post)
    bound = model().bind_tools([], tool_choice="any")

    message = await bound.ainvoke([HumanMessage(content="create a file")])

    assert isinstance(message, AIMessage)
    assert message.tool_calls == [
        {
            "name": "write_file",
            "args": {"file_path": "/a.txt", "content": "x"},
            "id": "call-write",
            "type": "tool_call",
        }
    ]
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["tool_choice"] == "required"


async def test_http_model_maps_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def unavailable_post(**kwargs: object) -> FakeResponse:
        return FakeResponse({"error": "unavailable"}, status_code=503)

    monkeypatch.setattr(requests, "post", unavailable_post)

    with pytest.raises(ModelUnavailableError, match="HTTP 503"):
        await model().ainvoke([HumanMessage(content="hi")])


async def test_http_model_maps_request_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_post(**kwargs: object) -> FakeResponse:
        raise requests.ConnectionError("offline")

    monkeypatch.setattr(requests, "post", failing_post)

    with pytest.raises(ModelUnavailableError, match="model request failed"):
        await model().ainvoke([HumanMessage(content="hi")])


async def test_model_factory_uses_http_adapter_by_default(settings: Settings) -> None:
    factory = ModelFactory(settings)
    try:
        assert isinstance(factory.model, OpenAICompatibleHTTPModel)
        assert factory.model.model_name == "fake-model"
    finally:
        await factory.aclose()


async def test_model_factory_can_use_openai_sdk_adapter(settings: Settings) -> None:
    factory = ModelFactory(replace(settings, model_adapter="openai"))
    try:
        assert isinstance(factory.model, OpenAIChatModel)
    finally:
        await factory.aclose()


def test_settings_reject_unknown_model_adapter(settings: Settings) -> None:
    with pytest.raises(ValueError, match="model_adapter"):
        replace(settings, model_adapter="unknown")
