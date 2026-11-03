"""Collapsible tool-call cards and syntax-highlighted read-only logs."""

from __future__ import annotations

import qtawesome
from PySide6.QtCore import QRegularExpression, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QSyntaxHighlighter, QTextCharFormat
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPlainTextEdit, QVBoxLayout, QWidget
from qfluentwidgets import FluentIcon, SimpleCardWidget, TransparentToolButton, qconfig

from cgent_desktop.theme.tokens import (
    LOG_MIN_HEIGHT,
    RADIUS_CARD,
    RADIUS_CONTROL,
    SPACE_1,
    SPACE_2,
    SPACE_3,
    T3,
    T4,
    T5,
    TOOL_HEADER_HEIGHT,
    TOOL_ICON_SIZE,
    WEIGHT_SEMIBOLD,
    font,
    palette,
)
from cgent_desktop.ui.widgets import StatusBadge
from cgent_tui.models import ToolCallSummary, Usage


def format_tool_call(call: ToolCallSummary) -> str:
    """``tool read_file: completed (exit 0)``-style single line."""
    suffix = ""
    if call.exit_code is not None:
        suffix = f" (exit {call.exit_code})"
    elif call.error:
        suffix = f" ({call.error})"
    return f"tool {call.name}: {call.status}{suffix}"


class TerminalHighlighter(QSyntaxHighlighter):
    def __init__(self, document) -> None:
        super().__init__(document)
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []
        self.refresh_theme()

    def refresh_theme(self) -> None:
        colors = palette()
        self._rules = []

        def add(pattern: str, color: str, *, bold: bool = False) -> None:
            text_format = QTextCharFormat()
            text_format.setForeground(QColor(color))
            if bold:
                text_format.setFontWeight(font(T4, WEIGHT_SEMIBOLD).weight())
            self._rules.append((QRegularExpression(pattern), text_format))

        add(r"(?i)\b(error|failed|exception)\b", colors.terminal_error, bold=True)
        add(r"^tool\s+[^\s]+", colors.on_primary, bold=True)
        add(r"(?:[A-Za-z]:)?[^\s()]+\.[A-Za-z]+(?::\d+)?", colors.terminal_path)
        add(r"#.*$", colors.terminal_comment)
        add(r"\b(exit|status)\s+\d+\b", colors.terminal_path)
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        for expression, text_format in self._rules:
            matches = expression.globalMatch(text)
            while matches.hasNext():
                match = matches.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), text_format)


class _ToolHeader(QWidget):
    clicked = Signal()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ToolCallCard(SimpleCardWidget):
    def __init__(self, call: ToolCallSummary) -> None:
        super().__init__()
        self.call = call
        self._expanded = False
        self.setObjectName("toolCallCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = _ToolHeader()
        self.header.setFixedHeight(TOOL_HEADER_HEIGHT)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(SPACE_3, 0, SPACE_3, 0)
        header_layout.setSpacing(SPACE_2)
        self.icon = TransparentToolButton()
        self.icon.setFixedSize(TOOL_ICON_SIZE, TOOL_ICON_SIZE)
        self.icon.setEnabled(False)
        self.name = QLabel(call.name)
        self.name.setFont(font(T3, WEIGHT_SEMIBOLD, mono=True))
        if call.error:
            summary = call.error
        elif call.exit_code is not None:
            summary = f"exit {call.exit_code}"
        else:
            summary = call.status
        self.summary = QLabel(summary)
        self.summary.setFont(font(T4))
        self.summary.setToolTip(summary)
        state = {"completed": "成功", "failed": "失败", "pending": "执行中"}[call.status]
        self.badge = StatusBadge(call.status, state)
        self.duration = QLabel("--")
        self.duration.setFont(font(T5, mono=True))
        self.arrow = TransparentToolButton(FluentIcon.CHEVRON_DOWN_MED)
        self.arrow.setFixedSize(TOOL_ICON_SIZE, TOOL_ICON_SIZE)
        header_layout.addWidget(self.icon)
        header_layout.addWidget(self.name)
        header_layout.addWidget(self.summary, stretch=1)
        header_layout.addWidget(self.badge)
        header_layout.addWidget(self.duration)
        header_layout.addWidget(self.arrow)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.log.setFont(font(T4, mono=True))
        self.log.setFixedHeight(LOG_MIN_HEIGHT)
        self.log.setPlainText(format_tool_call(call))
        self.highlighter = TerminalHighlighter(self.log.document())
        self.log.setVisible(False)
        layout.addWidget(self.header)
        layout.addWidget(self.log)
        self.header.clicked.connect(self.toggle)
        self.arrow.clicked.connect(self.toggle)
        qconfig.themeChanged.connect(self.refresh_theme)
        self.refresh_theme()

    @property
    def expanded(self) -> bool:
        return self._expanded

    def toggle(self) -> None:
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self.log.setVisible(expanded)
        self.arrow.setIcon(FluentIcon.CARE_UP_SOLID if expanded else FluentIcon.CHEVRON_DOWN_MED)
        self.setAccessibleDescription("已展开" if expanded else "已折叠")

    def _normalBackgroundColor(self) -> QColor:  # noqa: N802
        return QColor(palette().card)

    def refresh_theme(self) -> None:
        self._updateBackgroundColor()
        colors = palette()
        border = colors.failure if self.call.status == "failed" else colors.border
        self.setStyleSheet(
            f"SimpleCardWidget#toolCallCard {{ background: {colors.card}; "
            f"border: 1px solid {border}; border-radius: {RADIUS_CARD}px; }}"
        )
        self.header.setStyleSheet("QWidget { background: transparent; border: none; }")
        self.icon.setIcon(qtawesome.icon("fa5s.wrench", color=colors.primary))
        self.icon.setStyleSheet(
            f"TransparentToolButton {{ background: {colors.primary_soft}; border: none; "
            f"border-radius: {RADIUS_CONTROL}px; }}"
        )
        self.name.setStyleSheet(f"color: {colors.text}; background: transparent;")
        self.summary.setStyleSheet(f"color: {colors.secondary}; background: transparent;")
        self.duration.setStyleSheet(f"color: {colors.muted}; background: transparent;")
        self.badge.refresh_theme()
        self.log.setStyleSheet(
            f"QPlainTextEdit {{ background: {colors.terminal}; color: {colors.terminal_text}; "
            f"border: none; border-bottom-left-radius: {RADIUS_CARD}px; "
            f"border-bottom-right-radius: {RADIUS_CARD}px; padding: {SPACE_3}px; "
            f"selection-background-color: {colors.selection_background}; "
            f"selection-color: {colors.selection_foreground}; }}"
        )
        self.highlighter.refresh_theme()


class ToolRound(QWidget):
    def __init__(self, calls: tuple[ToolCallSummary, ...], usage: Usage | None) -> None:
        super().__init__()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(SPACE_2)
        self.cards = [ToolCallCard(call) for call in calls]
        for card in self.cards:
            self._layout.addWidget(card)
        summary_row = QHBoxLayout()
        summary_row.setContentsMargins(0, SPACE_1, 0, 0)
        summary_text = f"本轮共调用 {len(calls)} 个工具"
        if usage is not None:
            summary_text += f" · tokens in {usage.input_tokens:,} / out {usage.output_tokens:,}"
        self.summary = QLabel(summary_text)
        self.summary.setFont(font(T5))
        self.expand_all = TransparentToolButton(FluentIcon.CHEVRON_DOWN_MED, "全部展开")
        self.collapse_all = TransparentToolButton(FluentIcon.CARE_UP_SOLID, "全部收起")
        summary_row.addWidget(self.summary, stretch=1)
        summary_row.addWidget(self.expand_all)
        summary_row.addWidget(self.collapse_all)
        self._layout.addLayout(summary_row)
        self.expand_all.clicked.connect(self.expand_all_cards)
        self.collapse_all.clicked.connect(self.collapse_all_cards)
        qconfig.themeChanged.connect(self.refresh_theme)
        self.refresh_theme()

    def expand_all_cards(self) -> None:
        for card in self.cards:
            card.set_expanded(True)

    def collapse_all_cards(self) -> None:
        for card in self.cards:
            card.set_expanded(False)

    def refresh_theme(self) -> None:
        colors = palette()
        self.summary.setStyleSheet(f"color: {colors.muted}; background: transparent; border: none;")
        for button in (self.expand_all, self.collapse_all):
            button.setStyleSheet(
                f"TransparentToolButton {{ color: {colors.secondary}; border: none; "
                f"padding: 0 {SPACE_2}px; }}"
            )
