"""Small theme-aware widgets shared by desktop pages."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPaintEvent
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
from qfluentwidgets import SimpleCardWidget, qconfig

from cgent_desktop.theme.tokens import (
    AVATAR_SIZE,
    RADIUS_CONTROL,
    RADIUS_PILL,
    SPACE_1,
    SPACE_2,
    STATUS_DOT_SIZE,
    T2,
    T5,
    T6,
    WEIGHT_SEMIBOLD,
    font,
    palette,
    state_colors,
)


class ThemeAwareWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        qconfig.themeChanged.connect(self.refresh_theme)

    def refresh_theme(self) -> None:
        self.update()


class ThemeAwareCard(SimpleCardWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        qconfig.themeChanged.connect(self.refresh_theme)

    def _normalBackgroundColor(self) -> QColor:  # noqa: N802
        return QColor(palette().card)

    def refresh_theme(self) -> None:
        self._updateBackgroundColor()
        self.update()


class StatusBadge(QLabel):
    def __init__(self, state: str = "succeeded", text: str | None = None) -> None:
        super().__init__(text or state)
        self._state = state
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(font(T6, WEIGHT_SEMIBOLD, mono=True))
        self.setFixedHeight(T6 + SPACE_2)
        self.refresh_theme()

    def set_state(self, state: str, text: str | None = None) -> None:
        self._state = state
        self.setText(text or state)
        self.refresh_theme()

    def refresh_theme(self) -> None:
        foreground, background = state_colors(self._state)
        self.setStyleSheet(
            f"QLabel {{ color: {foreground}; background: {background}; "
            f"border-radius: {RADIUS_PILL}px; padding: 0 {SPACE_2}px; }}"
        )


class StateDot(QWidget):
    def __init__(self, state: str = "succeeded", size: int = STATUS_DOT_SIZE) -> None:
        super().__init__()
        self._state = state
        self.setFixedSize(size, size)
        self.setAccessibleName(f"状态：{state}")

    def set_state(self, state: str) -> None:
        self._state = state
        self.setAccessibleName(f"状态：{state}")
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        foreground, _ = state_colors(self._state)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(foreground))
        painter.drawEllipse(self.rect())


class Avatar(QLabel):
    def __init__(self, text: str = "C", size: int = AVATAR_SIZE) -> None:
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFont(font(T2, WEIGHT_SEMIBOLD))
        self.setFixedSize(size, size)
        self.refresh_theme()
        qconfig.themeChanged.connect(self.refresh_theme)

    def refresh_theme(self) -> None:
        colors = palette()
        self.setStyleSheet(
            f"QLabel {{ color: {colors.primary}; background: {colors.primary_soft}; "
            f"border: none; border-radius: {RADIUS_CONTROL}px; }}"
        )


class KeyCap(QLabel):
    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setFont(font(T6, mono=True))
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.refresh_theme()
        qconfig.themeChanged.connect(self.refresh_theme)

    def refresh_theme(self) -> None:
        colors = palette()
        self.setStyleSheet(
            f"QLabel {{ color: {colors.secondary}; background: {colors.workspace}; "
            f"border: 1px solid {colors.border}; border-radius: {SPACE_1}px; "
            f"padding: 0 {SPACE_1}px; }}"
        )


class EmptyState(ThemeAwareWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.title = QLabel("开始一个新任务")
        self.title.setFont(font(T2, WEIGHT_SEMIBOLD))
        self.detail = QLabel("描述你的目标，Cgent 会在这里展示执行过程与结果。")
        self.detail.setFont(font(T5))
        self.detail.setWordWrap(True)
        layout.addStretch()
        layout.addWidget(self.title, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(SPACE_2)
        layout.addWidget(self.detail, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addStretch()
        self.refresh_theme()

    def refresh_theme(self) -> None:
        colors = palette()
        self.title.setStyleSheet(f"color: {colors.secondary}; background: transparent;")
        self.detail.setStyleSheet(f"color: {colors.muted}; background: transparent;")
