"""Collapsible session history, inline renaming and monthly token usage."""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QResizeEvent, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    Action,
    CardWidget,
    FluentIcon,
    LineEdit,
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
from cgent_desktop.ui.i18n import (
    COPY_TITLE,
    DELETE,
    EMPTY_HISTORY,
    NEW_SESSION,
    NO_MATCHING_HISTORY,
    RENAME,
    RETRY,
    UNNAMED_SESSION,
    tr,
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


class ElidedLabel(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text)
        self._full_text = text
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.setMinimumWidth(0)

    def set_full_text(self, text: str) -> None:
        self._full_text = text
        self.refresh_elision()

    def refresh_elision(self) -> None:
        width = max(0, self.width())
        self.setText(
            self.fontMetrics().elidedText(self._full_text, Qt.TextElideMode.ElideRight, width)
        )

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self.refresh_elision()


class SessionCard(CardWidget):
    sessionClicked = Signal(object)
    retryRequested = Signal(str)
    deleteRequested = Signal(object)
    renameRequested = Signal(object, str)

    def __init__(self, record: SessionRecord) -> None:
        super().__init__()
        self.record = record
        self._selected = False
        self._collapsed = False
        self._renaming = False
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
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
        title = record.display_title or tr(UNNAMED_SESSION)
        self.title = ElidedLabel(title)
        self.title.setFont(font(T2, WEIGHT_SEMIBOLD))
        self.title.setToolTip(title)
        self.title_edit = LineEdit()
        self.title_edit.setFont(font(T2, WEIGHT_SEMIBOLD))
        self.title_edit.setText(record.display_title)
        self.title_edit.setVisible(False)
        self.title_edit.installEventFilter(self)
        meta = QHBoxLayout()
        meta.setSpacing(SPACE_2)
        self.meta = QLabel(f"{_record_time(record)} · {record.total_tokens:,} tokens")
        self.meta.setFont(font(T5, mono=True))
        self.state = QLabel(record.state)
        self.state.setFont(font(T6, mono=True))
        meta.addWidget(self.meta, stretch=1)
        meta.addWidget(self.state)
        text_layout.addWidget(self.title)
        text_layout.addWidget(self.title_edit)
        text_layout.addLayout(meta)
        layout.addWidget(self.dot, alignment=Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.text, stretch=1)
        self.refresh_theme()
        qconfig.themeChanged.connect(self.refresh_theme)
        QTimer.singleShot(0, self.title.refresh_elision)

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        self.refresh_theme()

    def set_collapsed(self, collapsed: bool) -> None:
        self.cancel_rename()
        self._collapsed = collapsed
        self.text.setVisible(not collapsed)
        self.setToolTip(self.record.display_title if collapsed else "")
        self.refresh_theme()

    def start_rename(self) -> None:
        if self._collapsed or self._renaming:
            return
        self._renaming = True
        self.title_edit.setText(self.record.display_title)
        self.title.setVisible(False)
        self.title_edit.setVisible(True)
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def cancel_rename(self) -> None:
        self._renaming = False
        self.title_edit.hide()
        self.title.setVisible(not self._collapsed)

    def _finish_rename(self, save: bool) -> None:
        if not self._renaming:
            return
        title = self.title_edit.text().strip()
        self.cancel_rename()
        if save and title and title != self.record.display_title:
            self.renameRequested.emit(self.record, title)

    def eventFilter(self, obj, e) -> bool:  # noqa: N802
        if obj is getattr(self, "title_edit", None):
            if e.type() == QEvent.Type.KeyPress:
                key_event = e
                if key_event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
                    self._finish_rename(True)
                    return True
                if key_event.key() == Qt.Key.Key_Escape:
                    self._finish_rename(False)
                    return True
            if e.type() == QEvent.Type.FocusOut:
                self._finish_rename(True)
        return super().eventFilter(obj, e)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton and self.rect().contains(e.position().toPoint()):
            self.sessionClicked.emit(self.record)
        super().mouseReleaseEvent(e)

    def _show_menu(self, position) -> None:
        self.sessionClicked.emit(self.record)
        menu = RoundMenu(parent=self)
        copy_action = Action(FluentIcon.COPY, tr(COPY_TITLE), self)
        copy_action.triggered.connect(self._copy_title)
        menu.addAction(copy_action)
        rename_action = Action(FluentIcon.EDIT, tr(RENAME), self)
        rename_action.setShortcut(QKeySequence("F2"))
        rename_action.triggered.connect(self.start_rename)
        menu.addAction(rename_action)
        if self.record.state == "failed":
            retry_action = Action(FluentIcon.SYNC, tr(RETRY), self)
            retry_action.triggered.connect(lambda: self.retryRequested.emit(self.record.prompt))
            menu.addAction(retry_action)
        menu.addSeparator()
        delete_action = Action(FluentIcon.DELETE, tr(DELETE), self)
        delete_action.setShortcut(QKeySequence(Qt.Key.Key_Delete))
        delete_action.triggered.connect(lambda: self.deleteRequested.emit(self.record))
        menu.addAction(delete_action)
        menu.exec(self.mapToGlobal(position))

    def _copy_title(self) -> None:
        QApplication.clipboard().setText(self.record.display_title)

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
        self.title_edit.setStyleSheet(
            f"LineEdit {{ color: {colors.sidebar_text}; background: {colors.sidebar_input}; "
            f"border: 1px solid {colors.primary}; border-radius: {RADIUS_CONTROL}px; }}"
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
    renameRequested = Signal(object, str)

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
        self.new_button = PrimaryPushButton(FluentIcon.ADD, tr(NEW_SESSION))
        self.new_button.setFont(font(T3, WEIGHT_SEMIBOLD))
        self.new_button.setFixedHeight(SPACE_5 + SPACE_4)
        self.new_button.clicked.connect(self.newSessionRequested)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.scroll_area.customContextMenuRequested.connect(self._show_blank_menu)
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
        self._delete_shortcut = QShortcut(QKeySequence(Qt.Key.Key_Delete), self)
        self._delete_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._delete_shortcut.activated.connect(self.delete_selected)
        self._rename_shortcut = QShortcut(QKeySequence("F2"), self)
        self._rename_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._rename_shortcut.activated.connect(self.rename_selected)
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

    @property
    def selected_record(self) -> SessionRecord | None:
        return self._selected.record if self._selected is not None else None

    def set_collapsed(self, collapsed: bool) -> None:
        self._collapsed = collapsed
        self.setFixedWidth(SIDEBAR_COLLAPSED_WIDTH if collapsed else SIDEBAR_WIDTH)
        self.search.setVisible(not collapsed)
        self.search_button.setVisible(collapsed)
        self.usage.setVisible(not collapsed)
        self.new_button.setText("" if collapsed else tr(NEW_SESSION))
        self.new_button.setToolTip(tr(NEW_SESSION) if collapsed else "")
        self._rebuild()

    def toggle_collapsed(self) -> None:
        self.set_collapsed(not self._collapsed)

    def focus_search(self) -> None:
        if self._collapsed:
            self.set_collapsed(False)
        self.search.setFocus()
        self.search.selectAll()

    def set_records(self, records: list[SessionRecord]) -> None:
        selected_id = self.selected_record.session_id if self.selected_record is not None else None
        self._records = records
        self._selected = None
        self._rebuild()
        if selected_id:
            self.select_session(selected_id)
        self._update_usage()

    def select_session(self, session_id: str) -> None:
        self._selected = None
        for card in self._cards:
            selected = card.record.session_id == session_id
            card.set_selected(selected)
            if selected:
                self._selected = card

    def rename_selected(self) -> None:
        if self._selected is not None:
            self._selected.start_rename()

    def delete_selected(self) -> None:
        if self._selected is not None:
            self.deleteRequested.emit(self._selected.record)

    def cancel_selected_rename(self) -> bool:
        if self._selected is not None and self._selected._renaming:
            self._selected.cancel_rename()
            return True
        return False

    def _rebuild(self) -> None:
        query = self.search.text().strip().casefold()
        records = [
            record
            for record in self._records
            if query in record.display_title.casefold() or query in record.prompt.casefold()
        ]
        container = QWidget()
        container.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        container.customContextMenuRequested.connect(self._show_blank_menu)
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
            card.renameRequested.connect(self.renameRequested)
            self._cards.append(card)
            layout.addWidget(card)
        if not records and not self._collapsed:
            empty = QLabel(tr(NO_MATCHING_HISTORY) if query else tr(EMPTY_HISTORY))
            empty.setFont(font(T4))
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                f"color: {palette().sidebar_muted}; background: transparent; border: none;"
            )
            layout.addWidget(empty)
        layout.addStretch()
        old = self.scroll_area.takeWidget()
        if old is not None:
            old.hide()
            old.deleteLater()
        self.scroll_area.setWidget(container)
        self.refresh_theme()

    def _select_card(self, record: SessionRecord) -> None:
        self.select_session(record.session_id)
        if self._selected is not None:
            self._selected.setFocus()
        self.sessionSelected.emit(record)

    def _show_blank_menu(self, position) -> None:
        menu = RoundMenu(parent=self)
        new_action = Action(FluentIcon.ADD, tr(NEW_SESSION), self)
        new_action.triggered.connect(self.newSessionRequested)
        menu.addAction(new_action)
        sender = self.sender()
        if isinstance(sender, QWidget):
            menu.exec(sender.mapToGlobal(position))

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
