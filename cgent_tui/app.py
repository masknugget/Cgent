"""Interactive Textual application for the Cgent TUI.

Concurrency model: each invocation runs in one async Worker
(``group="invocation", exclusive=True``); P0 allows a single active
invocation. The runner reports typed events; the worker posts them to the App
as ``InvocationUpdate`` messages carrying a session sequence number, and late
events from a cancelled invocation are ignored. Widget updates happen on the
App's message path, never from raw worker threads.
"""

import time
from collections.abc import Callable

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Footer

from cgent_tui.client import CgentClient
from cgent_tui.config import TuiConfig
from cgent_tui.models import (
    CancelResultEvent,
    RunnerEvent,
    RunnerState,
    RunOutcome,
    SubmittedEvent,
)
from cgent_tui.runner import InvocationRunner
from cgent_tui.sanitize import sanitize_display_text
from cgent_tui.widgets import ChatView, PromptInput, StatusBar, ToolCalls

_UPDATE = RunnerEvent | SubmittedEvent | CancelResultEvent | RunOutcome | BaseException


class InvocationUpdate(Message):
    """Runner progress for one session; stale sequences are ignored."""

    def __init__(self, seq: int, payload: _UPDATE) -> None:
        super().__init__()
        self.seq = seq
        self.payload = payload


class CgentApp(App[None]):
    """Interactive terminal client for a local Cgent server."""

    CSS = """
    #chat {
        height: 1fr;
        border: solid $primary;
        padding: 0 1;
    }
    ToolCalls {
        height: auto;
        max-height: 30%;
        border: solid $secondary;
    }
    #status {
        height: 1;
        padding: 0 1;
        background: $panel;
    }
    PromptInput {
        height: 5;
        border: solid $secondary;
    }
    Footer {
        dock: bottom;
    }
    """

    BINDINGS = [
        Binding("escape", "request_cancel", "请求取消"),
        Binding("ctrl+q", "quit", "退出"),
        Binding("ctrl+l", "clear_chat", "清屏"),
    ]

    def __init__(
        self,
        config: TuiConfig,
        *,
        client: CgentClient | None = None,
        client_factory: Callable[[str, float], CgentClient] = CgentClient,
    ) -> None:
        super().__init__()
        self._config = config
        self._client = (
            client
            if client is not None
            else client_factory(config.base_url, config.request_timeout)
        )
        self._owns_client = client is None
        self._workspace_id = config.workspace_id or ""
        self._runner: InvocationRunner | None = None
        self._worker = None
        self._active = False
        self._seq = 0
        self._history: list[str] = []
        self._history_index = 0
        self._elapsed_start = 0.0
        self._ticker = None

    def compose(self) -> ComposeResult:  # noqa: F821
        yield ChatView(id="chat")
        yield ToolCalls(id="tools")
        yield StatusBar(self._config.base_url, self._workspace_id, id="status")
        yield PromptInput(id="prompt")
        yield Footer()

    @property
    def chat(self) -> ChatView:
        return self.query_one("#chat", ChatView)

    @property
    def tools(self) -> ToolCalls:
        return self.query_one("#tools", ToolCalls)

    @property
    def status_bar(self) -> StatusBar:
        return self.query_one("#status", StatusBar)

    @property
    def prompt_input(self) -> PromptInput:
        return self.query_one("#prompt", PromptInput)

    def on_mount(self) -> None:
        self.title = "Cgent TUI"
        self.tools.display = False
        self.status_bar.set_state("正在连接 server…")
        self.prompt_input.focus()
        self.run_worker(self._check_health(), group="health", exit_on_error=False)

    async def on_unmount(self) -> None:
        if self._ticker is not None:
            self._ticker.stop()
        if self._owns_client:
            await self._client.aclose()

    async def _check_health(self) -> None:
        from cgent_tui.client import ClientError

        try:
            info = await self._client.health()
        except ClientError as exc:
            self.chat.add_status(f"无法连接 server：{sanitize_display_text(exc.detail)}", "error")
            self.chat.add_status("请确认 Cgent server 已在运行（python -m cgent）", "warning")
            self.status_bar.set_state("server 不可用")
            return
        self.chat.add_status(
            f"server {self._config.base_url} 状态：{sanitize_display_text(info.status)}"
            f"（workspace {self._workspace_id}）",
            "success",
        )
        self.chat.add_status(
            "警示：Agent 可能通过 server 对 workspace 文件和 Shell 产生真实副作用；"
            "本地退出不代表任务已经停止",
            "warning",
        )
        self.status_bar.set_state("就绪")

    def _start_invocation(self, prompt: str) -> None:
        self._active = True
        self._seq += 1
        seq = self._seq
        self._history.append(prompt)
        self._history_index = len(self._history)
        self.chat.add_user(prompt)
        self.status_bar.set_state("执行中…")
        self.status_bar.set_usage(None)
        self.tools.display = False
        self.tools.update_calls(())
        self._elapsed_start = time.monotonic()
        self._ticker = self.set_interval(0.5, self._tick_elapsed)
        runner = InvocationRunner(
            self._client,
            self._workspace_id,
            poll_interval=self._config.poll_interval,
        )
        self._runner = runner

        def emit(event: RunnerEvent | SubmittedEvent | CancelResultEvent) -> None:
            self.post_message(InvocationUpdate(seq, event))

        async def drive() -> None:
            try:
                outcome = await runner.run(prompt, emit)
            except Exception as exc:  # unexpected: keep the App alive
                self.post_message(InvocationUpdate(seq, exc))
                return
            self.post_message(InvocationUpdate(seq, outcome))

        self._worker = self.run_worker(
            drive(), group="invocation", exclusive=True, exit_on_error=False
        )

    def _finish_invocation(self) -> None:
        self._active = False
        self._runner = None
        if self._ticker is not None:
            self._ticker.stop()
            self._ticker = None
        self.status_bar.set_elapsed(None)
        self.prompt_input.focus()

    def _tick_elapsed(self) -> None:
        self.status_bar.set_elapsed(time.monotonic() - self._elapsed_start)

    def on_prompt_input_prompt_submitted(self, message: PromptInput.PromptSubmitted) -> None:
        if self._active:
            self.chat.add_status("已有任务在执行，请等待完成或按 Esc 请求取消", "warning")
            return
        self._start_invocation(message.text)

    def on_prompt_input_history_prev(self, _: PromptInput.HistoryPrev) -> None:
        if self._history_index > 0:
            self._history_index -= 1
            self.prompt_input.set_prompt(self._history[self._history_index])

    def on_prompt_input_history_next(self, _: PromptInput.HistoryNext) -> None:
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self.prompt_input.set_prompt(self._history[self._history_index])
        else:
            self._history_index = len(self._history)
            self.prompt_input.set_prompt("")

    def on_invocation_update(self, message: InvocationUpdate) -> None:
        if message.seq != self._seq:
            return  # late event from a cancelled invocation
        payload = message.payload
        if isinstance(payload, SubmittedEvent):
            self.status_bar.set_state(f"已提交 {payload.invocation_id}，执行中…")
            return
        if isinstance(payload, CancelResultEvent):
            self.status_bar.set_state(sanitize_display_text(payload.detail))
            return
        if isinstance(payload, RunnerEvent):
            self._apply_runner_event(payload)
            return
        if isinstance(payload, RunOutcome):
            self._apply_outcome(payload)
            return
        # Unexpected worker exception: readable state, App stays alive.
        self.chat.add_status(f"发生未预期错误：{sanitize_display_text(str(payload))}", "error")
        self._finish_invocation()

    def _apply_runner_event(self, event: RunnerEvent) -> None:
        detail = sanitize_display_text(event.detail)
        match event.state:
            case RunnerState.SUBMITTING:
                self.status_bar.set_state("正在提交…")
            case RunnerState.DISCONNECTED:
                self.status_bar.set_state(detail or "连接中断，正在重试…")
            case RunnerState.CANCELLING:
                self.status_bar.set_state(detail or "正在请求取消…")
            case RunnerState.POLLING:
                self.status_bar.set_state(detail or "执行中…")

    def _apply_outcome(self, outcome: RunOutcome) -> None:
        detail = sanitize_display_text(outcome.detail)
        if outcome.usage is not None:
            self.status_bar.set_usage(outcome.usage)
        if outcome.tool_calls:
            self.tools.update_calls(outcome.tool_calls)
            self.tools.display = True
        match outcome.state:
            case "succeeded":
                self.status_bar.set_state("已完成")
                if outcome.output:
                    self.chat.add_output(outcome.output)
            case "failed":
                self.status_bar.set_state("失败")
                self.chat.add_status(detail or "调用失败", "error")
            case "cancelled":
                self.status_bar.set_state("已确认取消")
                self.chat.add_status(detail or "server 已确认取消", "warning")
            case "unknown":
                self.status_bar.set_state("结果未知")
                self.chat.add_status(detail or "远端最终状态无法确定", "warning")
        self._finish_invocation()

    def action_request_cancel(self) -> None:
        if not self._active or self._runner is None:
            return
        self._runner.request_cancel()
        self.status_bar.set_state("正在请求取消…")

    def action_clear_chat(self) -> None:
        self.chat.clear()
        self.tools.display = False
        self.tools.update_calls(())

    async def action_quit(self) -> None:
        if self._active:
            self.chat.add_status("任务未达终态：远端可能仍在执行；本地客户端正在退出", "warning")
            if self._worker is not None:
                self._worker.cancel()
        self.exit()
