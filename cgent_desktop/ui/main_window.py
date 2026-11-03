"""Main window: branded navigation, conversation, composer and runtime status."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QVBoxLayout, QWidget
from qfluentwidgets import InfoBar, MessageBox, qconfig

from cgent_desktop.models.session import SessionRecord
from cgent_desktop.server import EmbeddedServer
from cgent_desktop.service import CgentService
from cgent_desktop.settings import DesktopSettings
from cgent_desktop.theme.tokens import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    MIN_HEIGHT,
    MIN_WIDTH,
    SPACE_3,
    SPACE_7,
    palette,
)
from cgent_desktop.ui.chat_view import ChatView
from cgent_desktop.ui.composer import Composer
from cgent_desktop.ui.sidebar import Sidebar
from cgent_desktop.ui.status_bar import StatusBar
from cgent_desktop.ui.title_bar import TitleBar
from cgent_desktop.ui.toolbar import WorkspaceToolbar
from cgent_tui.models import RunOutcome


class MainWindow(QMainWindow):
    """Assembles the desktop UI and wires it to ``CgentService`` signals."""

    def __init__(
        self,
        *,
        server: EmbeddedServer,
        store: DesktopSettings,
        workspace_id: str,
        model_id: str = "auto",
        request_timeout: float,
        poll_interval: float,
        overall_timeout: float | None,
    ) -> None:
        super().__init__()
        self.setWindowTitle(f"Cgent Desktop — workspace {workspace_id}")
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(MIN_WIDTH, MIN_HEIGHT)
        self._server = server
        self._store = store
        self._workspace_id = workspace_id
        self._model_id = model_id
        self._request_timeout = request_timeout
        self._poll_interval = poll_interval
        self._overall_timeout = overall_timeout
        self._service: CgentService | None = None
        self._started_at: str | None = None
        self._last_prompt: str | None = None
        self._last_completed_prompt: str | None = None
        self._opened_record: SessionRecord | None = None

        geometry = store.geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(DEFAULT_WIDTH, DEFAULT_HEIGHT)

        self._chat = ChatView()
        self._composer = Composer()
        self._status = StatusBar(workspace_id)
        self._sidebar = Sidebar()
        self._toolbar = WorkspaceToolbar(workspace_id, model_id)
        self._title_bar = TitleBar(workspace_id, self)
        self.setStatusBar(self._status)

        root = QWidget()
        root.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self._title_bar)
        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        body_layout.addWidget(self._sidebar)
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(self._toolbar)
        right_layout.addWidget(self._chat, stretch=1)
        composer_host = QWidget()
        composer_layout = QVBoxLayout(composer_host)
        composer_layout.setContentsMargins(SPACE_7, 0, SPACE_7, SPACE_3)
        composer_layout.addWidget(self._composer)
        right_layout.addWidget(composer_host)
        body_layout.addWidget(right, stretch=1)
        root_layout.addWidget(body, stretch=1)
        self.setCentralWidget(root)

        self._composer.submitted.connect(self._on_submit)
        self._composer.cancelRequested.connect(self._on_cancel)
        self._sidebar.newSessionRequested.connect(self._new_session)
        self._sidebar.sessionSelected.connect(self._open_session)
        self._sidebar.retryRequested.connect(self._on_submit)
        self._sidebar.deleteRequested.connect(self._delete_session)
        self._title_bar.collapse_button.clicked.connect(self._sidebar.toggle_collapsed)
        self._toolbar.rerunRequested.connect(self._rerun)
        self._toolbar.settingsRequested.connect(self._show_settings)
        self._search_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self._search_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._search_shortcut.activated.connect(self._sidebar.focus_search)
        self._escape_shortcut = QShortcut(QKeySequence("Esc"), self)
        self._escape_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._escape_shortcut.activated.connect(self._chat.collapse_all_tools)
        qconfig.themeChanged.connect(self.refresh_theme)
        self._reload_history()
        self.refresh_theme()

    def show_loading(self) -> None:
        self.show()
        self._status.set_connection("启动中…")

    def attach_service(self, service: CgentService) -> None:
        self._service = service
        service.healthOk.connect(lambda _s: self._status.set_connection("正常"))
        service.healthFailed.connect(self._on_health_failed)
        service.submitted.connect(self._status.set_invocation)
        service.progress.connect(self._chat.add_progress)
        service.runFinished.connect(self._on_finished)
        service.runStarted.connect(self._on_started)

    def _reload_history(self) -> None:
        self._sidebar.set_records(self._store.sessions())

    def _on_submit(self, prompt: str) -> None:
        if self._service is None:
            dialog = MessageBox("Cgent Desktop", "server 尚未就绪，请稍候", self)
            dialog.exec()
            return
        if self._service.is_running:
            return
        self._started_at = datetime.now().isoformat(timespec="seconds")
        self._last_prompt = prompt
        self._last_completed_prompt = prompt
        self._opened_record = None
        self._chat.add_user_message(prompt)
        self._service.run(prompt, overall_timeout=self._overall_timeout)

    def _on_cancel(self) -> None:
        if self._service is not None:
            self._status.set_note("正在请求取消…")
            self._service.request_cancel()

    def _on_started(self) -> None:
        self._composer.set_running(True)
        self._toolbar.set_running(True)
        self._status.start_elapsed()
        self._status.set_note("运行中")
        self._chat.add_progress("正在等待 server 响应")

    def _on_finished(self, outcome: RunOutcome) -> None:
        self._composer.set_running(False)
        self._toolbar.set_running(False)
        self._chat.add_outcome(outcome)
        self._status.set_invocation(outcome.invocation_id)
        self._status.set_note(f"状态：{outcome.state}")
        self._status.stop_elapsed(outcome.state)
        if self._started_at is not None:
            usage = outcome.usage
            self._store.add_session(
                SessionRecord(
                    prompt=(self._last_prompt or "")[:120],
                    state=outcome.state,
                    started_at=self._started_at,
                    detail=outcome.detail[:200],
                    input_tokens=usage.input_tokens if usage is not None else 0,
                    output_tokens=usage.output_tokens if usage is not None else 0,
                )
            )
            self._reload_history()
        self._started_at = None
        self._last_prompt = None

    def _new_session(self) -> None:
        if self._service is not None and self._service.is_running:
            InfoBar.warning("任务正在运行", "请先停止当前任务，再新建会话。", parent=self)
            return
        self._opened_record = None
        self._chat.clear()
        self._status.set_invocation(None)
        self._status.set_note("就绪")
        self._composer.setFocus()

    def _open_session(self, record: SessionRecord) -> None:
        if self._service is not None and self._service.is_running:
            return
        self._opened_record = record
        self._chat.show_history(record)
        self._status.set_invocation(None)
        self._status.set_note(f"状态：{record.state}")

    def _delete_session(self, record: SessionRecord) -> None:
        dialog = MessageBox("删除会话", f"确定删除“{record.prompt[:60]}”？此操作不可撤销。", self)
        dialog.yesButton.setText("删除")
        dialog.cancelButton.setText("取消")
        if not dialog.exec() or not self._store.delete_session(record):
            return
        if self._opened_record == record:
            self._opened_record = None
            self._chat.clear()
            self._status.set_invocation(None)
            self._status.set_note("就绪")
        self._reload_history()
        InfoBar.success("会话已删除", record.prompt[:60], parent=self)

    def _rerun(self) -> None:
        if self._last_completed_prompt:
            self._on_submit(self._last_completed_prompt)

    def _show_settings(self) -> None:
        content = (
            f"工作区：{self._workspace_id}\n"
            f"模型：{self._model_id}\n"
            f"请求超时：{self._request_timeout:g} 秒\n"
            f"轮询间隔：{self._poll_interval:g} 秒"
        )
        dialog = MessageBox("设置", content, self)
        dialog.exec()

    def _on_health_failed(self, text: str) -> None:
        self._status.set_connection(text)
        InfoBar.error("Server 连接失败", text, parent=self)

    def refresh_theme(self) -> None:
        colors = palette()
        central = self.centralWidget()
        if central is not None:
            central.setObjectName("desktopRoot")
            central.setStyleSheet(f"QWidget#desktopRoot {{ background: {colors.workspace}; }}")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._store.set_geometry(self.saveGeometry())
        if self._service is not None and self._service.is_running:
            self._service.request_cancel()
        super().closeEvent(event)
