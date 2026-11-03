"""Three-part status bar for server, invocation and elapsed run state."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QMouseEvent, QResizeEvent
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QStatusBar, QWidget
from qfluentwidgets import qconfig

from cgent_desktop.theme.tokens import (
    ELAPSED_TIMER_MS,
    SPACE_2,
    SPACE_3,
    STATUS_BAR_HEIGHT,
    T5,
    WEIGHT_SEMIBOLD,
    font,
    palette,
    state_colors,
)
from cgent_desktop.ui.widgets import StateDot, StatusBadge


class _InvocationLabel(QLabel):
    def __init__(self) -> None:
        super().__init__("invocation: —")
        self._invocation_id = ""
        self.setFont(font(T5, mono=True))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("点击复制完整 Invocation ID")

    def set_invocation(self, invocation_id: str | None) -> None:
        self._invocation_id = invocation_id or ""
        self.setToolTip(
            f"invocation: {self._invocation_id}\n点击复制" if invocation_id else "invocation: —"
        )
        self._update_text()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._update_text()

    def _update_text(self) -> None:
        text = f"invocation: {self._invocation_id or '—'}"
        available = max(self.width(), self.fontMetrics().horizontalAdvance("invocation: —"))
        self.setText(self.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle, available))

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._invocation_id:
            QApplication.clipboard().setText(self._invocation_id)
        super().mouseReleaseEvent(event)


class StatusBar(QStatusBar):
    def __init__(self, workspace_id: str = "") -> None:
        super().__init__()
        self._workspace_id = workspace_id
        self.setFixedHeight(STATUS_BAR_HEIGHT)
        self.setObjectName("desktopStatusBar")
        self._started = 0.0
        self._elapsed = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(ELAPSED_TIMER_MS)
        self._timer.timeout.connect(self._update_elapsed)
        content = QWidget()
        layout = QHBoxLayout(content)
        layout.setContentsMargins(SPACE_3, 0, SPACE_3, 0)
        layout.setSpacing(SPACE_2)
        self._dot = StateDot("pending")
        self._connection = QLabel("server: 启动中…")
        self._connection.setFont(font(T5, WEIGHT_SEMIBOLD))
        self._project = QLabel(f"· {workspace_id}" if workspace_id else "")
        self._project.setFont(font(T5))
        self._invocation = _InvocationLabel()
        self._elapsed_label = QLabel("耗时 --")
        self._elapsed_label.setFont(font(T5, mono=True))
        self._workspace_hint = QLabel("目录已折叠 · Ctrl+L 展开")
        self._workspace_hint.setFont(font(T5))
        self._workspace_hint.hide()
        self._badge = StatusBadge("pending", "idle")
        layout.addWidget(self._dot)
        layout.addWidget(self._connection)
        layout.addWidget(self._project)
        layout.addStretch(1)
        layout.addWidget(self._invocation, stretch=1)
        layout.addStretch(1)
        layout.addWidget(self._elapsed_label)
        layout.addWidget(self._workspace_hint)
        layout.addWidget(self._badge)
        self.addWidget(content, stretch=1)
        qconfig.themeChanged.connect(self.refresh_theme)
        self.refresh_theme()

    def set_connection(self, text: str) -> None:
        self._connection.setText(f"server: {text}")
        healthy = text == "正常"
        starting = "启动" in text
        state = "succeeded" if healthy else "pending" if starting else "failed"
        self._dot.set_state(state)
        foreground, _ = state_colors(state)
        self._connection.setStyleSheet(f"color: {foreground}; background: transparent;")

    def set_invocation(self, invocation_id: str | None) -> None:
        self._invocation.set_invocation(invocation_id)

    def set_workspace_panel_visible(self, visible: bool) -> None:
        self._workspace_hint.setVisible(not visible)

    def set_note(self, text: str) -> None:
        if text.startswith("状态："):
            state = text.removeprefix("状态：")
            self._badge.set_state(state)
        elif "运行中" in text or "取消" in text:
            self._badge.set_state("pending", "running" if "运行中" in text else text)
        else:
            self._badge.set_state("pending", text or "idle")

    def start_elapsed(self) -> None:
        self._started = time.monotonic()
        self._elapsed = 0.0
        self._timer.start()
        self._update_elapsed()

    def stop_elapsed(self, state: str) -> None:
        self._timer.stop()
        self._update_elapsed()
        self._badge.set_state(state)

    def _update_elapsed(self) -> None:
        elapsed = time.monotonic() - self._started if self._timer.isActive() else self._elapsed
        if self._timer.isActive():
            self._elapsed = elapsed
        self._elapsed_label.setText(f"耗时 {self._elapsed:.1f}s")

    def refresh_theme(self) -> None:
        colors = palette()
        self.setStyleSheet(
            f"QStatusBar#desktopStatusBar {{ background: {colors.card}; "
            f"border-top: 1px solid {colors.border}; }}"
            f"QStatusBar#desktopStatusBar QWidget {{ background: transparent; border: none; }}"
        )
        self._project.setStyleSheet(f"color: {colors.secondary};")
        self._invocation.setStyleSheet(f"color: {colors.muted};")
        self._elapsed_label.setStyleSheet(f"color: {colors.secondary};")
        self._workspace_hint.setStyleSheet(f"color: {colors.muted};")
