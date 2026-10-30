"""Minimal non-streaming LangChain adapter for the official OpenAI SDK."""

import json
from collections.abc import Sequence
from typing import Any, cast

from langchain_core.callbacks import (
    AsyncCallbackManagerForLLMRun,
    CallbackManagerForLLMRun,
)
from langchain_core.language_models import BaseChatModel, LanguageModelInput
from langchain_core.language_models.base import LangSmithParams
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from openai import AsyncOpenAI, OpenAIError
from pydantic import ConfigDict

from cgent.errors import ModelUnavailableError


def _text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
            else:
                raise ValueError("Cgent P0 supports only text message content")
        return "".join(parts)
    raise ValueError("Cgent P0 supports only text message content")


def _messages(messages: Sequence[BaseMessage]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        content = _text(message.content)
        if isinstance(message, SystemMessage):
            converted.append({"role": "system", "content": content})
        elif isinstance(message, HumanMessage):
            converted.append({"role": "user", "content": content})
        elif isinstance(message, ToolMessage):
            converted.append(
                {
                    "role": "tool",
                    "content": content,
                    "tool_call_id": message.tool_call_id,
                }
            )
        elif isinstance(message, AIMessage):
            item: dict[str, Any] = {
                "role": "assistant",
                "content": content or None if message.tool_calls else content,
            }
            if message.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": call["id"],
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": json.dumps(call["args"], ensure_ascii=False),
                        },
                    }
                    for call in message.tool_calls
                ]
            converted.append(item)
        else:
            raise ValueError(f"Unsupported message type: {message.type}")
    return converted


class OpenAIChatModel(BaseChatModel):
    """The Chat Completions subset required by an in-process DeepAgent."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    client: AsyncOpenAI
    model_name: str

    @property
    def _llm_type(self) -> str:
        return "cgent-openai"

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
            "messages": _messages(messages),
            "stream": False,
            **kwargs,
        }
        if stop:
            request["stop"] = stop
        try:
            response = await self.client.chat.completions.create(**request)
        except OpenAIError as exc:
            raise ModelUnavailableError() from exc
        if not response.choices:
            raise ModelUnavailableError("The model provider returned no choices")
        choice = response.choices[0]
        message = choice.message
        tool_calls: list[dict[str, Any]] = []
        invalid_tool_calls: list[dict[str, Any]] = []
        for call in message.tool_calls or []:
            try:
                arguments = json.loads(call.function.arguments)
                if not isinstance(arguments, dict):
                    raise ValueError("Tool arguments must be a JSON object")
                tool_calls.append(
                    {
                        "name": call.function.name,
                        "args": arguments,
                        "id": call.id,
                        "type": "tool_call",
                    }
                )
            except (json.JSONDecodeError, ValueError) as exc:
                invalid_tool_calls.append(
                    {
                        "name": call.function.name,
                        "args": call.function.arguments,
                        "id": call.id,
                        "error": str(exc),
                        "type": "invalid_tool_call",
                    }
                )
        usage = response.usage
        usage_metadata = (
            {
                "input_tokens": usage.prompt_tokens,
                "output_tokens": usage.completion_tokens,
                "total_tokens": usage.total_tokens,
            }
            if usage is not None
            else None
        )
        ai_message = AIMessage(
            content=message.content or "",
            tool_calls=tool_calls,
            invalid_tool_calls=invalid_tool_calls,
            usage_metadata=usage_metadata,
            response_metadata={
                "model": response.model,
                "finish_reason": choice.finish_reason,
                "model_provider": self._llm_type,
            },
        )
        return ChatResult(generations=[ChatGeneration(message=ai_message)])

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
