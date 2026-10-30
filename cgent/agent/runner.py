"""Synchronous invocation boundary, tool summaries and cancellation."""

import asyncio
import logging
from dataclasses import dataclass
from typing import Literal

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError

from cgent.agent.factory import AgentFactory
from cgent.config import Settings
from cgent.errors import (
    AgentStepLimitError,
    AgentTimeoutError,
    ModelUnavailableError,
    ServiceStoppingError,
)
from cgent.telemetry.logging import log_event
from cgent.telemetry.request_id import new_id, reset_invocation_id, set_invocation_id

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ToolSummary:
    name: str
    status: Literal["pending", "completed", "failed"]
    exit_code: int | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class InvocationResult:
    invocation_id: str
    status: Literal["succeeded"]
    output: str
    tool_calls: list[ToolSummary]
    usage: Usage | None


def message_text(message: BaseMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    parts: list[str] = []
    for block in message.content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "\n".join(parts)


class AgentRunner:
    def __init__(self, settings: Settings, factory: AgentFactory) -> None:
        self._settings = settings
        self._factory = factory
        self._active: set[asyncio.Task[object]] = set()
        self._closing = False

    async def invoke(
        self,
        workspace_id: str,
        text: str,
        timeout_seconds: float | None = None,
        invocation_id: str | None = None,
    ) -> InvocationResult:
        if self._closing:
            raise ServiceStoppingError()
        invocation_id = invocation_id or new_id("inv")
        token = set_invocation_id(invocation_id)
        task = asyncio.current_task()
        if task is not None:
            self._active.add(task)
        timeout = self._timeout(timeout_seconds)
        started = asyncio.get_running_loop().time()
        try:
            agent = self._factory.create(workspace_id)
            try:
                result = await asyncio.wait_for(
                    agent.ainvoke(
                        {"messages": [HumanMessage(content=text)]},
                        {"recursion_limit": self._settings.agent_max_steps},
                    ),
                    timeout=timeout,
                )
            except TimeoutError as exc:
                raise AgentTimeoutError() from exc
            except GraphRecursionError as exc:
                raise AgentStepLimitError() from exc
            messages = self._messages(result)
            output = self._final_text(messages)
            invocation = InvocationResult(
                invocation_id=invocation_id,
                status="succeeded",
                output=output,
                tool_calls=self._tool_summaries(messages),
                usage=self._usage(messages),
            )
            log_event(
                logger,
                logging.INFO,
                "Agent invocation finished",
                status=invocation.status,
                tool_call_count=len(invocation.tool_calls),
                duration_seconds=round(asyncio.get_running_loop().time() - started, 3),
            )
            return invocation
        finally:
            if task is not None:
                self._active.discard(task)
            reset_invocation_id(token)

    async def close(self) -> None:
        self._closing = True
        current = asyncio.current_task()
        tasks = [task for task in self._active if task is not current]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _timeout(self, requested: float | None) -> float:
        if requested is None:
            return self._settings.agent_timeout_seconds
        if requested <= 0:
            raise ValueError("The invocation timeout must be positive")
        return min(requested, self._settings.agent_timeout_seconds)

    @staticmethod
    def _messages(result: dict[str, object]) -> list[BaseMessage]:
        values = result.get("messages", [])
        if not isinstance(values, list) or not all(
            isinstance(item, BaseMessage) for item in values
        ):
            raise ModelUnavailableError("The Agent returned an invalid message state")
        return values

    @staticmethod
    def _final_text(messages: list[BaseMessage]) -> str:
        for message in reversed(messages):
            if isinstance(message, AIMessage):
                text = message_text(message)
                if text:
                    return text
        raise ModelUnavailableError("The Agent completed without a final response")

    @staticmethod
    def _tool_summaries(messages: list[BaseMessage]) -> list[ToolSummary]:
        summaries: list[ToolSummary] = []
        positions: dict[str, int] = {}
        for message in messages:
            if isinstance(message, AIMessage):
                for call in message.tool_calls:
                    call_id = call.get("id")
                    if isinstance(call_id, str):
                        positions[call_id] = len(summaries)
                    summaries.append(ToolSummary(name=call["name"], status="pending"))
            elif isinstance(message, ToolMessage):
                index = positions.get(message.tool_call_id)
                if index is None:
                    continue
                previous = summaries[index]
                artifact = message.artifact if isinstance(message.artifact, dict) else {}
                exit_code = artifact.get("exit_code")
                summaries[index] = ToolSummary(
                    name=previous.name,
                    status="failed" if message.status == "error" else "completed",
                    exit_code=exit_code if isinstance(exit_code, int) else None,
                    error=message_text(message)[:500] if message.status == "error" else None,
                )
        return summaries

    @staticmethod
    def _usage(messages: list[BaseMessage]) -> Usage | None:
        usages = [
            message.usage_metadata
            for message in messages
            if isinstance(message, AIMessage) and message.usage_metadata is not None
        ]
        if not usages:
            return None
        return Usage(
            input_tokens=sum(item["input_tokens"] for item in usages),
            output_tokens=sum(item["output_tokens"] for item in usages),
            total_tokens=sum(item["total_tokens"] for item in usages),
        )
