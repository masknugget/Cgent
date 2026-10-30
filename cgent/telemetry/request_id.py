"""Request and execution identifiers propagated through logs and responses."""

import re
from contextvars import ContextVar, Token
from uuid import uuid4

_REQUEST_ID = re.compile(r"^req_[0-9a-f-]{36}$")
_request_id: ContextVar[str] = ContextVar("cgent_request_id", default="")
_invocation_id: ContextVar[str] = ContextVar("cgent_invocation_id", default="")
_execution_id: ContextVar[str] = ContextVar("cgent_execution_id", default="")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4()}"


def normalize_request_id(candidate: str | None) -> str:
    return candidate if candidate and _REQUEST_ID.fullmatch(candidate) else new_id("req")


def set_request_id(value: str) -> Token[str]:
    return _request_id.set(value)


def reset_request_id(token: Token[str]) -> None:
    _request_id.reset(token)


def current_request_id() -> str:
    return _request_id.get()


def set_invocation_id(value: str) -> Token[str]:
    return _invocation_id.set(value)


def current_invocation_id() -> str:
    return _invocation_id.get()


def reset_invocation_id(token: Token[str]) -> None:
    _invocation_id.reset(token)


def set_execution_id(value: str) -> Token[str]:
    return _execution_id.set(value)


def reset_execution_id(token: Token[str]) -> None:
    _execution_id.reset(token)


def current_execution_id() -> str:
    return _execution_id.get()
