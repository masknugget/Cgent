"""Embedded Cgent server lifecycle for the desktop app.

The desktop runs the FastAPI service in-process on a loopback-only address.
``EmbeddedServer`` owns a ``QThread`` running ``uvicorn.Server``; startup
resolves a free port (port 0) so multiple instances never collide. Shutdown
sets ``should_exit`` from the UI thread, which uvicorn polls on its own loop.
"""

from __future__ import annotations

import socket
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from langchain_core.language_models import BaseChatModel
from PySide6.QtCore import QObject, QThread, Signal

from cgent.app import create_app
from cgent.config import Settings

if TYPE_CHECKING:
    import uvicorn


def find_free_port(host: str) -> int:
    """Bind an ephemeral loopback port and return its number."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return int(sock.getsockname()[1])


class EmbeddedServer(QThread):
    """Runs ``uvicorn.Server`` for one ``cgent`` FastAPI app.

    Emits ``started(str)`` with the base URL once the server is serving,
    or ``failed(str)`` when startup raised. Call :meth:`shutdown` then
    :meth:`wait` from the owner thread to stop cleanly.
    """

    started = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        settings: Settings,
        model: BaseChatModel | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = replace(settings, host="127.0.0.1", port=find_free_port("127.0.0.1"))
        self._model = model
        self._server: uvicorn.Server | None = None  # noqa: F821 - assigned in run()

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._settings.port}"

    @property
    def settings(self) -> Settings:
        return self._settings

    def run(self) -> None:  # noqa: D102 - QThread entry point
        try:
            app = create_app(self._settings, model=self._model)
        except Exception as exc:  # startup error must reach the UI, not the console
            self.failed.emit(f"无法启动 Cgent 服务：{exc}")
            return
        import uvicorn

        class _DesktopServer(uvicorn.Server):
            # uvicorn 0.54+ always captures SIGINT/SIGTERM in run(); we run in
            # a QThread where signal.signal() is illegal, and the desktop owns
            # process-lifetime signals itself. Shutdown goes through
            # ``should_exit`` instead.
            @contextmanager
            def capture_signals(self):  # type: ignore[override]
                yield

        config = uvicorn.Config(
            app,
            host=self._settings.host,
            port=self._settings.port,
            log_level="warning",
        )
        server = _DesktopServer(config)
        self._server = server
        try:
            self.started.emit(self.base_url)
            server.run()
        except Exception as exc:  # after started: report runtime failure
            self.failed.emit(f"Cgent 服务异常退出：{exc}")

    def shutdown(self) -> None:
        """Ask uvicorn to stop; safe to call before the thread has started."""
        server = self._server
        if server is not None:
            server.should_exit = True


def resolve_settings(workspace_id: str | None, dotenv_path: Path | None) -> Settings:
    """Load ``Settings`` from the environment (optionally a project ``.env``).

    When ``workspace_id`` is given it must already exist in the configured
    workspaces; the desktop never invents workspace mappings.
    """
    settings = Settings.from_env(dotenv_path=dotenv_path)
    if workspace_id is not None and workspace_id not in settings.workspaces:
        known = ", ".join(sorted(settings.workspaces))
        raise ValueError(f"未知 workspace {workspace_id!r}；已配置：{known}")
    return settings
