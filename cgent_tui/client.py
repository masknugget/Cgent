"""REST client for the Cgent server.

One ``CgentClient`` owns one ``httpx.AsyncClient``; callers reuse it for the
whole command or App session. The client performs single REST calls, classifies
HTTP and protocol errors, and never prints or touches UI state.

Error taxonomy:

- ``TransientConnectionError`` — network-level failure (connect, read, write).
  A read timeout after a POST was sent means the submission result is unknown.
- ``ProtocolError`` — malformed JSON or a response that violates the contract.
- ``NotFoundError`` — 404; the invocation record does not exist.
- ``ConflictError`` — 409; the invocation is not cancellable in its state.
- ``ServerError`` — 5xx.
- ``HttpStatusError`` — any other non-success status.
"""

import json
from typing import Any, cast

import httpx

from cgent_tui.models import (
    HealthInfo,
    InvocationStatus,
    InvocationStatusLiteral,
    ToolCallStatus,
    ToolCallSummary,
    Usage,
)

MAX_DETAIL_CHARS = 600


class ClientError(Exception):
    """Base class for all client errors, carrying a human-readable detail."""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class TransientConnectionError(ClientError):
    """Network failure; may be retried for polling but never for submission."""


class ProtocolError(ClientError):
    """The server response violates the response contract."""


class NotFoundError(ClientError):
    """404 — the invocation record does not exist."""


class ConflictError(ClientError):
    """409 — the invocation cannot be cancelled in its current state."""


class ServerError(ClientError):
    """5xx — the server reported an internal error."""


class HttpStatusError(ClientError):
    """Any other non-success HTTP status."""


_TERMINAL_STATUSES = {"pending", "succeeded", "failed", "cancelled"}
_TOOL_STATUSES = {"pending", "completed", "failed"}


def _detail_from(status_code: int, body: str) -> str:
    """Extract a readable detail from an error body, capping its length."""
    text = body.strip()
    try:
        parsed = json.loads(body)
    except (ValueError, TypeError):
        parsed = None
    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message")
            if isinstance(code, str) and isinstance(message, str):
                text = f"{code}: {message}"
            elif isinstance(message, str):
                text = message
        elif isinstance(parsed.get("detail"), str):
            text = parsed["detail"]
    if not text:
        text = f"HTTP {status_code}"
    if len(text) > MAX_DETAIL_CHARS:
        text = f"{text[:MAX_DETAIL_CHARS]}…"
    return text


def _json_object(response: httpx.Response, context: str) -> dict[str, Any]:
    try:
        parsed = response.json()
    except ValueError as exc:
        raise ProtocolError(f"{context}: response is not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise ProtocolError(f"{context}: response is not a JSON object")
    return parsed


def _require_str(record: dict[str, Any], key: str, context: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        raise ProtocolError(f"{context}: missing or invalid string field {key!r}")
    return value


def _optional_str(record: dict[str, Any], key: str, context: str) -> str | None:
    value = record.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ProtocolError(f"{context}: field {key!r} must be a string or null")
    return value


def _optional_int(record: dict[str, Any], key: str, context: str) -> int | None:
    value = record.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolError(f"{context}: field {key!r} must be an integer or null")
    return value


def _parse_tool_calls(raw: Any, context: str) -> tuple[ToolCallSummary, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ProtocolError(f"{context}: 'tool_calls' must be a list")
    calls: list[ToolCallSummary] = []
    for index, item in enumerate(raw):
        item_context = f"{context}: tool_calls[{index}]"
        if not isinstance(item, dict):
            raise ProtocolError(f"{item_context} is not an object")
        name = _require_str(item, "name", item_context)
        status = _require_str(item, "status", item_context)
        if status not in _TOOL_STATUSES:
            raise ProtocolError(f"{item_context}: unknown tool status {status!r}")
        calls.append(
            ToolCallSummary(
                name=name,
                status=cast(ToolCallStatus, status),
                exit_code=_optional_int(item, "exit_code", item_context),
                error=_optional_str(item, "error", item_context),
            )
        )
    return tuple(calls)


def _parse_usage(raw: Any, context: str) -> Usage | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ProtocolError(f"{context}: 'usage' must be an object or null")
    usage_context = f"{context}: usage"
    input_tokens = _optional_int(raw, "input_tokens", usage_context)
    output_tokens = _optional_int(raw, "output_tokens", usage_context)
    total_tokens = _optional_int(raw, "total_tokens", usage_context)
    if input_tokens is None or output_tokens is None or total_tokens is None:
        raise ProtocolError(f"{context}: usage is missing a token field")
    return Usage(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
    )


def _parse_status(record: dict[str, Any], context: str) -> InvocationStatus:
    invocation_id = _require_str(record, "invocation_id", context)
    status = _require_str(record, "status", context)
    if status not in _TERMINAL_STATUSES:
        raise ProtocolError(f"{context}: unknown invocation status {status!r}")
    output = _optional_str(record, "output", context)
    if status == "succeeded" and output is None:
        raise ProtocolError(f"{context}: succeeded invocation is missing 'output'")
    error = record.get("error")
    error_code: str | None = None
    error_message: str | None = None
    if error is not None:
        if not isinstance(error, dict):
            raise ProtocolError(f"{context}: 'error' must be an object or null")
        error_code = _optional_str(error, "code", f"{context}: error")
        error_message = _optional_str(error, "message", f"{context}: error")
    return InvocationStatus(
        invocation_id=invocation_id,
        status=cast(InvocationStatusLiteral, status),
        output=output,
        tool_calls=_parse_tool_calls(record.get("tool_calls"), context),
        usage=_parse_usage(record.get("usage"), context),
        error_code=error_code,
        error_message=error_message,
    )


class CgentClient:
    """Thin async REST client for the Cgent server."""

    def __init__(
        self,
        base_url: str,
        request_timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=httpx.Timeout(request_timeout),
            trust_env=False,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "CgentClient":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()

    async def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        try:
            return await self._client.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise TransientConnectionError(f"cannot reach the server: {exc}") from exc

    @staticmethod
    def _ensure_success(response: httpx.Response, context: str) -> None:
        if response.status_code < 400:
            return
        detail = _detail_from(response.status_code, response.text)
        if response.status_code == 404:
            raise NotFoundError(detail)
        if response.status_code == 409:
            raise ConflictError(detail)
        if response.status_code >= 500:
            raise ServerError(detail)
        raise HttpStatusError(f"{context}: {detail}")

    async def health(self) -> HealthInfo:
        """``GET /health``; raises typed errors on any failure."""
        response = await self._send("GET", "/health")
        self._ensure_success(response, "health check")
        record = _json_object(response, "health check")
        status = record.get("status")
        if not isinstance(status, str) or not status:
            raise ProtocolError("health check: missing or invalid 'status'")
        return HealthInfo(status=status)

    async def submit(
        self,
        workspace_id: str,
        prompt: str,
        timeout_seconds: float | None = None,
    ) -> str:
        """``POST /v1/agent/invocations``; returns the invocation ID.

        Never retried: the API has no idempotency key, so a network failure
        after the request was sent leaves the submission result unknown.
        """
        payload: dict[str, Any] = {"input": prompt}
        if timeout_seconds is not None:
            payload["timeout_seconds"] = timeout_seconds
        response = await self._send(
            "POST",
            "/v1/agent/invocations",
            headers={"X-Workspace-ID": workspace_id},
            json=payload,
        )
        self._ensure_success(response, "submit invocation")
        record = _json_object(response, "submit invocation")
        return _require_str(record, "invocation_id", "submit invocation")

    async def get_invocation(self, invocation_id: str) -> InvocationStatus:
        """``GET /v1/agent/invocations/{id}`` with full contract validation."""
        response = await self._send("GET", f"/v1/agent/invocations/{invocation_id}")
        self._ensure_success(response, "get invocation")
        record = _json_object(response, "get invocation")
        return _parse_status(record, "get invocation")

    async def request_cancel(self, invocation_id: str) -> None:
        """``DELETE /v1/agent/invocations/{id}``; 204 means confirmed.

        Raises ``ConflictError`` when the server reports the invocation is not
        cancellable, and ``TransientConnectionError`` when the cancel result
        cannot be determined.
        """
        response = await self._send("DELETE", f"/v1/agent/invocations/{invocation_id}")
        self._ensure_success(response, "cancel invocation")
