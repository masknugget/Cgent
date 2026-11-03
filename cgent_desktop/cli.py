"""Command line entry point for the Cgent desktop app."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from PySide6.QtWidgets import QApplication
from qfluentwidgets import MessageBox

import cgent_desktop
from cgent_desktop.server import EmbeddedServer, resolve_settings
from cgent_desktop.service import CgentService
from cgent_desktop.settings import DesktopSettings
from cgent_desktop.theme import setup_app_theme
from cgent_desktop.ui.main_window import MainWindow

DEFAULT_REQUEST_TIMEOUT = 10.0
DEFAULT_POLL_INTERVAL = 1.0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cgent-desktop",
        description="Cgent 桌面客户端：内嵌 server + PySide6 界面。",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {cgent_desktop.__version__}"
    )
    parser.add_argument("--workspace", default=None, help="workspace ID（缺省使用上次会话的选择）")
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SECONDS",
        help="本地总等待期限（秒）；到期仅停止本地等待",
    )
    parser.add_argument("--dotenv", type=Path, default=None, help="server 使用的 .env 文件路径")
    parser.add_argument("--debug", action="store_true", help="提高内嵌 server 日志级别")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.timeout is not None and args.timeout <= 0:
        print("cgent-desktop: --timeout 必须为正数", file=sys.stderr)
        return 2
    try:
        settings = resolve_settings(args.workspace, args.dotenv)
    except ValueError as exc:
        print(f"cgent-desktop: {exc}", file=sys.stderr)
        return 2

    store = DesktopSettings()
    workspace_id = args.workspace or store.workspace_id
    if workspace_id is None or workspace_id not in settings.workspaces:
        known = ", ".join(sorted(settings.workspaces))
        print(
            f"cgent-desktop: 缺少 workspace；请用 --workspace 指定（已配置：{known}）",
            file=sys.stderr,
        )
        return 2
    store.set_workspace_id(workspace_id)

    qt_app = QApplication(sys.argv[:1])
    qt_app.setApplicationName("cgent-desktop")
    qt_app.setOrganizationName("Cgent")
    setup_app_theme(qt_app)

    server = EmbeddedServer(settings, parent=None)
    service: CgentService | None = None
    if args.debug:
        import logging

        logging.getLogger().setLevel(logging.DEBUG)
    window = MainWindow(
        server=server,
        store=store,
        workspace_id=workspace_id,
        model_id=settings.model,
        request_timeout=DEFAULT_REQUEST_TIMEOUT,
        poll_interval=DEFAULT_POLL_INTERVAL,
        overall_timeout=args.timeout,
    )

    def _on_server_started(_base_url: str) -> None:
        nonlocal service
        service = CgentService(
            base_url=server.base_url,
            workspace_id=workspace_id,
            request_timeout=DEFAULT_REQUEST_TIMEOUT,
            poll_interval=DEFAULT_POLL_INTERVAL,
            parent=window,
        )
        window.attach_service(service)
        service.health_check()
        window.show()

    def _on_server_failed(message: str) -> None:
        dialog = MessageBox("Cgent Desktop", message, window)
        dialog.exec()
        qt_app.quit()

    server.started.connect(_on_server_started)
    server.failed.connect(_on_server_failed)
    server.start()
    window.show_loading()

    try:
        return qt_app.exec()
    finally:
        if service is not None:
            service.shutdown()
        server.shutdown()
        server.wait(5000)


if __name__ == "__main__":
    raise SystemExit(main())
