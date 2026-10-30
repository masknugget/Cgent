from dataclasses import replace

import pytest
import requests
from langchain_core.messages import AIMessage, HumanMessage

from cgent.config import Settings
from cgent.errors import ModelUnavailableError
from cgent.models.custom_chat import BASE_URL, MAX_TOKENS, MODEL, USER_ID, CustomChatModel
from cgent.models.factory import ModelFactory


class FakeResponse:
    def __init__(self, payload: object, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> object:
        return self._payload


def model() -> CustomChatModel:
    return CustomChatModel(timeout_seconds=7)


async def test_custom_model_sends_gaip_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_jwt() -> str:
        return "dsp-jwt-token"

    def fake_post(**kwargs: object) -> FakeResponse:
        captured.update(kwargs)
        return FakeResponse(
            {
                "id": "chat-1",
                "model": MODEL,
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

    monkeypatch.setattr("cgent.models.custom_chat._get_service_account_jwt", fake_jwt)
    monkeypatch.setattr(requests, "post", fake_post)

    message = await model().ainvoke([HumanMessage(content="你好")])

    assert isinstance(message, AIMessage)
    assert message.content == "你好！"
    assert captured["url"] == BASE_URL
    assert captured["timeout"] == 7
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers["X-HSBC-E2E-Trust-Token"] == "dsp-jwt-token"
    assert headers["Content-Type"] == "application/json"
    assert headers["x-correlation-id"] != headers["x-usersession-id"]
    payload = captured["json"]
    assert isinstance(payload, dict)
    assert payload["model"] == MODEL
    assert payload["stream"] is False
    assert payload["max_tokens"] == MAX_TOKENS
    assert payload["user"] == USER_ID
    assert payload["messages"] == [{"role": "user", "content": "你好"}]


async def test_custom_model_maps_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cgent.models.custom_chat._get_service_account_jwt", lambda: "jwt")

    def unavailable_post(**kwargs: object) -> FakeResponse:
        return FakeResponse({"error": "unavailable"}, status_code=503)

    monkeypatch.setattr(requests, "post", unavailable_post)

    with pytest.raises(ModelUnavailableError, match="HTTP 503"):
        await model().ainvoke([HumanMessage(content="hi")])


async def test_custom_model_rejects_missing_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    def missing_jwt() -> str:
        raise ModelUnavailableError("JWT not found in response: {}")

    monkeypatch.setattr("cgent.models.custom_chat._get_service_account_jwt", missing_jwt)

    with pytest.raises(ModelUnavailableError, match="JWT not found"):
        await model().ainvoke([HumanMessage(content="hi")])


async def test_model_factory_uses_custom_adapter(settings: Settings) -> None:
    factory = ModelFactory(replace(settings, model_adapter="custom"))
    try:
        assert isinstance(factory.model, CustomChatModel)
        assert factory.model.model_name == MODEL
        assert factory.model.timeout_seconds == settings.model_timeout_seconds
    finally:
        await factory.aclose()


def test_settings_allow_custom_adapter_without_model_config(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replaced = replace(settings, model="", model_api_key="", model_adapter="custom")
    assert replaced.model_adapter == "custom"

    monkeypatch.setenv("HARNESS_WORKSPACES", '{"test": "F:/templates/Cgent"}')
    monkeypatch.setenv("HARNESS_MODEL_ADAPTER", "custom")
    monkeypatch.delenv("HARNESS_MODEL", raising=False)
    monkeypatch.delenv("HARNESS_MODEL_API_KEY", raising=False)
    loaded = Settings.from_env()
    assert loaded.model_adapter == "custom"
    assert loaded.model == ""
    assert loaded.model_api_key == ""
