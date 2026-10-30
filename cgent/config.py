"""Validated, process-owned configuration."""

import json
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

_WORKSPACE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_DEFAULT_ENV_ALLOWLIST = (
    "PATH",
    "SYSTEMROOT",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "TEMP",
    "TMP",
)


def _integer(name: str, default: int) -> int:
    value = os.environ.get(name)
    try:
        return int(value) if value is not None else default
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _number(name: str, default: float) -> float:
    value = os.environ.get(name)
    try:
        return float(value) if value is not None else default
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _boolean(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _csv(value: str | None, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    if value is None:
        return default
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _paths(value: str | None) -> tuple[Path, ...]:
    if not value:
        return ()
    return tuple(Path(item).expanduser().resolve() for item in _csv(value))


def _decode_workspaces(value: str) -> object:
    try:
        return json.loads(value)
    except json.JSONDecodeError as original_exc:
        if "\\" not in value:
            raise ValueError("HARNESS_WORKSPACES must be a JSON object") from original_exc
        try:
            # Accept the common Windows .env form: {"project":"F:\path"}.
            return json.loads(value.replace("\\", "\\\\"))
        except json.JSONDecodeError:
            raise ValueError(
                "HARNESS_WORKSPACES must be a JSON object with forward slashes "
                "or escaped Windows backslashes"
            ) from original_exc


def _workspaces(value: str) -> dict[str, Path]:
    raw = _decode_workspaces(value)
    if not isinstance(raw, dict) or not raw:
        raise ValueError("HARNESS_WORKSPACES must be a non-empty JSON object")
    result: dict[str, Path] = {}
    for workspace_id, root in raw.items():
        if not isinstance(workspace_id, str) or not _WORKSPACE_ID.fullmatch(workspace_id):
            raise ValueError(f"Invalid workspace ID: {workspace_id!r}")
        if not isinstance(root, str) or not root.strip():
            raise ValueError(f"Workspace {workspace_id!r} must have a directory path")
        result[workspace_id] = Path(root).expanduser().resolve()
    return result


@dataclass(frozen=True, slots=True)
class Settings:
    workspaces: Mapping[str, Path]
    model: str
    model_api_key: str = field(repr=False)
    model_adapter: str = "http"
    skills_dirs: tuple[Path, ...] = ()
    host: str = "127.0.0.1"
    port: int = 8000
    model_base_url: str = "https://api.openai.com/v1"
    model_timeout_seconds: float = 600
    model_max_retries: int = 3
    agent_timeout_seconds: float = 600
    agent_max_steps: int = 50
    invocation_result_ttl_seconds: float = 600
    shell_allowlist: tuple[str, ...] = ()
    shell_timeout_seconds: float = 300
    shell_max_timeout_seconds: float = 600
    shell_max_output_bytes: int = 1024 * 1024
    max_concurrent_shells: int = 4
    shell_queue_timeout_seconds: float = 1
    shell_kill_grace_seconds: float = 2
    max_body_bytes: int = 4 * 1024 * 1024
    max_file_bytes: int = 2 * 1024 * 1024
    max_search_results: int = 1000
    shell_env_allowlist: tuple[str, ...] = _DEFAULT_ENV_ALLOWLIST
    enable_direct_tools: bool = True

    def __post_init__(self) -> None:
        for name in ("model_base_url", "host"):
            if not getattr(self, name).strip():
                raise ValueError(f"{name} must not be empty")
        if self.model_adapter not in {"http", "openai", "custom"}:
            raise ValueError("model_adapter must be http, openai or custom")
        if self.model_adapter != "custom":
            for name in ("model", "model_api_key"):
                if not getattr(self, name).strip():
                    raise ValueError(f"{name} must not be empty")
        if self.host not in _LOOPBACK_HOSTS:
            raise ValueError("host must be a loopback address")
        if not self.workspaces:
            raise ValueError("At least one workspace is required")
        for workspace_id, root in self.workspaces.items():
            if not _WORKSPACE_ID.fullmatch(workspace_id):
                raise ValueError(f"Invalid workspace ID: {workspace_id!r}")
            if not root.is_dir():
                raise ValueError(f"Workspace {workspace_id!r} is not an existing directory")
        for root in self.skills_dirs:
            if not root.is_dir():
                raise ValueError(f"Skills directory does not exist: {root}")
        for name in (
            "model_timeout_seconds",
            "agent_timeout_seconds",
            "invocation_result_ttl_seconds",
            "shell_timeout_seconds",
            "shell_max_timeout_seconds",
            "shell_max_output_bytes",
            "max_concurrent_shells",
            "max_body_bytes",
            "max_file_bytes",
            "max_search_results",
            "agent_max_steps",
            "port",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive")
        for name in ("shell_queue_timeout_seconds", "shell_kill_grace_seconds"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must not be negative")
        if self.model_max_retries < 0:
            raise ValueError("model_max_retries must not be negative")
        if self.port > 65535:
            raise ValueError("port must not exceed 65535")
        if self.shell_timeout_seconds > self.shell_max_timeout_seconds:
            raise ValueError("shell_timeout_seconds must not exceed shell_max_timeout_seconds")

    @classmethod
    def from_env(cls, dotenv_path: str | Path | None = None) -> "Settings":
        load_dotenv(dotenv_path=dotenv_path, override=False)
        required = {"HARNESS_WORKSPACES": os.environ.get("HARNESS_WORKSPACES")}
        adapter = os.environ.get("HARNESS_MODEL_ADAPTER", "http").strip().lower()
        # The custom adapter hardcodes its model config, so no model env vars are needed.
        if adapter != "custom":
            required["HARNESS_MODEL"] = os.environ.get("HARNESS_MODEL")
            required["HARNESS_MODEL_API_KEY"] = os.environ.get("HARNESS_MODEL_API_KEY")
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
        return cls(
            workspaces=_workspaces(required["HARNESS_WORKSPACES"] or ""),
            model=required.get("HARNESS_MODEL") or "",
            model_api_key=required.get("HARNESS_MODEL_API_KEY") or "",
            model_adapter=adapter,
            skills_dirs=_paths(os.environ.get("HARNESS_SKILLS_DIRS")),
            host=os.environ.get("HARNESS_HOST", "127.0.0.1"),
            port=_integer("HARNESS_PORT", 8000),
            model_base_url=os.environ.get(
                "HARNESS_MODEL_BASE_URL", "https://api.openai.com/v1"
            ).rstrip("/"),
            model_timeout_seconds=_number("HARNESS_MODEL_TIMEOUT_SECONDS", 600),
            model_max_retries=_integer("HARNESS_MODEL_MAX_RETRIES", 3),
            agent_timeout_seconds=_number("HARNESS_AGENT_TIMEOUT_SECONDS", 600),
            agent_max_steps=_integer("HARNESS_AGENT_MAX_STEPS", 50),
            invocation_result_ttl_seconds=_number("HARNESS_INVOCATION_RESULT_TTL_SECONDS", 600),
            shell_allowlist=_csv(os.environ.get("HARNESS_SHELL_ALLOWLIST")),
            shell_timeout_seconds=_number("HARNESS_SHELL_TIMEOUT_SECONDS", 300),
            shell_max_timeout_seconds=_number("HARNESS_SHELL_MAX_TIMEOUT_SECONDS", 600),
            shell_max_output_bytes=_integer("HARNESS_SHELL_MAX_OUTPUT_BYTES", 1024 * 1024),
            max_concurrent_shells=_integer("HARNESS_MAX_CONCURRENT_SHELLS", 4),
            shell_queue_timeout_seconds=_number("HARNESS_SHELL_QUEUE_TIMEOUT_SECONDS", 1),
            shell_kill_grace_seconds=_number("HARNESS_SHELL_KILL_GRACE_SECONDS", 2),
            max_body_bytes=_integer("HARNESS_MAX_BODY_BYTES", 4 * 1024 * 1024),
            max_file_bytes=_integer("HARNESS_MAX_FILE_BYTES", 2 * 1024 * 1024),
            max_search_results=_integer("HARNESS_MAX_SEARCH_RESULTS", 1000),
            shell_env_allowlist=_csv(
                os.environ.get("HARNESS_SHELL_ENV_ALLOWLIST"), _DEFAULT_ENV_ALLOWLIST
            ),
            enable_direct_tools=_boolean("HARNESS_ENABLE_DIRECT_TOOLS", True),
        )
