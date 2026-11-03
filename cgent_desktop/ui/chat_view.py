"""Scrollable Markdown conversation with user and assistant message bubbles."""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPaintEvent, QTextDocument
from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget
from qfluentwidgets import qconfig

from cgent_desktop.models.session import SessionRecord
from cgent_desktop.theme.tokens import (
    MESSAGE_MAX_WIDTH,
    MESSAGE_MIN_WIDTH,
    RADIUS_BUBBLE,
    RADIUS_CARD,
    SPACE_1,
    SPACE_2,
    SPACE_3,
    SPACE_4,
    SPACE_7,
    T1,
    T2,
    T5,
    WEIGHT_SEMIBOLD,
    font,
    palette,
)
from cgent_desktop.ui.tool_calls import ToolRound
from cgent_desktop.ui.widgets import Avatar, EmptyState, ThemeAwareCard, ThemeAwareWidget
from cgent_tui.models import RunOutcome, Usage


def markdown_to_html(text: str) -> str:
    document = QTextDocument()
    document.setDefaultFont(font(T1))
    document.setMarkdown(text)
    return document.toHtml()


class MessageBubble(ThemeAwareWidget):
    def __init__(self, role: str, text: str) -> None:
        super().__init__()
        self.role = role
        self.source_text = text
        self.setObjectName("messageBubble")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAutoFillBackground(False)
        self._background = QColor()
        self._radii = (RADIUS_BUBBLE, SPACE_1, RADIUS_BUBBLE, RADIUS_BUBBLE)
        if role == "assistant":
            self.setMinimumWidth(MESSAGE_MIN_WIDTH)
        self.setMaximumWidth(MESSAGE_MAX_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_4, SPACE_3, SPACE_4, SPACE_3)
        layout.setSpacing(0)
        self.body = QLabel()
        self.body.setObjectName("messageBody")
        self.body.setFont(font(T1))
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.TextFormat.RichText)
        self.body.setText(markdown_to_html(text))
        self.body.setOpenExternalLinks(True)
        self.body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
            | Qt.TextInteractionFlag.LinksAccessibleByMouse
        )
        self.body.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        layout.addWidget(self.body)
        self.refresh_theme()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        top_left, top_right, bottom_right, bottom_left = self._radii
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        left, top = rect.left(), rect.top()
        right, bottom = rect.right(), rect.bottom()
        path = QPainterPath()
        path.moveTo(left + top_left, top)
        path.lineTo(right - top_right, top)
        path.arcTo(right - 2 * top_right, top, 2 * top_right, 2 * top_right, 90, -90)
        path.lineTo(right, bottom - bottom_right)
        path.arcTo(
            right - 2 * bottom_right,
            bottom - 2 * bottom_right,
            2 * bottom_right,
            2 * bottom_right,
            0,
            -90,
        )
        path.lineTo(left + bottom_left, bottom)
        path.arcTo(left, bottom - 2 * bottom_left, 2 * bottom_left, 2 * bottom_left, 270, -90)
        path.lineTo(left, top + top_left)
        path.arcTo(left, top, 2 * top_left, 2 * top_left, 180, -90)
        path.closeSubpath()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._background)
        painter.drawPath(path)

    def refresh_theme(self) -> None:
        colors = palette()
        if self.role == "user":
            self._background = QColor(colors.primary)
            foreground = colors.on_primary
            self._radii = (RADIUS_BUBBLE, SPACE_1, RADIUS_BUBBLE, RADIUS_BUBBLE)
        else:
            self._background = QColor(colors.card)
            foreground = colors.text
            self._radii = (SPACE_1, RADIUS_BUBBLE, RADIUS_BUBBLE, RADIUS_BUBBLE)
        self.setStyleSheet(
            f"QLabel#messageBody {{ color: {foreground}; background: transparent; "
            f"border: none; selection-background-color: {colors.primary_soft}; }}"
        )
        self.update()


class MessageWidget(ThemeAwareWidget):
    def __init__(self, role: str, text: str) -> None:
        super().__init__()
        self.role = role
        self.setObjectName("messageRow")
        self.bubble = MessageBubble(role, text)
        now = datetime.now().strftime("%H:%M:%S")
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(SPACE_3)
        content = QWidget()
        content.setObjectName("messageContent")
        content.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        content.setStyleSheet("QWidget#messageContent { background: transparent; border: none; }")
        content.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Minimum)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(SPACE_2)
        meta = QHBoxLayout()
        self.time = QLabel(now)
        self.time.setFont(font(T5, mono=True))
        self.name = QLabel("我" if role == "user" else "Cgent Agent")
        self.name.setFont(font(T2, WEIGHT_SEMIBOLD))
        if role == "user":
            meta.addStretch()
            meta.addWidget(self.time)
            meta.addWidget(self.name)
        else:
            meta.addWidget(self.name)
            meta.addWidget(self.time)
            meta.addStretch()
        content_layout.addLayout(meta)
        content_layout.addWidget(self.bubble)
        if role == "user":
            outer.addStretch()
            outer.addWidget(content, alignment=Qt.AlignmentFlag.AlignTop)
            outer.addWidget(Avatar("我"), alignment=Qt.AlignmentFlag.AlignTop)
        else:
            outer.addWidget(Avatar("C"), alignment=Qt.AlignmentFlag.AlignTop)
            outer.addWidget(content, alignment=Qt.AlignmentFlag.AlignTop)
            outer.addStretch()
        self.refresh_theme()

    def refresh_theme(self) -> None:
        colors = palette()
        self.setStyleSheet("QWidget#messageRow { background: transparent; border: none; }")
        self.name.setStyleSheet(f"color: {colors.text}; background: transparent;")
        self.time.setStyleSheet(f"color: {colors.muted}; background: transparent;")


class _ProgressCard(ThemeAwareCard):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("progressCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_4, SPACE_2, SPACE_4, SPACE_2)
        self.label = QLabel("正在运行…")
        self.label.setFont(font(T5))
        layout.addWidget(self.label)
        self.refresh_theme()

    def set_text(self, text: str) -> None:
        self.label.setText(f"正在运行… {text}")
        self.label.setToolTip(text)

    def refresh_theme(self) -> None:
        colors = palette()
        self.setStyleSheet(
            f"SimpleCardWidget#progressCard {{ background: {colors.primary_soft}; "
            f"border: 1px solid {colors.border}; border-radius: {RADIUS_CARD}px; }}"
        )
        self.label.setStyleSheet(f"color: {colors.primary}; background: transparent;")


class ChatView(QScrollArea):
    """Read-only transcript of the current session."""

    def __init__(self) -> None:
        super().__init__()
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setObjectName("chatScrollArea")
        self.container = QWidget()
        self.container.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._content_layout = QVBoxLayout(self.container)
        self._content_layout.setContentsMargins(SPACE_7, SPACE_7, SPACE_7, SPACE_7)
        self._content_layout.setSpacing(SPACE_4)
        self._content_layout.addStretch()
        self.setWidget(self.container)
        self.messages: list[MessageWidget] = []
        self.tool_rounds: list[ToolRound] = []
        self._progress: _ProgressCard | None = None
        self._empty = EmptyState()
        self._content_layout.insertWidget(0, self._empty)
        qconfig.themeChanged.connect(self.refresh_theme)
        self.refresh_theme()

    def _remove_empty(self) -> None:
        if self._empty is not None:
            self._content_layout.removeWidget(self._empty)
            self._empty.hide()
            self._empty.deleteLater()
            self._empty = None

    def _add_message(self, role: str, text: str) -> None:
        self._remove_empty()
        message = MessageWidget(role, text)
        self.messages.append(message)
        self._content_layout.insertWidget(self._content_layout.count() - 1, message)
        self._scroll_to_bottom()

    def add_user_message(self, text: str) -> None:
        self._add_message("user", text)

    def add_progress(self, text: str) -> None:
        self._remove_empty()
        if self._progress is None:
            self._progress = _ProgressCard()
            self._content_layout.insertWidget(self._content_layout.count() - 1, self._progress)
        self._progress.set_text(text)
        self._scroll_to_bottom()

    def add_outcome(self, outcome: RunOutcome) -> None:
        self._clear_progress()
        if outcome.output:
            self._add_message("assistant", outcome.output.rstrip("\n"))
        elif outcome.detail:
            self._add_message("assistant", outcome.detail)
        if outcome.tool_calls:
            self._remove_empty()
            tool_round = ToolRound(outcome.tool_calls, outcome.usage)
            tool_round.setMaximumWidth(MESSAGE_MAX_WIDTH)
            row = QWidget()
            row.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            row.setStyleSheet("background: transparent;")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addSpacing(SPACE_7 + SPACE_4)
            row_layout.addWidget(tool_round)
            row_layout.addStretch()
            self.tool_rounds.append(tool_round)
            self._content_layout.insertWidget(self._content_layout.count() - 1, row)
        elif outcome.usage is not None:
            self._add_usage(outcome.usage)
        self._scroll_to_bottom()

    def _add_usage(self, usage: Usage) -> None:
        self._remove_empty()
        label = QLabel(
            f"tokens: in {usage.input_tokens} / out {usage.output_tokens} / "
            f"total {usage.total_tokens}"
        )
        label.setFont(font(T5, mono=True))
        label.setStyleSheet(f"color: {palette().muted}; background: transparent;")
        self._content_layout.insertWidget(self._content_layout.count() - 1, label)

    def _clear_progress(self) -> None:
        if self._progress is not None:
            self._content_layout.removeWidget(self._progress)
            self._progress.deleteLater()
            self._progress = None

    def collapse_all_tools(self) -> None:
        for tool_round in self.tool_rounds:
            tool_round.collapse_all_cards()

    def show_history(self, record: SessionRecord) -> None:
        self.clear()
        self.add_user_message(record.prompt)
        self.add_outcome(
            RunOutcome(
                state=record.state
                if record.state in {"succeeded", "failed", "cancelled", "unknown"}
                else "unknown",
                detail=record.detail or "该历史会话没有保存输出摘要。",
            )
        )

    def clear(self) -> None:
        self._clear_progress()
        for message in self.messages:
            self._content_layout.removeWidget(message)
            message.deleteLater()
        for tool_round in self.tool_rounds:
            self._content_layout.removeWidget(tool_round)
            tool_round.deleteLater()
        self.messages.clear()
        self.tool_rounds.clear()
        while self._content_layout.count() > 1:
            item = self._content_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._empty = EmptyState()
        self._content_layout.insertWidget(0, self._empty)

    def _scroll_to_bottom(self) -> None:
        QTimer.singleShot(
            0,
            lambda: self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()),
        )

    def refresh_theme(self) -> None:
        colors = palette()
        self.container.setObjectName("chatContainer")
        self.setStyleSheet(
            f"QScrollArea#chatScrollArea {{ background: {colors.workspace}; border: none; }}"
            f"QWidget#chatContainer {{ background: {colors.workspace}; border: none; }}"
        )
