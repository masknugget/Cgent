"""Cross-platform argv parsing, executable allowlisting and sanitized environments."""

import ctypes
import os
import shlex
import shutil
from ctypes import wintypes
from pathlib import Path

from cgent.config import Settings
from cgent.errors import CommandRejectedError

_FORBIDDEN_ENV = {
    "HARNESS_API_KEY",
    "HARNESS_MODEL_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GOOGLE_API_KEY",
    "AWS_SECRET_ACCESS_KEY",
    "GITHUB_TOKEN",
}


def windows_command_line_to_argv(command: str) -> list[str]:
    """Parse using the same Windows rules as CommandLineToArgvW."""
    if not command.strip():
        raise CommandRejectedError("The command must not be empty")
    windll = getattr(ctypes, "windll", None)
    if windll is None:
        raise CommandRejectedError("P0 Shell execution is supported only on Windows")
    parse = windll.shell32.CommandLineToArgvW
    parse.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_int)]
    parse.restype = ctypes.POINTER(wintypes.LPWSTR)
    count = ctypes.c_int()
    pointer = parse(command, ctypes.byref(count))
    if not pointer:
        raise CommandRejectedError("The command could not be parsed")
    try:
        argv = [pointer[index] for index in range(count.value)]
    finally:
        windll.kernel32.LocalFree(pointer)
    if not argv or not argv[0]:
        raise CommandRejectedError("The command must include an executable")
    return argv


def command_line_to_argv(command: str) -> list[str]:
    """Parse a command without invoking a command shell."""
    if os.name == "nt":
        return windows_command_line_to_argv(command)
    if not command.strip():
        raise CommandRejectedError("The command must not be empty")
    try:
        argv = shlex.split(command, posix=True)
    except ValueError as exc:
        raise CommandRejectedError("The command could not be parsed") from exc
    if not argv or not argv[0]:
        raise CommandRejectedError("The command must include an executable")
    return argv


class ShellPolicy:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._executables: dict[str, str] = {}
        for configured in settings.shell_allowlist:
            resolved = shutil.which(configured)
            if resolved is None or not Path(resolved).is_file():
                raise ValueError(f"Allowlisted executable was not found: {configured}")
            path = str(Path(resolved).resolve())
            self._executables[Path(configured).name.lower()] = path
            self._executables[Path(path).name.lower()] = path

    def argv(self, command: str) -> list[str]:
        argv = command_line_to_argv(command)
        executable = argv[0]
        if Path(executable).name != executable or "/" in executable or "\\" in executable:
            raise CommandRejectedError("Use an allowlisted executable name, not a path")
        resolved = self._executables.get(executable.lower())
        if resolved is None:
            raise CommandRejectedError()
        return [resolved, *argv[1:]]

    def environment(self) -> dict[str, str]:
        allowed = {name.upper() for name in self._settings.shell_env_allowlist}
        environment: dict[str, str] = {}
        for name, value in os.environ.items():
            upper = name.upper()
            if (
                upper in allowed
                and upper not in _FORBIDDEN_ENV
                and not upper.startswith("HARNESS_")
            ):
                environment[name] = value
        return environment
