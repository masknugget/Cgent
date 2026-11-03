"""Floating prompt composer with keyboard submission and live character count."""

from __future__ import annotations

import qtawesome
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, PrimaryPushButton, TransparentToolButton

from cgent_desktop.theme.tokens import (
    COMPOSER_MIN_HEIGHT,
    INPUT_MAX_HEIGHT,
    INPUT_MIN_HEIGHT,
    MAX_PROMPT_CHARS,
    RADIUS_COMPOSER,
    SPACE_1,
    SPACE_2,
    SPACE_3,
    SPACE_4,
    T1,
    T3,
    T5,
    WEIGHT_SEMIBOLD,
    font,
    palette,
)
from cgent_desktop.ui.widgets import KeyCap, ThemeAwareCard


class PromptEdit(QPlainTextEdit):
    submitRequested = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                super().keyPressEvent(event)
                return
            event.accept()
            self.submitRequested.emit()
            return
        super().keyPressEvent(event)


class Composer(ThemeAwareCard):
    submitted = Signal(str)
    cancelRequested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("composerCard")
        self._running = False
        self.setMinimumHeight(COMPOSER_MIN_HEIGHT)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_4, SPACE_3, SPACE_4, SPACE_3)
        layout.setSpacing(SPACE_2)
        self._input = PromptEdit()
        self._input.setPlaceholderText("输入任务描述，Enter 发送，Shift+Enter 换行")
        self._input.setMinimumHeight(INPUT_MIN_HEIGHT)
        self._input.setMaximumHeight(INPUT_MAX_HEIGHT)
        self._input.setFont(font(T1))
        self._input.installEventFilter(self)
        self.setFocusProxy(self._input)
        self._action = PrimaryPushButton(FluentIcon.SEND, "发送")
        self._action.setFont(font(T3, WEIGHT_SEMIBOLD))
        self._action.setEnabled(False)
        self._attachment = TransparentToolButton()
        self._attachment.setToolTip("附件功能尚未开放")
        self._attachment.setEnabled(False)
        self._count = QLabel()
        self._count.setFont(font(T5, mono=True))
        self._count.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        bottom = QHBoxLayout()
        bottom.setSpacing(SPACE_2)
        bottom.addWidget(self._attachment)
        bottom.addWidget(self._hint("Enter", "发送"))
        bottom.addWidget(self._hint("Shift+Enter", "换行"))
        slash = KeyCap("/")
        command = QLabel("快捷命令")
        command.setFont(font(T5))
        bottom.addWidget(slash)
        bottom.addWidget(command)
        bottom.addStretch()
        bottom.addWidget(self._count)
        bottom.addSpacing(SPACE_2)
        bottom.addWidget(self._action)
        layout.addWidget(self._input)
        layout.addLayout(bottom)
        self._action.clicked.connect(self._on_action)
        self._input.submitRequested.connect(self._on_action)
        self._input.textChanged.connect(self._on_text_changed)
        self._command_label = command
        self._on_text_changed()
        self.refresh_theme()

    @staticmethod
    def _hint(key: str, text: str) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_1)
        layout.addWidget(KeyCap(key))
        label = QLabel(text)
        label.setFont(font(T5))
        layout.addWidget(label)
        return widget

    def eventFilter(self, obj, e: QEvent) -> bool:  # noqa: N802
        if obj is getattr(self, "_input", None) and e.type() in {
            QEvent.Type.FocusIn,
            QEvent.Type.FocusOut,
        }:
            self.refresh_theme()
        return super().eventFilter(obj, e)

    def _on_action(self) -> None:
        if self._running:
            self.cancelRequested.emit()
            return
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._input.clear()
        self.submitted.emit(text)

    def _on_text_changed(self) -> None:
        text = self._input.toPlainText()
        if len(text) > MAX_PROMPT_CHARS:
            cursor = self._input.textCursor()
            self._input.blockSignals(True)
            self._input.setPlainText(text[:MAX_PROMPT_CHARS])
            cursor.setPosition(MAX_PROMPT_CHARS)
            self._input.setTextCursor(cursor)
            self._input.blockSignals(False)
            text = self._input.toPlainText()
        line_height = self._input.fontMetrics().lineSpacing()
        content_height = self._input.document().blockCount() * line_height + SPACE_4
        self._input.setFixedHeight(min(INPUT_MAX_HEIGHT, max(INPUT_MIN_HEIGHT, content_height)))
        self._count.setText(f"{len(text):,} / {MAX_PROMPT_CHARS:,}")
        self._action.setEnabled(self._running or bool(text.strip()))

    def set_running(self, running: bool) -> None:
        self._running = running
        self._input.setEnabled(not running)
        self._action.setText("停止" if running else "发送")
        self._action.setIcon(FluentIcon.CLOSE if running else FluentIcon.SEND)
        self._on_text_changed()
        self.refresh_theme()
        if not running:
            self._input.setFocus()

    def set_text(self, text: str) -> None:
        self._input.setPlainText(text)
        self._input.moveCursor(self._input.textCursor().MoveOperation.End)
        self._input.setFocus()

    def refresh_theme(self) -> None:
        colors = palette()
        focused = self._input.hasFocus()
        border = colors.primary if focused else colors.input_border
        action_color = colors.failure if self._running else colors.primary
        action_hover = colors.failure if self._running else colors.primary_hover
        self.setStyleSheet(
            f"SimpleCardWidget#composerCard {{ background: {colors.card}; "
            f"border: {2 if focused else 1}px solid {border}; "
            f"border-radius: {RADIUS_COMPOSER}px; }}"
        )
        self._input.setStyleSheet(
            f"QPlainTextEdit {{ background: {colors.card}; color: {colors.text}; "
            f"border: none; padding: {SPACE_1}px; "
            f"selection-background-color: {colors.selection_background}; "
            f"selection-color: {colors.selection_foreground}; }}"
        )
        self._action.setStyleSheet(
            f"PrimaryPushButton {{ background: {action_color}; color: {colors.on_primary}; "
            f"border: none; border-radius: {SPACE_2}px; padding: {SPACE_2}px {SPACE_4}px; }}"
            f"PrimaryPushButton:hover {{ background: {action_hover}; }}"
            f"PrimaryPushButton:disabled {{ background: {colors.primary_soft}; "
            f"color: {colors.muted}; }}"
        )
        self._attachment.setIcon(qtawesome.icon("fa5s.paperclip", color=colors.muted))
        self._attachment.setStyleSheet("TransparentToolButton { border: none; }")
        self._count.setStyleSheet(f"color: {colors.muted}; background: transparent;")
        self._command_label.setStyleSheet(f"color: {colors.secondary}; background: transparent;")
