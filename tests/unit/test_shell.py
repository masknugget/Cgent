import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import python_command

from cgent.config import Settings
from cgent.errors import CommandRejectedError, ShellCapacityExceededError
from cgent.execution.shell import ShellService
from cgent.execution.workspace import Workspace


async def test_shell_returns_output_and_real_exit_codes(settings: Settings, tmp_path: Path) -> None:
    service = ShellService(settings)
    workspace = Workspace("test", tmp_path)
    try:
        succeeded = await service.execute(workspace, python_command("print('hello')"))
        failed = await service.execute(workspace, python_command("raise SystemExit(7)"))

        assert succeeded.status == "completed"
        assert succeeded.exit_code == 0
        assert succeeded.output.strip() == "hello"
        assert failed.status == "failed"
        assert failed.exit_code == 7
        assert service.active_count == 0
    finally:
        await service.close()


async def test_shell_timeout_terminates_process(settings: Settings, tmp_path: Path) -> None:
    service = ShellService(settings)
    try:
        result = await service.execute(
            Workspace("test", tmp_path),
            python_command("import time; time.sleep(10)"),
            timeout_seconds=0.05,
        )

        assert result.status == "timed_out"
        assert result.exit_code == 124
        assert result.duration_seconds < 3
        assert service.active_count == 0
    finally:
        await service.close()


async def test_shell_output_is_bounded(settings: Settings, tmp_path: Path) -> None:
    service = ShellService(replace(settings, shell_max_output_bytes=256))
    try:
        result = await service.execute(
            Workspace("test", tmp_path), python_command("print('x' * 4096)")
        )

        assert result.truncated
        assert "bytes truncated" in result.output
        assert len(result.output.encode("utf-8")) < 400
    finally:
        await service.close()


async def test_shell_rejects_command_before_creating_process(
    settings: Settings, tmp_path: Path
) -> None:
    service = ShellService(settings)
    try:
        with pytest.raises(CommandRejectedError):
            await service.execute(Workspace("test", tmp_path), "not-allowlisted --version")
        assert service.active_count == 0
    finally:
        await service.close()


async def test_shell_does_not_leak_service_secrets(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HARNESS_API_KEY", "service-secret")
    monkeypatch.setenv("HARNESS_MODEL_API_KEY", "model-secret")
    service = ShellService(settings)
    try:
        result = await service.execute(
            Workspace("test", tmp_path),
            python_command(
                "import os; print(os.getenv('HARNESS_API_KEY'), os.getenv('HARNESS_MODEL_API_KEY'))"
            ),
        )

        assert result.output.strip() == "None None"
        assert "service-secret" not in result.output
        assert "model-secret" not in result.output
    finally:
        await service.close()


async def test_shell_capacity_is_bounded(settings: Settings, tmp_path: Path) -> None:
    service = ShellService(
        replace(settings, max_concurrent_shells=1, shell_queue_timeout_seconds=0.01)
    )
    workspace = Workspace("test", tmp_path)
    first = asyncio.create_task(
        service.execute(workspace, python_command("import time; time.sleep(0.3)"))
    )
    try:
        for _ in range(100):
            if service.active_count:
                break
            await asyncio.sleep(0.01)
        assert service.active_count == 1

        with pytest.raises(ShellCapacityExceededError):
            await service.execute(workspace, python_command("print('second')"))
        assert (await first).status == "completed"
    finally:
        if not first.done():
            first.cancel()
        await asyncio.gather(first, return_exceptions=True)
        await service.close()
