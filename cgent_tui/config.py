"""Client-side configuration: environment variables and CLI flags.

Command line values take precedence over environment variables. The TUI never
reads the server's `.env` and never accepts ``HARNESS_*`` or model credentials.
"""

import math
import os
from dataclasses import dataclass
from urllib.parse import urlsplit

ENV_BASE_URL = "CGENT_TUI_BASE_URL"
ENV_WORKSPACE_ID = "CGENT_TUI_WORKSPACE_ID"
ENV_POLL_INTERVAL = "CGENT_TUI_POLL_INTERVAL"
ENV_REQUEST_TIMEOUT = "CGENT_TUI_REQUEST_TIMEOUT"

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_POLL_INTERVAL = 1.0
DEFAULT_REQUEST_TIMEOUT = 10.0

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}


class ConfigError(Exception):
    """Invalid configuration; maps to exit code 2."""


@dataclass(frozen=True, slots=True)
class TuiConfig:
    """Resolved client configuration shared by the CLI and the TUI."""

    base_url: str
    workspace_id: str | None
    poll_interval: float
    request_timeout: float


def normalize_base_url(raw: str) -> str:
    """Validate and normalize a base URL; only loopback hosts are allowed."""
    value = raw.strip()
    if not value:
        raise ConfigError("base URL must not be empty")
    if "://" not in value:
        value = f"http://{value}"
    try:
        parts = urlsplit(value)
    except ValueError as exc:
        raise ConfigError(f"invalid base URL {raw!r}: {exc}") from exc
    if parts.scheme not in {"http", "https"}:
        raise ConfigError(f"base URL must use http or https, got {parts.scheme!r}")
    host = parts.hostname
    if host is None:
        raise ConfigError(f"invalid base URL {raw!r}: missing host")
    if host.lower() not in _LOOPBACK_HOSTS:
        raise ConfigError(
            f"base URL host {host!r} is not a loopback address; "
            "Cgent TUI only connects to a local server"
        )
    if parts.username is not None or parts.password is not None:
        raise ConfigError("base URL must not contain credentials")
    if parts.query or parts.fragment:
        raise ConfigError("base URL must not contain a query string or fragment")
    normalized = f"{parts.scheme}://{parts.netloc}{parts.path}".rstrip("/")
    return normalized or f"{parts.scheme}://{parts.netloc}"


def _positive_float(env_name: str, raw: str | None, default: float) -> float:
    if raw is None or raw.strip() == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{env_name} must be a number, got {raw!r}") from exc
    if not math.isfinite(value) or value <= 0:
        raise ConfigError(f"{env_name} must be a positive finite number, got {raw!r}")
    return value


def resolve_config(
    *,
    base_url: str | None,
    workspace_id: str | None,
    poll_interval: str | None,
    request_timeout: str | None,
    environ: dict[str, str] | None = None,
) -> TuiConfig:
    """Resolve configuration with CLI flags taking precedence over the environment."""
    env = os.environ if environ is None else environ
    resolved_url = normalize_base_url(
        base_url if base_url is not None else env.get(ENV_BASE_URL, DEFAULT_BASE_URL)
    )
    resolved_workspace = (
        workspace_id if workspace_id is not None else env.get(ENV_WORKSPACE_ID) or None
    )
    resolved_poll = _positive_float(
        ENV_POLL_INTERVAL,
        poll_interval if poll_interval is not None else env.get(ENV_POLL_INTERVAL),
        DEFAULT_POLL_INTERVAL,
    )
    resolved_request_timeout = _positive_float(
        ENV_REQUEST_TIMEOUT,
        request_timeout if request_timeout is not None else env.get(ENV_REQUEST_TIMEOUT),
        DEFAULT_REQUEST_TIMEOUT,
    )
    return TuiConfig(
        base_url=resolved_url,
        workspace_id=resolved_workspace,
        poll_interval=resolved_poll,
        request_timeout=resolved_request_timeout,
    )


def require_workspace(config: TuiConfig) -> str:
    """Return the workspace ID or raise a config error (exit code 2)."""
    if not config.workspace_id:
        raise ConfigError(
            "a workspace ID is required: pass --workspace or set CGENT_TUI_WORKSPACE_ID"
        )
    return config.workspace_id
