"""Shared API contracts."""

from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["healthy"] = "healthy"


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
    request_id: str


class ToolDescriptor(BaseModel):
    name: str
    description: str
    method: str
    path: str
    input_schema: dict[str, object]


class ToolsResponse(BaseModel):
    tools: list[ToolDescriptor]


class UsageResponse(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int


class ToolCallSummary(BaseModel):
    name: str
    status: Literal["pending", "completed", "failed"]
    exit_code: int | None = None
    error: str | None = None
