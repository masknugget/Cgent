"""A wall-clock deadline around each provider call.

The timeout middleware pattern is adapted from Open SWE (MIT).
"""

import asyncio
from collections.abc import Awaitable, Callable

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse

from cgent.errors import ModelUnavailableError


class ModelCallTimeoutMiddleware(AgentMiddleware):
    def __init__(self, timeout_seconds: float) -> None:
        super().__init__()
        self._timeout_seconds = timeout_seconds

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        try:
            return await asyncio.wait_for(handler(request), timeout=self._timeout_seconds)
        except TimeoutError as exc:
            raise ModelUnavailableError("The model call exceeded its deadline") from exc
