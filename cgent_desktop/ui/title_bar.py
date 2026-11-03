"""Branded frameless title bar with standard window controls."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QMouseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget
from qfluentwidgets import FluentIcon, TransparentToolButton, qconfig

from cgent_desktop.theme.tokens import (
    LOGO_SIZE,
    SPACE_2,
    SPACE_3,
    T2,
    T4,
    TITLE_BAR_HEIGHT,
    WEIGHT_SEMIBOLD,
    WINDOW_CONTROL_WIDTH,
    font,
    palette,
)
from cgent_desktop.ui.widgets import Avatar


class TitleBar(QWidget):
    def __init__(self, workspace_id: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(TITLE_BAR_HEIGHT)
        self.setObjectName("desktopTitleBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_3, 0, 0, 0)
        layout.setSpacing(SPACE_2)
        self.logo = Avatar("C", LOGO_SIZE)
        self.title = QLabel("Cgent Desktop")
        self.title.setFont(font(T2, WEIGHT_SEMIBOLD))
        self.workspace = QLabel(f"— {workspace_id}")
        self.workspace.setFont(font(T4))
        self.collapse_button = TransparentToolButton(FluentIcon.MENU)
        self.collapse_button.setToolTip("折叠或展开侧栏")
        self.minimize_button = TransparentToolButton(FluentIcon.MINIMIZE)
        self.maximize_button = TransparentToolButton(FluentIcon.FULL_SCREEN)
        self.close_button = TransparentToolButton(FluentIcon.CLOSE)
        for button in (self.minimize_button, self.maximize_button, self.close_button):
            button.setFixedWidth(WINDOW_CONTROL_WIDTH)
        layout.addWidget(self.logo)
        layout.addWidget(self.title)
        layout.addWidget(self.workspace)
        layout.addStretch()
        layout.addWidget(self.collapse_button)
        layout.addWidget(self.minimize_button)
        layout.addWidget(self.maximize_button)
        layout.addWidget(self.close_button)

        window = self.window()
        self.minimize_button.clicked.connect(window.showMinimized)
        self.maximize_button.clicked.connect(self._toggle_maximized)
        self.close_button.clicked.connect(window.close)
        qconfig.themeChanged.connect(self.refresh_theme)
        self.refresh_theme()

    def _toggle_maximized(self) -> None:
        window = self.window()
        if window.isMaximized():
            window.showNormal()
        else:
            window.showMaximized()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None and hasattr(handle, "startSystemMove"):
                handle.startSystemMove()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximized()
        super().mouseDoubleClickEvent(event)

    def refresh_theme(self) -> None:
        colors = palette()
        self.setStyleSheet(
            f"QWidget#desktopTitleBar {{ background: {colors.sidebar}; }}"
            f"QWidget#desktopTitleBar QLabel {{ background: transparent; border: none; }}"
        )
        self.title.setStyleSheet(f"color: {colors.sidebar_text};")
        self.workspace.setStyleSheet(f"color: {colors.sidebar_muted};")
        self.collapse_button.setIcon(FluentIcon.MENU.icon(color=QColor(colors.sidebar_muted)))
        self.minimize_button.setIcon(FluentIcon.MINIMIZE.icon(color=QColor(colors.sidebar_muted)))
        self.maximize_button.setIcon(
            FluentIcon.FULL_SCREEN.icon(color=QColor(colors.sidebar_muted))
        )
        self.close_button.setIcon(FluentIcon.CLOSE.icon(color=QColor(colors.sidebar_muted)))
        for button in (
            self.collapse_button,
            self.minimize_button,
            self.maximize_button,
            self.close_button,
        ):
            button.setStyleSheet(
                f"TransparentToolButton {{ color: {colors.sidebar_muted}; border: none; }}"
                f"TransparentToolButton:hover {{ background: {colors.sidebar_hover}; }}"
            )
