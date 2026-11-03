"""Invocation runner: submit, poll with bounded backoff, cancel, and deadlines.

The runner is UI-agnostic. It reports progress through typed events and
returns a final ``RunOutcome``; callers never see ``httpx`` objects.

State machine (client-side workflow states, not the server enum):

    SUBMITTING ──id──► POLLING ──succeeded──► SUCCEEDED
                         │ ├─failed────────► FAILED
                         │ ├─cancelled─────► CANCELLED
                         │ ├─404───────────► UNKNOWN（记录不存在）
                         │ ├─断线×5────────► UNKNOWN（停止本地等待）
                         │ ├─总期限到期────► UNKNOWN（任务可能仍在执行）
                         │ └─请求取消──────► CANCELLING ─204► CANCELLED
                         │                    ├─409────► POLLING（继续等待）
                         │                    └─不明───► POLLING（警告）
    SUBMITTING ──网络错误──► UNKNOWN（提交结果不确定）

Only GET-after-id polls retry, with sleeps of 1, 2, 2, 2, 2 seconds and at
most 5 consecutive failures. Submission, cancel and the startup health check
never retry.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Protocol

from cgent_tui.client import (
    ClientError,
    ConflictError,
    NotFoundError,
    TransientConnectionError,
)
from cgent_tui.models import (
    CancelResultEvent,
    InvocationStatus,
    RunnerEvent,
    RunnerState,
    RunOutcome,
    SubmittedEvent,
)

BACKOFF_SECONDS = (1.0, 2.0, 2.0, 2.0, 2.0)
MAX_CONSECUTIVE_FAILURES = len(BACKOFF_SECONDS)

type Clock = Callable[[], float]
type Sleep = Callable[[float], Awaitable[None]]
type EventSink = Callable[[RunnerEvent | SubmittedEvent | CancelResultEvent], None]


class _DeadlineExceeded(Exception):
    """The overall wait deadline passed; only local waiting stops."""


class InvocationClient(Protocol):
    """The REST surface the runner depends on; ``CgentClient`` implements it."""

    async def submit(
        self, workspace_id: str, prompt: str, timeout_seconds: float | None = None
    ) -> str: ...

    async def get_invocation(self, invocation_id: str) -> InvocationStatus: ...

    async def request_cancel(self, invocation_id: str) -> None: ...


class InvocationRunner:
    """Drives one invocation through submit, poll, and optional cancellation."""

    def __init__(
        self,
        client: InvocationClient,
        workspace_id: str,
        *,
        poll_interval: float = 1.0,
        overall_timeout: float | None = None,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._client = client
        self._workspace_id = workspace_id
        self._poll_interval = poll_interval
        self._overall_timeout = overall_timeout
        self._clock = clock
        self._sleep = sleep
        self._cancel_requested = False
        self.invocation_id: str | None = None

    def request_cancel(self) -> None:
        """Ask the runner to issue a cancel request at the next poll boundary.

        Safe to call from a signal handler: it only sets a flag, and the
        DELETE is performed by the running event loop.
        """
        self._cancel_requested = True

    async def run(self, prompt: str, on_event: EventSink | None = None) -> RunOutcome:
        """Submit ``prompt`` and follow it to a terminal or unknown state."""
        self._cancel_requested = False
        self.invocation_id = None
        emit = on_event if on_event is not None else lambda event: None

        deadline = (
            self._clock() + self._overall_timeout if self._overall_timeout is not None else None
        )
        self._deadline = deadline

        emit(RunnerEvent(RunnerState.SUBMITTING))
        try:
            invocation_id = await self._client.submit(self._workspace_id, prompt)
        except TransientConnectionError as exc:
            return RunOutcome(
                state="unknown",
                detail=(
                    f"提交结果未知：{exc.detail}；server 中可能已创建该任务，"
                    "客户端未自动重试（API 无幂等键）"
                ),
            )
        except ClientError as exc:
            return RunOutcome(state="failed", detail=f"提交失败：{exc.detail}")
        self.invocation_id = invocation_id
        emit(SubmittedEvent(invocation_id))
        emit(RunnerEvent(RunnerState.POLLING))

        try:
            return await self._poll(invocation_id, emit)
        except _DeadlineExceeded:
            return RunOutcome(
                state="unknown",
                invocation_id=invocation_id,
                detail=(
                    "总等待期限已到，已停止本地等待；"
                    f"invocation {invocation_id} 在 server 上可能仍在执行，"
                    "客户端未自动发送取消请求"
                ),
            )
        except asyncio.CancelledError:
            return RunOutcome(
                state="unknown",
                invocation_id=invocation_id,
                detail=(f"本地等待已被停止；invocation {invocation_id} 在 server 上可能仍在执行"),
            )

    async def _poll(self, invocation_id: str, emit: EventSink) -> RunOutcome:
        failures = 0
        disconnected = False
        while True:
            if self._cancel_requested:
                outcome = await self._cancel_flow(invocation_id, emit)
                if outcome is not None:
                    return outcome
                continue
            try:
                status = await self._client.get_invocation(invocation_id)
            except TransientConnectionError as exc:
                failures += 1
                if failures >= MAX_CONSECUTIVE_FAILURES:
                    return RunOutcome(
                        state="unknown",
                        invocation_id=invocation_id,
                        detail=(
                            f"连接连续失败 {MAX_CONSECUTIVE_FAILURES} 次，已停止本地等待："
                            f"{exc.detail}；server 任务可能仍在执行"
                        ),
                    )
                if not disconnected:
                    emit(
                        RunnerEvent(
                            RunnerState.DISCONNECTED,
                            f"与 server 的连接中断：{exc.detail}；正在重试",
                        )
                    )
                    disconnected = True
                await self._sleep_within(BACKOFF_SECONDS[failures - 1])
                continue
            except NotFoundError:
                return RunOutcome(
                    state="unknown",
                    invocation_id=invocation_id,
                    detail=("未找到该 invocation；server 可能已重启、记录已过期或连接了不同实例"),
                )
            except ClientError as exc:
                return RunOutcome(
                    state="failed",
                    invocation_id=invocation_id,
                    detail=f"查询调用状态时出错：{exc.detail}",
                )
            failures = 0
            if disconnected:
                emit(RunnerEvent(RunnerState.POLLING, "连接已恢复"))
                disconnected = False
            if status.status == "pending":
                await self._sleep_within(self._poll_interval)
                continue
            if status.status == "succeeded":
                return RunOutcome(
                    state="succeeded",
                    invocation_id=invocation_id,
                    output=status.output,
                    tool_calls=status.tool_calls,
                    usage=status.usage,
                )
            if status.status == "failed":
                detail = status.error_message or status.error_code or "server 报告调用失败"
                return RunOutcome(
                    state="failed",
                    invocation_id=invocation_id,
                    detail=f"调用失败：{detail}",
                    tool_calls=status.tool_calls,
                    usage=status.usage,
                )
            return RunOutcome(
                state="cancelled",
                invocation_id=invocation_id,
                detail="server 报告该调用已被取消",
            )

    async def _cancel_flow(self, invocation_id: str, emit: EventSink) -> RunOutcome | None:
        """Issue one cancel request; returns an outcome only when final."""
        self._cancel_requested = False
        emit(RunnerEvent(RunnerState.CANCELLING, "正在请求 server 取消该调用…"))
        try:
            await self._client.request_cancel(invocation_id)
        except ConflictError:
            emit(
                CancelResultEvent(
                    "rejected",
                    "server 拒绝取消：当前状态不可取消，继续等待其结果",
                )
            )
            return None
        except ClientError as exc:
            emit(
                CancelResultEvent(
                    "unknown",
                    f"取消结果未知：{exc.detail}；server 任务可能仍在执行",
                )
            )
            return None
        emit(CancelResultEvent("confirmed", "server 已确认取消"))
        return RunOutcome(
            state="cancelled",
            invocation_id=invocation_id,
            detail="server 已确认取消该调用",
        )

    async def _sleep_within(self, seconds: float) -> None:
        """Sleep up to ``seconds``, honouring the overall deadline."""
        if self._deadline is None:
            await self._sleep(seconds)
            return
        remaining = self._deadline - self._clock()
        if remaining <= 0:
            raise _DeadlineExceeded
        await self._sleep(min(seconds, remaining))
        if self._deadline - self._clock() <= 0:
            raise _DeadlineExceeded
