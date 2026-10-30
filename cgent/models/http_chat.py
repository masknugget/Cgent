"""Non-streaming OpenAI-compatible chat model backed by requests."""

import asyncio
import json
from collections.abc import Sequence
from typing import Any, cast

import requests
from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.language_models.base import LangSmithParams
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import ConfigDict, Field

from cgent.errors import ModelUnavailableError
from cgent.models.openai_messages import to_openai_messages


class OpenAICompatibleHTTPModel(BaseChatModel):
    """OpenAI-compatible Chat Completions client using direct HTTP requests."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    api_key: str = Field(repr=False)
    base_url: str
    model_name: str
    timeout_seconds: float

    @property
    def _llm_type(self) -> str:
        return "cgent-openai-http"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model_name": self.model_name, "model_provider": self._llm_type}

    def _get_ls_params(self, stop: list[str] | None = None, **kwargs: Any) -> LangSmithParams:
        params = super()._get_ls_params(stop=stop, **kwargs)
        params["ls_provider"] = self._llm_type
        params["ls_model_name"] = self.model_name
        return params

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        raise NotImplementedError("Cgent uses asynchronous model invocation")

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        request: dict[str, Any] = {
            "model": self.model_name,
            "messages": to_openai_messages(messages),
            "stream": False,
            **kwargs,
        }
        if stop:
            request["stop"] = stop

        def call_provider() -> requests.Response:
            return requests.post(
                url=f"{self.base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=request,
                timeout=self.timeout_seconds,
            )

        try:
            response = await asyncio.to_thread(call_provider)
        except requests.RequestException as exc:
            raise ModelUnavailableError("The model request failed") from exc
        if response.status_code >= 400:
            raise ModelUnavailableError(f"The model provider returned HTTP {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise ModelUnavailableError("The model provider returned invalid JSON") from exc
        return self._result_from_payload(data)

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Any | BaseTool],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable[LanguageModelInput, AIMessage]:
        formatted = [convert_to_openai_tool(tool) for tool in tools]
        if tool_choice is not None:
            kwargs["tool_choice"] = "required" if tool_choice == "any" else tool_choice
        return cast(
            Runnable[LanguageModelInput, AIMessage],
            self.bind(tools=formatted, **kwargs),
        )

    def _result_from_payload(self, data: object) -> ChatResult:
        if not isinstance(data, dict):
            raise ModelUnavailableError("The model provider returned an invalid response")
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ModelUnavailableError("The model provider returned no choices")
        choice = choices[0]
        message = choice.get("message")
        if not isinstance(message, dict):
            raise ModelUnavailableError("The model provider returned no message")

        raw_content = message.get("content")
        content = raw_content if isinstance(raw_content, str) else ""
        tool_calls, invalid_tool_calls = self._tool_calls(message)
        usage_metadata = self._usage_metadata(data.get("usage"))
        raw_model = data.get("model")
        raw_finish_reason = choice.get("finish_reason")
        ai_message = AIMessage(
            content=content,
            tool_calls=tool_calls,
            invalid_tool_calls=invalid_tool_calls,
            usage_metadata=usage_metadata,
            response_metadata={
                "model": raw_model if isinstance(raw_model, str) else self.model_name,
                "finish_reason": (
                    raw_finish_reason if isinstance(raw_finish_reason, str) else None
                ),
                "model_provider": self._llm_type,
            },
        )
        return ChatResult(generations=[ChatGeneration(message=ai_message)])

    @staticmethod
    def _tool_calls(message: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        raw_calls = message.get("tool_calls")
        if raw_calls is None:
            return [], []
        if not isinstance(raw_calls, list):
            return [], [
                {
                    "name": None,
                    "args": None,
                    "id": None,
                    "error": "tool_calls must be a list",
                    "type": "invalid_tool_call",
                }
            ]
        tool_calls: list[dict[str, Any]] = []
        invalid_tool_calls: list[dict[str, Any]] = []
        for item in raw_calls:
            try:
                if not isinstance(item, dict):
                    raise ValueError("A tool call must be an object")
                call_id = item.get("id")
                function = item.get("function")
                if not isinstance(call_id, str) or not isinstance(function, dict):
                    raise ValueError("A tool call requires an ID and function object")
                name = function.get("name")
                arguments = function.get("arguments")
                if not isinstance(name, str) or not isinstance(arguments, str):
                    raise ValueError("A tool call requires a name and JSON arguments")
                parsed_arguments = json.loads(arguments)
                if not isinstance(parsed_arguments, dict):
                    raise ValueError("Tool arguments must be a JSON object")
                tool_calls.append(
                    {
                        "name": name,
                        "args": parsed_arguments,
                        "id": call_id,
                        "type": "tool_call",
                    }
                )
            except (json.JSONDecodeError, ValueError) as exc:
                invalid_tool_calls.append(
                    {
                        "name": item.get("function", {}).get("name")
                        if isinstance(item, dict)
                        else None,
                        "args": item.get("function", {}).get("arguments")
                        if isinstance(item, dict)
                        else None,
                        "id": item.get("id") if isinstance(item, dict) else None,
                        "error": str(exc),
                        "type": "invalid_tool_call",
                    }
                )
        return tool_calls, invalid_tool_calls

    @staticmethod
    def _usage_metadata(usage: object) -> dict[str, int] | None:
        if not isinstance(usage, dict):
            return None
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        total_tokens = usage.get("total_tokens")
        if (
            not isinstance(input_tokens, int)
            or not isinstance(output_tokens, int)
            or not isinstance(total_tokens, int)
        ):
            return None
        return {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
        }
