"""Typed API DTOs, runner states, events and outcomes.

These types are the contract between the REST client, the invocation runner,
and the CLI/TUI. No UI types and no ``httpx`` objects cross these boundaries.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Literal

ToolCallStatus = Literal["pending", "completed", "failed"]
InvocationStatusLiteral = Literal["pending", "succeeded", "failed", "cancelled"]


@dataclass(frozen=True, slots=True)
class ToolCallSummary:
    name: str
    status: ToolCallStatus
    exit_code: int | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class InvocationStatus:
    """Validated ``GET /v1/agent/invocations/{id}`` response."""

    invocation_id: str
    status: InvocationStatusLiteral
    output: str | None
    tool_calls: tuple[ToolCallSummary, ...] = ()
    usage: Usage | None = None
    error_code: str | None = None
    error_message: str | None = None


class RunnerState(Enum):
    """Client-side workflow state; never equals the server ``pending`` enum."""

    IDLE = "idle"
    SUBMITTING = "submitting"
    POLLING = "polling"
    DISCONNECTED = "disconnected"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


CancelResultKind = Literal["confirmed", "rejected", "unknown"]


@dataclass(frozen=True, slots=True)
class RunnerEvent:
    """State or progress notification emitted while a run is in flight."""

    state: RunnerState
    detail: str = ""


@dataclass(frozen=True, slots=True)
class SubmittedEvent:
    """The server accepted the invocation; carries its ID."""

    invocation_id: str


@dataclass(frozen=True, slots=True)
class CancelResultEvent:
    """Outcome of a cancel request against the server."""

    result: CancelResultKind
    detail: str = ""


@dataclass(frozen=True, slots=True)
class RunOutcome:
    """Final local result of one invocation attempt."""

    state: Literal["succeeded", "failed", "cancelled", "unknown"]
    invocation_id: str | None = None
    output: str | None = None
    tool_calls: tuple[ToolCallSummary, ...] = ()
    usage: Usage | None = None
    detail: str = ""


@dataclass(frozen=True, slots=True)
class HealthInfo:
    """Validated ``GET /health`` response."""

    status: str
