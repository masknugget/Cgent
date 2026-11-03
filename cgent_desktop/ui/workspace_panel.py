"""Lazy-loaded workspace file tree with search, watching and context actions."""

from __future__ import annotations

import os
from pathlib import Path

import qtawesome
from PySide6.QtCore import (
    QDir,
    QFileInfo,
    QFileSystemWatcher,
    QRegularExpression,
    QSize,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    QUrl,
    Signal,
)
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QFileSystemModel,
    QHBoxLayout,
    QLabel,
    QStackedWidget,
    QTreeView,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    FluentIcon,
    PrimaryPushButton,
    RoundMenu,
    SearchLineEdit,
    TransparentToolButton,
)

from cgent_desktop.theme.tokens import (
    RADIUS_CONTROL,
    SPACE_2,
    SPACE_3,
    SPACE_4,
    T2,
    T4,
    TOOLBAR_HEIGHT,
    WEIGHT_SEMIBOLD,
    WORKSPACE_PANEL_MAX_WIDTH,
    WORKSPACE_PANEL_MIN_WIDTH,
    WORKSPACE_REFRESH_MS,
    font,
    palette,
)
from cgent_desktop.ui.i18n import (
    CHOOSE_WORKSPACE,
    COLLAPSE_ALL,
    COLLAPSE_PANEL,
    COPY_PATH,
    INVALID_WORKSPACE,
    REFRESH,
    SEARCH_FILES,
    SELECT_WORKSPACE,
    SHOW_IN_FILE_MANAGER,
    WORKSPACE_TITLE,
    tr_workspace,
)
from cgent_desktop.ui.widgets import ThemeAwareWidget

_CODE_SUFFIXES = {
    "py",
    "js",
    "ts",
    "tsx",
    "jsx",
    "java",
    "c",
    "cpp",
    "h",
    "hpp",
    "cs",
    "go",
    "rs",
    "rb",
    "php",
    "html",
    "css",
    "scss",
    "sql",
    "sh",
    "bat",
    "ps1",
    "vue",
}
_CONFIG_SUFFIXES = {"ini", "cfg", "conf", "json", "yaml", "yml", "toml"}


class WorkspaceFileSystemModel(QFileSystemModel):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self._icons: dict[str, object] = {}
        self.refresh_icons()

    def refresh_icons(self) -> None:
        colors = palette()
        self._icons = {
            "folder": qtawesome.icon("fa5s.folder", color=colors.primary),
            "code": qtawesome.icon("fa5s.file-code", color=colors.secondary),
            "file": qtawesome.icon("fa5s.file-alt", color=colors.secondary),
            "config": qtawesome.icon("fa5s.cog", color=colors.secondary),
        }

    def data(self, index, role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DecorationRole and index.isValid():
            if self.isDir(index):
                return self._icons["folder"]
            suffix = self.fileInfo(index).suffix().lower()
            if suffix in _CODE_SUFFIXES:
                return self._icons["code"]
            if suffix in _CONFIG_SUFFIXES:
                return self._icons["config"]
            return self._icons["file"]
        return super().data(index, role)


class WorkspacePanel(ThemeAwareWidget):
    collapseRequested = Signal()
    filePreviewRequested = Signal(str, str)

    def __init__(self, workspace_path: str = "") -> None:
        super().__init__()
        self.setObjectName("workspacePanel")
        self.setMinimumWidth(WORKSPACE_PANEL_MIN_WIDTH)
        self.setMaximumWidth(WORKSPACE_PANEL_MAX_WIDTH)
        self._workspace_path = ""
        self._expanded_paths: set[str] = set()
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(WORKSPACE_REFRESH_MS)
        self._refresh_timer.timeout.connect(self.refresh)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        header = QWidget()
        header.setFixedHeight(TOOLBAR_HEIGHT)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(SPACE_4, 0, SPACE_2, 0)
        header_layout.setSpacing(SPACE_2)
        self.title = QLabel(tr_workspace(WORKSPACE_TITLE))
        self.title.setFont(font(T2, WEIGHT_SEMIBOLD))
        self.refresh_button = TransparentToolButton(FluentIcon.SYNC)
        self.refresh_button.setToolTip(tr_workspace(REFRESH))
        self.collapse_all_button = TransparentToolButton(FluentIcon.CARE_UP_SOLID)
        self.collapse_all_button.setToolTip(tr_workspace(COLLAPSE_ALL))
        self.collapse_button = TransparentToolButton(FluentIcon.CLOSE)
        self.collapse_button.setToolTip(tr_workspace(COLLAPSE_PANEL))
        header_layout.addWidget(self.title)
        header_layout.addStretch()
        header_layout.addWidget(self.refresh_button)
        header_layout.addWidget(self.collapse_all_button)
        header_layout.addWidget(self.collapse_button)
        layout.addWidget(header)

        self.search = SearchLineEdit()
        self.search.setPlaceholderText(tr_workspace(SEARCH_FILES))
        self.search.setContentsMargins(SPACE_3, 0, SPACE_3, 0)
        layout.addWidget(self.search)
        layout.addSpacing(SPACE_2)

        self.model = WorkspaceFileSystemModel(self)
        self.model.setFilter(
            QDir.Filter.AllDirs | QDir.Filter.Files | QDir.Filter.NoDotAndDotDot
        )
        self.model.setNameFilterDisables(False)
        self.proxy = QSortFilterProxyModel(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setRecursiveFilteringEnabled(True)
        self.proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.tree = QTreeView()
        self.tree.setModel(self.proxy)
        self.tree.setHeaderHidden(True)
        for column in range(1, self.model.columnCount()):
            self.tree.setColumnHidden(column, True)
        self.tree.setAnimated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.setIndentation(SPACE_4)
        self.tree.setIconSize(QSize(SPACE_4, SPACE_4))
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        self.empty_page = QWidget()
        empty_layout = QVBoxLayout(self.empty_page)
        empty_layout.setContentsMargins(SPACE_4, SPACE_4, SPACE_4, SPACE_4)
        self.empty_label = QLabel(tr_workspace(INVALID_WORKSPACE))
        self.empty_label.setFont(font(T4))
        self.empty_label.setWordWrap(True)
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.choose_button = PrimaryPushButton(FluentIcon.FOLDER, tr_workspace(SELECT_WORKSPACE))
        empty_layout.addStretch()
        empty_layout.addWidget(self.empty_label)
        empty_layout.addSpacing(SPACE_3)
        empty_layout.addWidget(self.choose_button)
        empty_layout.addStretch()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.tree)
        self.stack.addWidget(self.empty_page)
        layout.addWidget(self.stack, stretch=1)

        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self._queue_refresh)
        self.refresh_button.clicked.connect(self.refresh)
        self.collapse_all_button.clicked.connect(self.collapse_all)
        self.collapse_button.clicked.connect(self.collapseRequested)
        self.choose_button.clicked.connect(self.choose_workspace)
        self.search.textChanged.connect(self._filter_files)
        self.tree.doubleClicked.connect(self._open_index)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.expanded.connect(self._on_expanded)
        self.tree.collapsed.connect(self._on_collapsed)
        self.model.directoryLoaded.connect(self._restore_expanded)
        self.refresh_theme()
        self.set_workspace_path(workspace_path)

    @property
    def workspace_path(self) -> str:
        return self._workspace_path

    @property
    def has_valid_workspace(self) -> bool:
        path = Path(self._workspace_path)
        return bool(self._workspace_path) and path.is_dir() and os.access(path, os.R_OK)

    def set_workspace_path(self, path: str) -> None:
        self._workspace_path = QDir.cleanPath(path) if path else ""
        self._expanded_paths.clear()
        self._clear_watcher()
        if not self.has_valid_workspace:
            self._show_empty_state()
            return
        self.search.setEnabled(True)
        self.stack.setCurrentWidget(self.tree)
        self._watch_path(self._workspace_path)
        self._reset_model_root()

    def choose_workspace(self) -> None:
        path = QFileDialog.getExistingDirectory(
            self,
            tr_workspace(CHOOSE_WORKSPACE),
            self._workspace_path or QDir.homePath(),
        )
        if path:
            self.set_workspace_path(path)

    def _show_empty_state(self) -> None:
        self.stack.setCurrentWidget(self.empty_page)
        self.search.setEnabled(False)

    def _clear_watcher(self) -> None:
        directories = self.watcher.directories()
        if directories:
            self.watcher.removePaths(directories)

    def _reset_model_root(self) -> None:
        self.tree.blockSignals(True)
        try:
            root_index = self.model.setRootPath(self._workspace_path)
            self.tree.setRootIndex(self.proxy.mapFromSource(root_index))
            self.tree.collapseAll()
        finally:
            self.tree.blockSignals(False)
        QTimer.singleShot(0, self._restore_expanded)

    def refresh(self) -> None:
        if self.has_valid_workspace:
            self._reset_model_root()
        else:
            self._clear_watcher()
            self._show_empty_state()

    def _queue_refresh(self, _path: str = "") -> None:
        self._refresh_timer.start()

    def collapse_all(self) -> None:
        self._expanded_paths.clear()
        self.tree.collapseAll()
        extra_paths = [path for path in self.watcher.directories() if path != self._workspace_path]
        if extra_paths:
            self.watcher.removePaths(extra_paths)

    def _filter_files(self, text: str) -> None:
        expression = QRegularExpression(QRegularExpression.escape(text))
        expression.setPatternOptions(QRegularExpression.PatternOption.CaseInsensitiveOption)
        self.proxy.setFilterRegularExpression(expression)
        if text:
            self.tree.expandAll()
        else:
            self.collapse_all()

    def _source_index(self, proxy_index):
        return self.proxy.mapToSource(proxy_index)

    def _path_for_index(self, proxy_index) -> str:
        return self.model.filePath(self._source_index(proxy_index)) if proxy_index.isValid() else ""

    def _open_index(self, index) -> None:
        path = self._path_for_index(index)
        if not path:
            return
        if self.model.isDir(self._source_index(index)):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        else:
            self.filePreviewRequested.emit(path, self._workspace_path)

    def _show_context_menu(self, position) -> None:
        path = self._path_for_index(self.tree.indexAt(position))
        menu = RoundMenu(parent=self)
        if path:
            show_action = Action(FluentIcon.FOLDER, tr_workspace(SHOW_IN_FILE_MANAGER), self)
            show_action.triggered.connect(lambda: self.show_in_file_manager(path))
            menu.addAction(show_action)
            copy_action = Action(FluentIcon.COPY, tr_workspace(COPY_PATH), self)
            copy_action.triggered.connect(lambda: self.copy_path(path))
            menu.addAction(copy_action)
        refresh_action = Action(FluentIcon.SYNC, tr_workspace(REFRESH), self)
        refresh_action.triggered.connect(self.refresh)
        menu.addAction(refresh_action)
        menu.exec(self.tree.viewport().mapToGlobal(position))

    @staticmethod
    def show_in_file_manager(path: str) -> None:
        directory = path if QFileInfo(path).isDir() else QFileInfo(path).absolutePath()
        QDesktopServices.openUrl(QUrl.fromLocalFile(directory))

    @staticmethod
    def copy_path(path: str) -> None:
        QApplication.clipboard().setText(QDir.toNativeSeparators(path))

    def _on_expanded(self, index) -> None:
        path = self._path_for_index(index)
        if path:
            self._expanded_paths.add(path)
            self._watch_path(path)

    def _on_collapsed(self, index) -> None:
        path = self._path_for_index(index)
        if path:
            self._expanded_paths.discard(path)

    def _watch_path(self, path: str) -> None:
        if path and path not in self.watcher.directories() and QFileInfo(path).isDir():
            self.watcher.addPath(path)

    def _restore_expanded(self, _path: str = "") -> None:
        if not self.has_valid_workspace:
            return
        if self.search.text():
            self.tree.expandAll()
            return
        for path in sorted(self._expanded_paths, key=lambda value: (value.count(os.sep), value)):
            source_index = self.model.index(path)
            if source_index.isValid():
                self.tree.expand(self.proxy.mapFromSource(source_index))

    def refresh_theme(self) -> None:
        colors = palette()
        self.setStyleSheet(
            f"QWidget#workspacePanel {{ background: {colors.card}; "
            f"border-left: 1px solid {colors.border}; }}"
            f"QWidget#workspacePanel QLabel {{ background: transparent; }}"
        )
        self.title.setStyleSheet(f"color: {colors.text};")
        self.empty_label.setStyleSheet(f"color: {colors.secondary};")
        self.search.setStyleSheet(
            f"SearchLineEdit {{ background: {colors.workspace}; color: {colors.text}; "
            f"border: 1px solid {colors.border}; border-radius: {RADIUS_CONTROL}px; }}"
        )
        self.tree.setStyleSheet(
            f"QTreeView {{ background: {colors.card}; color: {colors.text}; border: none; "
            f"padding: {SPACE_2}px; selection-background-color: {colors.primary_soft}; "
            f"selection-color: {colors.primary}; }}"
        )
        self.model.refresh_icons()
        self.model.layoutChanged.emit()
