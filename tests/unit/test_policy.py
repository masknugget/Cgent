import os
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import python_command

from cgent.config import Settings
from cgent.errors import CommandRejectedError
from cgent.execution.policy import ShellPolicy, command_line_to_argv


def test_policy_parses_argv_and_pins_allowlisted_executable(settings: Settings) -> None:
    policy = ShellPolicy(settings)

    argv = policy.argv(python_command("print('ok')"))

    assert argv[0] == str(Path(sys.executable).resolve())
    assert argv[1:] == ["-c", "print('ok')"]


def test_policy_rejects_unlisted_and_explicit_executables(settings: Settings) -> None:
    policy = ShellPolicy(settings)

    with pytest.raises(CommandRejectedError):
        policy.argv("definitely-not-allowlisted --version")
    with pytest.raises(CommandRejectedError):
        policy.argv(f'"{sys.executable}" -c "pass"')


def test_shell_environment_contains_only_allowed_non_secret_values(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = replace(
        settings,
        shell_env_allowlist=("PATH", "CGENT_TEST_VALUE", "HARNESS_API_KEY", "OPENAI_API_KEY"),
    )
    monkeypatch.setenv("CGENT_TEST_VALUE", "visible")
    monkeypatch.setenv("HARNESS_API_KEY", "service-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "model-secret")
    monkeypatch.setenv("UNRELATED_SECRET", "hidden")

    environment = ShellPolicy(settings).environment()

    assert environment["CGENT_TEST_VALUE"] == "visible"
    assert "HARNESS_API_KEY" not in environment
    assert "OPENAI_API_KEY" not in environment
    assert "UNRELATED_SECRET" not in environment


def test_posix_style_command_parser_handles_quotes() -> None:
    if os.name == "nt":
        pytest.skip("POSIX parser is used on non-Windows platforms")

    assert command_line_to_argv("python -c 'print(\"hello world\")'") == [
        "python",
        "-c",
        'print("hello world")',
    ]
