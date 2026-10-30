"""Asynchronous, bounded process execution and cross-platform tree cleanup."""

import asyncio
import logging
import os
import signal
import subprocess
import time
from asyncio.subprocess import Process
from pathlib import Path

from cgent.config import Settings
from cgent.errors import (
    CommandRejectedError,
    ServiceStoppingError,
    ShellCapacityExceededError,
)
from cgent.execution.models import ShellExecution
from cgent.execution.output import OutputWindow
from cgent.execution.policy import ShellPolicy
from cgent.execution.workspace import Workspace
from cgent.telemetry.logging import log_event
from cgent.telemetry.request_id import new_id, reset_execution_id, set_execution_id

logger = logging.getLogger(__name__)


def _kill_process_group(process_id: int, sig: int) -> None:
    killpg = getattr(os, "killpg", None)
    if killpg is None:
        raise RuntimeError("Process groups are not supported on this platform")
    killpg(process_id, sig)


class ShellService:
    def __init__(self, settings: Settings, policy: ShellPolicy | None = None) -> None:
        self._settings = settings
        self._policy = policy if policy is not None else ShellPolicy(settings)
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_shells)
        self._active: dict[int, Process] = {}
        self._closing = False

    @property
    def active_count(self) -> int:
        return len(self._active)

    async def execute(
        self, workspace: Workspace, command: str, timeout_seconds: float | None = None
    ) -> ShellExecution:
        if self._closing:
            raise ServiceStoppingError()
        argv = self._policy.argv(command)
        timeout = self._timeout(timeout_seconds)
        execution_id = new_id("cmd")
        token = set_execution_id(execution_id)
        started = time.monotonic()
        acquired = False
        process: Process | None = None
        reader: asyncio.Task[None] | None = None
        window = OutputWindow(self._settings.shell_max_output_bytes)
        try:
            try:
                await asyncio.wait_for(
                    self._semaphore.acquire(), timeout=self._settings.shell_queue_timeout_seconds
                )
                acquired = True
            except TimeoutError as exc:
                raise ShellCapacityExceededError() from exc
            if self._closing:
                raise ServiceStoppingError()
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            process = await asyncio.create_subprocess_exec(
                *argv,
                cwd=str(workspace.root),
                env=self._policy.environment(),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                creationflags=creationflags,
                start_new_session=os.name != "nt",
            )
            self._active[process.pid] = process
            log_event(
                logger,
                logging.INFO,
                "Shell execution started",
                tool="execute",
                executable=Path(argv[0]).name,
            )
            if process.stdout is None:
                raise RuntimeError("The subprocess stdout pipe was not created")
            reader = asyncio.create_task(self._drain(process.stdout, window))
            try:
                await asyncio.wait_for(self._wait_for_completion(process, reader), timeout=timeout)
            except TimeoutError:
                await self._terminate(process)
                await self._finish_reader(reader)
                result = ShellExecution(
                    execution_id,
                    "timed_out",
                    124,
                    window.render(),
                    window.truncated,
                    time.monotonic() - started,
                )
                self._log_result(result)
                return result
            except asyncio.CancelledError:
                await self._terminate(process)
                await self._finish_reader(reader)
                raise
            exit_code = process.returncode
            result = ShellExecution(
                execution_id,
                "completed" if exit_code == 0 else "failed",
                exit_code,
                window.render(),
                window.truncated,
                time.monotonic() - started,
            )
            self._log_result(result)
            return result
        finally:
            if process is not None:
                self._active.pop(process.pid, None)
            if reader is not None and not reader.done():
                reader.cancel()
                await asyncio.gather(reader, return_exceptions=True)
            if acquired:
                self._semaphore.release()
            reset_execution_id(token)

    async def close(self) -> None:
        self._closing = True
        processes = list(self._active.values())
        if processes:
            await asyncio.gather(*(self._terminate(process) for process in processes))

    async def _drain(self, stream: asyncio.StreamReader, window: OutputWindow) -> None:
        while chunk := await stream.read(64 * 1024):
            window.add(chunk)

    @staticmethod
    async def _wait_for_completion(process: Process, reader: asyncio.Task[None]) -> None:
        await process.wait()
        await reader

    async def _finish_reader(self, reader: asyncio.Task[None]) -> None:
        if not reader.done():
            await asyncio.wait({reader}, timeout=self._settings.shell_kill_grace_seconds)
        if not reader.done():
            reader.cancel()
        await asyncio.gather(reader, return_exceptions=True)

    @staticmethod
    def _log_result(result: ShellExecution) -> None:
        log_event(
            logger,
            logging.INFO,
            "Shell execution finished",
            tool="execute",
            status=result.status,
            exit_code=result.exit_code,
            duration_seconds=round(result.duration_seconds, 3),
            truncated=result.truncated,
        )

    def _timeout(self, requested: float | None) -> float:
        if requested is None:
            return self._settings.shell_timeout_seconds
        if requested <= 0:
            raise CommandRejectedError("The command timeout must be positive")
        return min(requested, self._settings.shell_max_timeout_seconds)

    async def _terminate(self, process: Process) -> None:
        if os.name == "nt":
            await self._terminate_windows(process)
        else:
            await self._terminate_posix(process)

    async def _terminate_windows(self, process: Process) -> None:
        if process.returncode is not None:
            return
        try:
            process.send_signal(getattr(subprocess, "CTRL_BREAK_EVENT", 1))
        except (OSError, ProcessLookupError, ValueError):
            pass
        try:
            await asyncio.wait_for(process.wait(), self._settings.shell_kill_grace_seconds)
            return
        except TimeoutError:
            pass
        system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        taskkill = system_root / "System32" / "taskkill.exe"
        killer = await asyncio.create_subprocess_exec(
            str(taskkill),
            "/PID",
            str(process.pid),
            "/T",
            "/F",
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(killer.wait(), timeout=10)
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except TimeoutError:
            process.kill()
            await process.wait()

    async def _terminate_posix(self, process: Process) -> None:
        try:
            _kill_process_group(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = asyncio.get_running_loop().time() + self._settings.shell_kill_grace_seconds
        while self._process_group_exists(process.pid):
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            await asyncio.sleep(min(0.05, remaining))
        if self._process_group_exists(process.pid):
            try:
                _kill_process_group(process.pid, getattr(signal, "SIGKILL", signal.SIGTERM))
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(process.wait(), timeout=10)
        except TimeoutError:
            process.kill()
            await process.wait()

    @staticmethod
    def _process_group_exists(process_id: int) -> bool:
        try:
            _kill_process_group(process_id, 0)
        except ProcessLookupError:
            return False
        return True
