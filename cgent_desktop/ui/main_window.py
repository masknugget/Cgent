"""Main window: branded navigation, conversation, composer and runtime status."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import QHBoxLayout, QMainWindow, QSplitter, QVBoxLayout, QWidget
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
    RADIUS_CONTROL,
    SIDEBAR_WIDTH,
    SPACE_2,
    SPACE_3,
    SPACE_7,
    palette,
)
from cgent_desktop.ui.chat_view import ChatView
from cgent_desktop.ui.composer import Composer
from cgent_desktop.ui.file_preview import FilePreviewDialog
from cgent_desktop.ui.i18n import (
    CANCEL,
    DELETE,
    DELETE_CONTENT,
    DELETE_ERROR_CONTENT,
    DELETE_ERROR_TITLE,
    DELETE_SUCCESS_TITLE,
    DELETE_TITLE,
    RENAME_ERROR_CONTENT,
    RENAME_ERROR_TITLE,
    tr,
)
from cgent_desktop.ui.sidebar import Sidebar
from cgent_desktop.ui.status_bar import StatusBar
from cgent_desktop.ui.title_bar import TitleBar
from cgent_desktop.ui.toolbar import WorkspaceToolbar
from cgent_desktop.ui.workspace_panel import WorkspacePanel
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
        self._file_preview: FilePreviewDialog | None = None

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
        workspace_path = ""
        if server is not None:
            configured_path = server.settings.workspaces.get(workspace_id)
            if configured_path is not None:
                workspace_path = str(configured_path)
        self._workspace_panel = WorkspacePanel(workspace_path)
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
        self._workspace_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._workspace_splitter.setChildrenCollapsible(False)
        self._workspace_splitter.setHandleWidth(1)
        self._workspace_splitter.addWidget(right)
        self._workspace_splitter.addWidget(self._workspace_panel)
        self._workspace_splitter.setStretchFactor(0, 1)
        self._workspace_splitter.setStretchFactor(1, 0)
        panel_width = store.workspace_panel_width()
        self._workspace_splitter.setSizes(
            [DEFAULT_WIDTH - SIDEBAR_WIDTH - panel_width, panel_width]
        )
        body_layout.addWidget(self._workspace_splitter, stretch=1)
        root_layout.addWidget(body, stretch=1)
        self.setCentralWidget(root)

        self._composer.submitted.connect(self._on_submit)
        self._composer.cancelRequested.connect(self._on_cancel)
        self._chat.regenerateRequested.connect(self._rerun)
        self._sidebar.newSessionRequested.connect(self._new_session)
        self._sidebar.sessionSelected.connect(self._open_session)
        self._sidebar.retryRequested.connect(self._on_submit)
        self._sidebar.deleteRequested.connect(self._delete_session)
        self._sidebar.renameRequested.connect(self._rename_session)
        self._title_bar.collapse_button.clicked.connect(self._sidebar.toggle_collapsed)
        self._toolbar.rerunRequested.connect(self._rerun)
        self._toolbar.settingsRequested.connect(self._show_settings)
        self._toolbar.workspaceToggleRequested.connect(self._toggle_workspace_panel)
        self._workspace_panel.collapseRequested.connect(self._toggle_workspace_panel)
        self._workspace_panel.filePreviewRequested.connect(self._show_file_preview)
        self._workspace_splitter.splitterMoved.connect(self._save_workspace_panel_width)
        self._search_shortcut = QShortcut(QKeySequence("Ctrl+K"), self)
        self._search_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._search_shortcut.activated.connect(self._sidebar.focus_search)
        self._workspace_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        self._workspace_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._workspace_shortcut.activated.connect(self._toggle_workspace_panel)
        self._escape_shortcut = QShortcut(QKeySequence("Esc"), self)
        self._escape_shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
        self._escape_shortcut.activated.connect(self._on_escape)
        if not store.workspace_panel_visible():
            self._toggle_workspace_panel()
        qconfig.themeChanged.connect(self.refresh_theme)
        self._reload_history()
        self.refresh_theme()

    def _toggle_workspace_panel(self) -> None:
        visible = self._workspace_panel.isHidden()
        if visible:
            self._workspace_panel.setVisible(True)
            total_width = self._workspace_splitter.width() or DEFAULT_WIDTH - SIDEBAR_WIDTH
            panel_width = self._store.workspace_panel_width()
            self._workspace_splitter.setSizes([total_width - panel_width, panel_width])
        else:
            self._save_workspace_panel_width()
            self._workspace_panel.setVisible(False)
        self._toolbar.set_workspace_panel_visible(visible)
        self._status.set_workspace_panel_visible(visible)
        self._store.set_workspace_panel_visible(visible)

    def _save_workspace_panel_width(self, _position: int = 0, _index: int = 0) -> None:
        if self._workspace_panel.isVisible():
            width = self._workspace_panel.width()
            if width >= self._workspace_panel.minimumWidth():
                self._store.set_workspace_panel_width(width)

    def _show_file_preview(self, path: str, workspace_root: str) -> None:
        if self._file_preview is None:
            self._file_preview = FilePreviewDialog(self._store, self)
        self._file_preview.show_file(path, workspace_root)

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
        records = self._store.sessions()
        self._sidebar.set_records(records)
        if self._opened_record is not None:
            opened = next(
                (
                    record
                    for record in records
                    if record.session_id == self._opened_record.session_id
                ),
                None,
            )
            if opened is not None:
                self._opened_record = opened
                self._sidebar.select_session(opened.session_id)

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
        self._sidebar.select_session("")
        self._chat.add_user_message(prompt)
        self._service.run(prompt, overall_timeout=self._overall_timeout)

    def _on_cancel(self) -> None:
        if self._service is not None:
            self._status.set_note("正在请求取消…")
            self._service.request_cancel()

    def _on_escape(self) -> None:
        if not self._sidebar.cancel_selected_rename():
            self._chat.collapse_all_tools()

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
        self._sidebar.select_session("")
        self._chat.clear()
        self._status.set_invocation(None)
        self._status.set_note("就绪")
        self._composer.setFocus()

    def _open_session(self, record: SessionRecord) -> None:
        if self._service is not None and self._service.is_running:
            return
        self._opened_record = record
        self._sidebar.select_session(record.session_id)
        self._chat.show_history(record)
        self._status.set_invocation(None)
        self._status.set_note(f"状态：{record.state}")

    def _rename_session(self, record: SessionRecord, title: str) -> None:
        if not self._store.rename_session(record.session_id, title):
            InfoBar.error(tr(RENAME_ERROR_TITLE), tr(RENAME_ERROR_CONTENT), parent=self)
            return
        self._reload_history()

    def _delete_session(self, record: SessionRecord) -> None:
        dialog = MessageBox(tr(DELETE_TITLE), tr(DELETE_CONTENT), self)
        dialog.yesButton.setText(tr(DELETE))
        dialog.cancelButton.setText(tr(CANCEL))
        colors = palette()
        dialog.yesButton.setStyleSheet(
            f"QPushButton {{ background: {colors.failure}; color: {colors.on_primary}; "
            f"border: none; border-radius: {RADIUS_CONTROL}px; "
            f"padding: {SPACE_2}px {SPACE_3}px; }}"
            f"QPushButton:hover {{ background: {colors.failure}; }}"
        )
        dialog.yesButton.setDefault(False)
        dialog.cancelButton.setDefault(True)
        dialog.cancelButton.setFocus()
        if not dialog.exec():
            return
        if not self._store.delete_session(record.session_id):
            InfoBar.error(tr(DELETE_ERROR_TITLE), tr(DELETE_ERROR_CONTENT), parent=self)
            return
        deleted_open = (
            self._opened_record is not None and self._opened_record.session_id == record.session_id
        )
        remaining = self._store.sessions()
        self._reload_history()
        if deleted_open:
            if remaining:
                self._open_session(remaining[0])
            else:
                self._new_session()
        InfoBar.success(tr(DELETE_SUCCESS_TITLE), record.display_title, parent=self)

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
        self._save_workspace_panel_width()
        if self._file_preview is not None:
            self._file_preview.close()
        if self._service is not None and self._service.is_running:
            self._service.request_cancel()
        super().closeEvent(event)
