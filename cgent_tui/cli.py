"""Command line interface for the Cgent TUI.

Output discipline for ``run`` (scriptable): stdout carries only the agent's
final output; every progress note, warning, invocation ID and diagnostic goes
to stderr. Exit codes: 0 success, 1 failure/unknown, 2 usage/config/input
errors, 130 local interrupt (never implies the server cancelled the task).
"""

import argparse
import asyncio
import os
import signal
import sys
from collections.abc import Sequence
from typing import Any

import cgent_tui
from cgent_tui import exit_codes as ex
from cgent_tui.client import CgentClient, ClientError
from cgent_tui.compose import ComposeError, compose_prompt, read_piped_stdin
from cgent_tui.config import ConfigError, require_workspace, resolve_config
from cgent_tui.models import (
    CancelResultEvent,
    RunnerEvent,
    RunnerState,
    RunOutcome,
    SubmittedEvent,
)
from cgent_tui.runner import InvocationRunner

_WARNING = (
    "警示：Agent 可能通过 server 对 workspace 文件和 Shell 产生真实副作用；"
    "本地客户端退出不代表任务已经停止"
)


class _BrokenPipe(Exception):
    """Raised when the downstream pipe closes; never prints a traceback."""


def note(text: str) -> None:
    """Write one diagnostic line to stderr as UTF-8 bytes.

    Explicit buffer writes keep output stable regardless of the host
    platform's console code page (e.g. GBK on Chinese Windows).
    """
    try:
        sys.stderr.buffer.write(f"cgent-tui: {text}\n".encode())
        sys.stderr.buffer.flush()
    except BrokenPipeError:
        pass


def _write_stdout(text: str) -> None:
    try:
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.flush()
    except BrokenPipeError as exc:
        raise _BrokenPipe from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cgent-tui",
        description="Cgent 终端客户端：提交 Agent 任务、观察状态、请求取消。",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {cgent_tui.__version__}")
    subcommands = parser.add_subparsers(dest="command", metavar="command")

    run = subcommands.add_parser(
        "run",
        help="非交互提交任务；stdout 只输出最终结果",
        description=(
            "提交一个 Agent 任务并等待其结果。stdout 只写最终 output，"
            "进度与诊断写 stderr。管道 stdin 会以 <stdin> 标签拼接到 prompt。"
        ),
    )
    _add_connection_options(run)
    run.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="本地总等待期限（秒）；到期仅停止本地等待，不自动取消 server 任务",
    )
    run.add_argument("prompt", nargs="*", help="任务描述（缺省时使用管道 stdin）")

    tui = subcommands.add_parser("tui", help="交互式终端界面（默认）")
    _add_connection_options(tui)

    status = subcommands.add_parser("status", help="检查 server 健康状态（不需要 workspace）")
    status.add_argument("--base-url", default=None, help="server 地址")
    status.add_argument(
        "--request-timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="单次 HTTP 请求超时（秒）",
    )
    return parser


def _add_connection_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", default=None, help="workspace ID")
    parser.add_argument("--base-url", default=None, help="server 地址")
    parser.add_argument(
        "--request-timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="单次 HTTP 请求超时（秒）",
    )


def _resolve(args: Any, need_workspace: bool) -> Any:
    config = resolve_config(
        base_url=args.base_url,
        workspace_id=getattr(args, "workspace", None),
        poll_interval=None,
        request_timeout=(
            str(args.request_timeout)
            if getattr(args, "request_timeout", None) is not None
            else None
        ),
    )
    if need_workspace:
        require_workspace(config)
    return config


def _stderr_events(event: RunnerEvent | SubmittedEvent | CancelResultEvent) -> None:
    """Progress notes for ``run`` mode; everything goes to stderr."""
    if isinstance(event, SubmittedEvent):
        note(f"已提交 invocation {event.invocation_id}")
        return
    if isinstance(event, CancelResultEvent):
        note(event.detail)
        return
    match event.state:
        case RunnerState.SUBMITTING:
            note("正在提交任务…")
        case RunnerState.DISCONNECTED | RunnerState.CANCELLING:
            note(event.detail)
        case RunnerState.POLLING if event.detail:
            note(event.detail)
        case _:
            pass


def _outcome_exit_code(outcome: RunOutcome, interrupts: int) -> int:
    if outcome.state == "succeeded":
        output = outcome.output or ""
        if output and not output.endswith("\n"):
            output = f"{output}\n"
        _write_stdout(output)
        if outcome.usage is not None:
            note(
                f"tokens: in {outcome.usage.input_tokens} / out {outcome.usage.output_tokens} / total {outcome.usage.total_tokens}"
            )
        return ex.EX_OK
    if outcome.state == "cancelled":
        note(outcome.detail)
        if interrupts > 0:
            note("本地已被 Ctrl-C 中断；退出码仅描述本地中断")
            return ex.EX_INTERRUPTED
        return ex.EX_FAILED
    note(outcome.detail)
    return ex.EX_FAILED


async def _run_command(args: Any) -> int:
    config = _resolve(args, need_workspace=True)
    if args.timeout is not None and args.timeout <= 0:
        note("--timeout 必须为正数")
        return ex.EX_USAGE
    prompt_arg = " ".join(args.prompt).strip()
    try:
        stdin_text = read_piped_stdin()
        prompt = compose_prompt(prompt_arg, stdin_text)
    except ComposeError as exc:
        note(str(exc))
        return ex.EX_USAGE
    if prompt is None:
        note("缺少 prompt：请通过参数或管道 stdin 提供任务描述")
        return ex.EX_USAGE

    client = CgentClient(config.base_url, config.request_timeout)
    try:
        try:
            await client.health()
        except ClientError as exc:
            note(f"无法连接 server：{exc.detail}")
            note("请确认 Cgent server 已在运行（python -m cgent）")
            return ex.EX_FAILED
        note(f"server {config.base_url} 状态正常（workspace {config.workspace_id}）")
        note(_WARNING)

        runner = InvocationRunner(
            client,
            config.workspace_id or "",
            poll_interval=config.poll_interval,
            overall_timeout=args.timeout,
        )
        loop = asyncio.get_running_loop()
        task = asyncio.ensure_future(runner.run(prompt, on_event=_stderr_events))
        interrupts = {"count": 0}

        def handle_sigint(signum: int, frame: Any) -> None:
            interrupts["count"] += 1
            if interrupts["count"] == 1:
                runner.request_cancel()
                note("\n已请求取消；再次按 Ctrl-C 立即退出（server 任务可能仍在执行）")
            else:
                note("第二次 Ctrl-C：正在退出…")
                loop.call_soon_threadsafe(task.cancel)

        previous = signal.signal(signal.SIGINT, handle_sigint)
        try:
            outcome = await task
        finally:
            signal.signal(signal.SIGINT, previous)
        return _outcome_exit_code(outcome, interrupts["count"])
    finally:
        await client.aclose()


async def _status_command(args: Any) -> int:
    config = _resolve(args, need_workspace=False)
    client = CgentClient(config.base_url, config.request_timeout)
    try:
        try:
            info = await client.health()
        except ClientError as exc:
            note(f"无法连接 server：{exc.detail}")
            note("请确认 Cgent server 已在运行（python -m cgent）")
            return ex.EX_FAILED
        _write_stdout(f"server {config.base_url} 状态：{info.status}\n")
        return ex.EX_OK
    finally:
        await client.aclose()


def _tui_command(args: Any) -> int:
    config = _resolve(args, need_workspace=True)
    from cgent_tui.app import CgentApp

    app = CgentApp(config)
    app.run()
    return ex.EX_OK


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    command = args.command or "tui"
    try:
        if command == "run":
            return asyncio.run(_run_command(args))
        if command == "status":
            return asyncio.run(_status_command(args))
        return _tui_command(args)
    except ConfigError as exc:
        note(f"配置错误：{exc}")
        return ex.EX_USAGE
    except KeyboardInterrupt:
        note("本地被 Ctrl-C 中断；server 任务可能仍在执行")
        return ex.EX_INTERRUPTED
    except _BrokenPipe:
        # Downstream closed the pipe: exit quietly without a traceback.
        try:
            devnull = os.open(os.devnull, os.O_WRONLY)
            os.dup2(devnull, sys.stdout.fileno())
        except OSError:
            pass
        note("stdout 管道已关闭（下游提前退出）")
        return ex.EX_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
