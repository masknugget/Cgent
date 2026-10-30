"""Shared conversion from LangChain messages to OpenAI Chat Completions."""

import json
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)


def message_text(content: object) -> str:
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
                raise ValueError("Cgent supports only text message content")
        return "".join(parts)
    raise ValueError("Cgent supports only text message content")


def to_openai_messages(messages: Sequence[BaseMessage]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    for message in messages:
        content = message_text(message.content)
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
