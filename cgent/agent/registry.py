"""In-memory asynchronous invocation registry with result TTL."""

import asyncio
from dataclasses import dataclass, field
from typing import Literal

from cgent.agent.runner import AgentRunner, InvocationResult
from cgent.errors import HarnessError
from cgent.telemetry.request_id import new_id


@dataclass(slots=True)
class InvocationRecord:
    invocation_id: str
    workspace_id: str
    status: Literal["pending", "succeeded", "failed", "cancelled"] = "pending"
    result: InvocationResult | None = None
    error_code: str | None = None
    error_message: str | None = None
    task: asyncio.Task[None] | None = field(default=None, repr=False)


class InvocationRegistry:
    """Owns background Agent tasks and their observable results.

    Results stay queryable for ``ttl_seconds`` after completion, then are
    dropped. Everything is process-local: a restart loses all records.
    """

    def __init__(self, runner: AgentRunner, ttl_seconds: float) -> None:
        self._runner = runner
        self._ttl_seconds = ttl_seconds
        self._records: dict[str, InvocationRecord] = {}

    def submit(
        self,
        workspace_id: str,
        text: str,
        timeout_seconds: float | None = None,
    ) -> InvocationRecord:
        invocation_id = new_id("inv")
        record = InvocationRecord(invocation_id=invocation_id, workspace_id=workspace_id)
        self._records[invocation_id] = record
        task = asyncio.create_task(
            self._run(record, workspace_id, text, timeout_seconds),
            name=f"cgent-invocation-{invocation_id}",
        )
        record.task = task
        task.add_done_callback(lambda _task: self._schedule_expiry(record))
        return record

    def get(self, invocation_id: str) -> InvocationRecord | None:
        return self._records.get(invocation_id)

    def cancel(self, invocation_id: str) -> bool:
        record = self._records.get(invocation_id)
        if (
            record is None
            or record.task is None
            or record.task.done()
            or record.status != "pending"
        ):
            return False
        # Mark optimistically: a task cancelled before its first step never runs
        # the coroutine body, so the CancelledError handler alone cannot be relied on.
        record.status = "cancelled"
        record.task.cancel()
        return True

    async def close(self) -> None:
        tasks: list[asyncio.Task[None]] = []
        for invocation_id, record in list(self._records.items()):
            self.cancel(invocation_id)
            if record.task is not None:
                tasks.append(record.task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(
        self,
        record: InvocationRecord,
        workspace_id: str,
        text: str,
        timeout_seconds: float | None,
    ) -> None:
        try:
            record.result = await self._runner.invoke(
                workspace_id, text, timeout_seconds, record.invocation_id
            )
            record.status = "succeeded"
        except asyncio.CancelledError:
            record.status = "cancelled"
            # The cancellation is the intended outcome; end the task quietly.
        except HarnessError as exc:
            record.status = "failed"
            record.error_code = exc.code
            record.error_message = exc.message
        except Exception as exc:  # Surface unexpected failures to pollers.
            record.status = "failed"
            record.error_code = "internal_error"
            record.error_message = str(exc) or "Unexpected invocation failure"

    def _schedule_expiry(self, record: InvocationRecord) -> None:
        loop = asyncio.get_running_loop()
        loop.call_later(self._ttl_seconds, self._records.pop, record.invocation_id, None)
