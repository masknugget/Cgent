"""Shell execution API contracts."""

from typing import Literal

from pydantic import BaseModel, Field


class ExecutionRequest(BaseModel):
    command: str = Field(min_length=1, max_length=100_000)
    timeout_seconds: float | None = Field(default=None, gt=0)


class ExecutionResponse(BaseModel):
    execution_id: str
    status: Literal["completed", "failed", "timed_out", "stopped"]
    exit_code: int | None
    output: str
    truncated: bool
    duration_seconds: float
