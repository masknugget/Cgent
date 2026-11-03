"""Background REST service for the desktop UI."""

from __future__ import annotations

import asyncio

from PySide6.QtCore import QObject, QThread, Signal, Slot

from cgent_tui.client import CgentClient, ClientError
from cgent_tui.models import CancelResultEvent, RunnerEvent, RunOutcome, SubmittedEvent
from cgent_tui.runner import InvocationRunner


class _ApiWorker(QObject):
    healthOk = Signal(str)
    healthFailed = Signal(str)
    submitted = Signal(str)
    progress = Signal(str)
    finished = Signal(object)

    def __init__(
        self,
        base_url: str,
        workspace_id: str,
        request_timeout: float,
        poll_interval: float,
    ) -> None:
        super().__init__()
        self._base_url = base_url
        self._workspace_id = workspace_id
        self._request_timeout = request_timeout
        self._poll_interval = poll_interval
        self._runner: InvocationRunner | None = None

    def request_cancel(self) -> None:
        runner = self._runner
        if runner is not None:
            runner.request_cancel()

    @Slot()
    def health_check(self) -> None:
        asyncio.run(self._health())

    async def _health(self) -> None:
        client = CgentClient(self._base_url, self._request_timeout)
        try:
            info = await client.health()
        except ClientError as exc:
            self.healthFailed.emit(exc.detail)
        else:
            self.healthOk.emit(info.status)
        finally:
            await client.aclose()

    @Slot(str, object)
    def run(self, prompt: str, overall_timeout: float | None) -> None:
        outcome = asyncio.run(self._run(prompt, overall_timeout))
        self.finished.emit(outcome)

    async def _run(self, prompt: str, overall_timeout: float | None) -> RunOutcome:
        client = CgentClient(self._base_url, self._request_timeout)
        runner = InvocationRunner(
            client,
            self._workspace_id,
            poll_interval=self._poll_interval,
            overall_timeout=overall_timeout,
        )
        self._runner = runner

        def on_event(event: RunnerEvent | SubmittedEvent | CancelResultEvent) -> None:
            if isinstance(event, SubmittedEvent):
                self.submitted.emit(event.invocation_id)
                self.progress.emit(f"已提交 invocation {event.invocation_id}")
            elif isinstance(event, CancelResultEvent):
                self.progress.emit(event.detail)
            elif event.detail:
                self.progress.emit(event.detail)

        try:
            return await runner.run(prompt, on_event=on_event)
        except Exception as exc:
            return RunOutcome(state="failed", detail=f"桌面服务执行失败：{exc}")
        finally:
            self._runner = None
            await client.aclose()


class CgentService(QObject):
    """Owns the worker thread; all public signals are delivered to the UI thread."""

    healthOk = Signal(str)
    healthFailed = Signal(str)
    runStarted = Signal()
    submitted = Signal(str)
    progress = Signal(str)
    outputReady = Signal(object)
    runFinished = Signal(object)
    _healthRequested = Signal()
    _runRequested = Signal(str, object)

    def __init__(
        self,
        base_url: str,
        workspace_id: str,
        *,
        request_timeout: float,
        poll_interval: float,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._running = False
        self._thread = QThread(self)
        self._worker = _ApiWorker(base_url, workspace_id, request_timeout, poll_interval)
        self._worker.moveToThread(self._thread)
        self._thread.finished.connect(self._worker.deleteLater)
        self._healthRequested.connect(self._worker.health_check)
        self._runRequested.connect(self._worker.run)
        self._worker.healthOk.connect(self.healthOk)
        self._worker.healthFailed.connect(self.healthFailed)
        self._worker.submitted.connect(self.submitted)
        self._worker.progress.connect(self.progress)
        self._worker.finished.connect(self._on_finished)
        self._thread.start()

    @property
    def is_running(self) -> bool:
        return self._running

    def health_check(self) -> None:
        self._healthRequested.emit()

    def run(self, prompt: str, overall_timeout: float | None = None) -> None:
        if self._running:
            return
        self._running = True
        self.runStarted.emit()
        self._runRequested.emit(prompt, overall_timeout)

    def request_cancel(self) -> None:
        self._worker.request_cancel()

    @Slot(object)
    def _on_finished(self, outcome: RunOutcome) -> None:
        self._running = False
        if outcome.output:
            self.outputReady.emit(outcome)
        self.runFinished.emit(outcome)

    def shutdown(self, timeout_ms: int = 5000) -> None:
        self.request_cancel()
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(timeout_ms)

    async def aclose(self) -> None:
        self.shutdown()
