"""Agent invocation API contracts."""

from typing import Literal

from pydantic import BaseModel, Field

from cgent.api.schemas.common import ErrorBody, ToolCallSummary, UsageResponse


class InvocationRequest(BaseModel):
    input: str = Field(min_length=1, max_length=1_000_000)
    timeout_seconds: float | None = Field(default=None, gt=0)


class InvocationAcceptedResponse(BaseModel):
    invocation_id: str
    status: Literal["pending"] = "pending"


class InvocationStatusResponse(BaseModel):
    invocation_id: str
    status: Literal["pending", "succeeded", "failed", "cancelled"]
    output: str | None = None
    tool_calls: list[ToolCallSummary] = []
    usage: UsageResponse | None = None
    error: ErrorBody | None = None
