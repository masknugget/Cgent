"""Collapsible session history and monthly token usage sidebar."""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QResizeEvent
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    CardWidget,
    FluentIcon,
    PrimaryPushButton,
    RoundMenu,
    SearchLineEdit,
    TransparentToolButton,
    qconfig,
)

from cgent_desktop.models.session import SessionRecord
from cgent_desktop.theme.tokens import (
    RADIUS_CARD,
    RADIUS_CONTROL,
    SESSION_DOT_SIZE,
    SIDEBAR_COLLAPSED_WIDTH,
    SIDEBAR_WIDTH,
    SPACE_1,
    SPACE_2,
    SPACE_3,
    SPACE_4,
    SPACE_5,
    T2,
    T3,
    T4,
    T5,
    T6,
    WEIGHT_SEMIBOLD,
    font,
    palette,
    state_colors,
)
from cgent_desktop.ui.widgets import StateDot, ThemeAwareWidget


def _record_date(record: SessionRecord) -> date | None:
    try:
        return datetime.fromisoformat(record.started_at).date()
    except ValueError:
        return None


def _group_name(record: SessionRecord) -> str:
    record_date = _record_date(record)
    today = datetime.now().date()
    if record_date == today:
        return "今 天"
    if record_date is not None and (today - record_date).days == 1:
        return "昨 天"
    return "更 早"


def _record_time(record: SessionRecord) -> str:
    try:
        parsed = datetime.fromisoformat(record.started_at)
    except ValueError:
        return record.started_at[:16] or "—"
    group = _group_name(record)
    if group == "今 天":
        return parsed.strftime("%H:%M")
    if group == "昨 天":
        return "昨天"
    return parsed.strftime("%m-%d")


class SessionCard(CardWidget):
    sessionClicked = Signal(object)
    retryRequested = Signal(str)
    deleteRequested = Signal(object)

    def __init__(self, record: SessionRecord) -> None:
        super().__init__()
        self.record = record
        self._selected = False
        self._collapsed = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_menu)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACE_3, SPACE_2, SPACE_3, SPACE_2)
        layout.setSpacing(SPACE_2)
        self.dot = StateDot(record.state, SESSION_DOT_SIZE)
        self.text = QWidget()
        self.text.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.text.setStyleSheet("background: transparent;")
        text_layout = QVBoxLayout(self.text)
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(SPACE_1)
        self.title = QLabel(record.prompt or "未命名会话")
        self.title.setFont(font(T2, WEIGHT_SEMIBOLD))
        self.title.setToolTip(record.prompt)
        meta = QHBoxLayout()
        meta.setSpacing(SPACE_2)
        self.meta = QLabel(f"{_record_time(record)} · {record.total_tokens:,} tokens")
        self.meta.setFont(font(T5, mono=True))
        self.state = QLabel(record.state)
        self.state.setFont(font(T6, mono=True))
        meta.addWidget(self.meta, stretch=1)
        meta.addWidget(self.state)
        text_layout.addWidget(self.title)
        text_layout.addLayout(meta)
        layout.addWidget(self.dot, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.text, stretch=1)
        self.refresh_theme()
        qconfig.themeChanged.connect(self.refresh_theme)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.refresh_theme()

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.text.setVisible(not collapsed)
        self.setToolTip(self.record.prompt if collapsed else "")
        self.refresh_theme()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.sessionClicked.emit(self.record)
        super().mouseReleaseEvent(e)

    def _show_menu(self, position) -> None:
        menu = RoundMenu(self)
        copy_action = Action(FluentIcon.COPY, "复制会话标题", self)
        copy_action.triggered.connect(lambda: self._copy_title())
        menu.addAction(copy_action)
        if self.record.state == "failed":
            retry_action = Action(FluentIcon.SYNC, "重新运行", self)
            retry_action.triggered.connect(lambda: self.retryRequested.emit(self.record.prompt))
            menu.addAction(retry_action)
        menu.addSeparator()
        delete_action = Action(FluentIcon.DELETE, "删除", self)
        delete_action.triggered.connect(lambda: self.deleteRequested.emit(self.record))
        menu.addAction(delete_action)
        menu.exec(self.mapToGlobal(position))

    def _copy_title(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.record.prompt)

    def _normalBackgroundColor(self) -> QColor:  # noqa: N802
        if getattr(self, "_selected", False):
            return QColor(palette().sidebar_selected)
        return QColor(0, 0, 0, 0)

    def _hoverBackgroundColor(self) -> QColor:  # noqa: N802
        return QColor(palette().sidebar_hover)

    def refresh_theme(self) -> None:
        self._updateBackgroundColor()
        colors = palette()
        foreground, _ = state_colors(self.record.state)
        background = colors.sidebar_selected if self._selected else "transparent"
        border = colors.sidebar_border if self._selected else "transparent"
        self.setStyleSheet(
            f"SessionCard {{ background: {background}; border: 1px solid {border}; "
            f"border-radius: {RADIUS_CARD}px; }}"
            f"SessionCard:hover {{ background: {colors.sidebar_hover}; }}"
        )
        self.title.setStyleSheet(
            f"color: {colors.sidebar_text}; background: transparent; border: none;"
        )
        self.meta.setStyleSheet(
            f"color: {colors.sidebar_muted}; background: transparent; border: none;"
        )
        self.state.setStyleSheet(f"color: {foreground}; background: transparent; border: none;")


class Sidebar(ThemeAwareWidget):
    newSessionRequested = Signal()
    sessionSelected = Signal(object)
    retryRequested = Signal(str)
    deleteRequested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("desktopSidebar")
        self._records: list[SessionRecord] = []
        self._cards: list[SessionCard] = []
        self._selected: SessionCard | None = None
        self._collapsed = False
        self.setFixedWidth(SIDEBAR_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(SPACE_3, SPACE_3, SPACE_3, SPACE_3)
        layout.setSpacing(SPACE_3)
        self.search = SearchLineEdit()
        self.search.setPlaceholderText("搜索会话…")
        self.search.setFixedHeight(SPACE_5 + SPACE_4)
        self.shortcut = QLabel("Ctrl K", self.search)
        self.shortcut.setFont(font(T6, mono=True))
        self.shortcut.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.shortcut.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.search_button = TransparentToolButton(FluentIcon.SEARCH)
        self.search_button.setToolTip("搜索会话（Ctrl+K）")
        self.search_button.setVisible(False)
        self.search_button.clicked.connect(self.focus_search)
        self.new_button = PrimaryPushButton(FluentIcon.ADD, "新建会话")
        self.new_button.setFont(font(T3, WEIGHT_SEMIBOLD))
        self.new_button.setFixedHeight(SPACE_5 + SPACE_4)
        self.new_button.clicked.connect(self.newSessionRequested)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.usage = QWidget()
        usage_layout = QVBoxLayout(self.usage)
        usage_layout.setContentsMargins(SPACE_1, SPACE_3, SPACE_1, 0)
        usage_layout.setSpacing(SPACE_2)
        self.usage_title = QLabel("本月用量")
        self.usage_title.setFont(font(T6, WEIGHT_SEMIBOLD))
        usage_layout.addWidget(self.usage_title)
        self.usage_values: list[QLabel] = []
        for label_text, value in (("输入 / 输出", "0 / 0"), ("剩余额度", "—")):
            row = QHBoxLayout()
            label = QLabel(label_text)
            label.setFont(font(T5))
            value_label = QLabel(value)
            value_label.setFont(font(T5, mono=True))
            value_label.setAlignment(Qt.AlignmentFlag.AlignRight)
            row.addWidget(label)
            row.addWidget(value_label)
            usage_layout.addLayout(row)
            self.usage_values.append(value_label)
            label.setStyleSheet("background: transparent; border: none;")
        self.usage_values[-1].setToolTip("未配置额度数据")
        layout.addWidget(self.search)
        layout.addWidget(self.search_button, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.new_button)
        layout.addWidget(self.scroll_area, stretch=1)
        layout.addWidget(self.usage)
        self.search.textChanged.connect(self._rebuild)
        self.refresh_theme()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._position_shortcut()

    def _position_shortcut(self) -> None:
        self.shortcut.adjustSize()
        x = self.search.width() - self.shortcut.width() - SPACE_3
        y = (self.search.height() - self.shortcut.height()) // 2
        self.shortcut.move(max(SPACE_2, x), y)
        self.search.setTextMargins(0, 0, self.shortcut.width() + SPACE_4, 0)

    @property
    def collapsed(self) -> bool:
        return self._collapsed

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.setFixedWidth(SIDEBAR_COLLAPSED_WIDTH if collapsed else SIDEBAR_WIDTH)
        self.search.setVisible(not collapsed)
        self.search_button.setVisible(collapsed)
        self.usage.setVisible(not collapsed)
        self.new_button.setText("" if collapsed else "新建会话")
        self.new_button.setToolTip("新建会话" if collapsed else "")
        self._rebuild()

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def focus_search(self) -> None:
        if self._collapsed:
            self.set_collapsed(False)
        self.search.setFocus()
        self.search.selectAll()

    def set_records(self, records: list[SessionRecord]) -> None:
        self._records = records
        self._selected = None
        self._rebuild()
        self._update_usage()

    def _rebuild(self) -> None:
        query = self.search.text().strip().casefold()
        records = [record for record in self._records if query in record.prompt.casefold()]
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACE_2)
        self._cards = []
        current_group = ""
        for record in records:
            group = _group_name(record)
            if not self._collapsed and group != current_group:
                group_label = QLabel(group)
                group_label.setFont(font(T6, WEIGHT_SEMIBOLD))
                group_label.setStyleSheet(
                    f"color: {palette().sidebar_muted}; background: transparent; "
                    f"border: none; padding-top: {SPACE_2}px;"
                )
                layout.addWidget(group_label)
                current_group = group
            card = SessionCard(record)
            card.set_collapsed(self._collapsed)
            card.sessionClicked.connect(self._select_card)
            card.retryRequested.connect(self.retryRequested)
            card.deleteRequested.connect(self.deleteRequested)
            self._cards.append(card)
            layout.addWidget(card)
        if not records and not self._collapsed:
            empty = QLabel("没有匹配的会话" if query else "暂无历史会话")
            empty.setFont(font(T4))
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                f"color: {palette().sidebar_muted}; background: transparent; border: none;"
            )
            layout.addWidget(empty)
        layout.addStretch()
        old = self.scroll_area.takeWidget()
        if old is not None:
            old.deleteLater()
        self.scroll_area.setWidget(container)
        self.refresh_theme()

    def _select_card(self, record: SessionRecord) -> None:
        for card in self._cards:
            selected = card.record is record
            card.set_selected(selected)
            if selected:
                self._selected = card
        self.sessionSelected.emit(record)

    def _update_usage(self) -> None:
        now = datetime.now()
        monthly = []
        for record in self._records:
            try:
                started = datetime.fromisoformat(record.started_at)
            except ValueError:
                continue
            if (started.year, started.month) == (now.year, now.month):
                monthly.append(record)
        input_tokens = sum(record.input_tokens for record in monthly)
        output_tokens = sum(record.output_tokens for record in monthly)
        self.usage_values[0].setText(f"{input_tokens:,} / {output_tokens:,}")

    def refresh_theme(self) -> None:
        colors = palette()
        self.setStyleSheet(
            f"QWidget#desktopSidebar {{ background: {colors.sidebar}; "
            f"border-right: 1px solid {colors.sidebar_border}; }}"
        )
        self.search.setStyleSheet(
            f"SearchLineEdit {{ background: {colors.sidebar_input}; color: {colors.sidebar_text}; "
            f"border: 1px solid {colors.sidebar_border}; border-radius: {RADIUS_CONTROL}px; }}"
        )
        self.shortcut.setStyleSheet(
            f"color: {colors.sidebar_muted}; background: {colors.sidebar_selected}; "
            f"border: 1px solid {colors.sidebar_border}; border-radius: {SPACE_1}px; "
            f"padding: 0 {SPACE_1}px;"
        )
        self.new_button.setStyleSheet(
            f"PrimaryPushButton {{ background: {colors.primary}; color: {colors.on_primary}; "
            f"border: none; border-radius: {RADIUS_CONTROL}px; }}"
            f"PrimaryPushButton:hover {{ background: {colors.primary_hover}; }}"
        )
        self.search_button.setStyleSheet(
            f"TransparentToolButton {{ color: {colors.sidebar_text}; border: none; }}"
            f"TransparentToolButton:hover {{ background: {colors.sidebar_hover}; }}"
        )
        self.scroll_area.setStyleSheet("QScrollArea { background: transparent; border: none; }")
        self.usage.setStyleSheet(
            f"QWidget {{ background: transparent; border-top: 1px solid {colors.sidebar_border}; }}"
            f"QLabel {{ color: {colors.sidebar_muted}; background: transparent; border: none; }}"
        )
        self.usage_title.setStyleSheet(
            f"color: {colors.sidebar_muted}; background: transparent; border: none;"
        )
        for value in self.usage_values:
            value.setStyleSheet(
                f"color: {colors.sidebar_text}; background: transparent; border: none;"
            )
