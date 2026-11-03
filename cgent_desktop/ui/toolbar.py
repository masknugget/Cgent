"""Workspace toolbar above the conversation."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel
from qfluentwidgets import FluentIcon, PushButton, TransparentToolButton
from superqt import QSearchableComboBox

from cgent_desktop.theme.tokens import (
    RADIUS_CONTROL,
    SPACE_1,
    SPACE_2,
    SPACE_3,
    SPACE_7,
    T2,
    T3,
    T6,
    TOOLBAR_HEIGHT,
    WEIGHT_SEMIBOLD,
    font,
    palette,
)
from cgent_desktop.ui.widgets import ThemeAwareWidget


class WorkspaceToolbar(ThemeAwareWidget):
    rerunRequested = Signal()
    settingsRequested = Signal()

    def __init__(self, workspace_id: str, model_id: str) -> None:
        super().__init__()
        self.setFixedHeight(TOOLBAR_HEIGHT)
        self.setObjectName("workspaceToolbar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_7, SPACE_2, SPACE_7, SPACE_2)
        layout.setSpacing(SPACE_3)
        self.project = QLabel(workspace_id)
        self.project.setFont(font(T2, WEIGHT_SEMIBOLD))
        self.workspace_tag = QLabel("默认工作区")
        self.workspace_tag.setFont(font(T6, WEIGHT_SEMIBOLD))
        self.model = QSearchableComboBox()
        self.model.addItems([f"{model_id} · auto"])
        self.model.setFixedWidth(190)
        self.model.setFont(font(T3))
        self.model.setToolTip("当前模型（由 server 配置）")
        self.rerun = PushButton(FluentIcon.SYNC, "重新运行")
        self.rerun.setFont(font(T3))
        self.settings = TransparentToolButton(FluentIcon.SETTING)
        self.settings.setToolTip("设置")
        layout.addWidget(self.project)
        layout.addWidget(self.workspace_tag)
        layout.addStretch()
        layout.addWidget(self.model)
        layout.addWidget(self.rerun)
        layout.addWidget(self.settings)
        self.rerun.clicked.connect(self.rerunRequested)
        self.settings.clicked.connect(self.settingsRequested)
        self.refresh_theme()

    def set_running(self, running: bool) -> None:
        self.rerun.setEnabled(not running)

    def refresh_theme(self) -> None:
        colors = palette()
        self.setStyleSheet(
            f"QWidget#workspaceToolbar {{ background: {colors.card}; "
            f"border-bottom: 1px solid {colors.border}; }}"
            f"QWidget#workspaceToolbar QLabel {{ background: transparent; border: none; }}"
        )
        self.project.setStyleSheet(f"color: {colors.text};")
        self.workspace_tag.setStyleSheet(
            f"color: {colors.primary}; background: {colors.primary_soft}; "
            f"border-radius: {RADIUS_CONTROL}px; padding: {SPACE_2 / 2:.0f}px {SPACE_2}px;"
        )
        self.model.setStyleSheet(
            f"QComboBox {{ background: {colors.card}; color: {colors.text}; "
            f"border: 1px solid {colors.border}; border-radius: {RADIUS_CONTROL}px; "
            f"padding: {SPACE_1}px {SPACE_2}px; }}"
        )
