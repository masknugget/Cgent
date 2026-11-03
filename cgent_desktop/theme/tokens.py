"""Design tokens for the Cgent desktop interface."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtGui import QFont
from qfluentwidgets import isDarkTheme

UI_FONT_FAMILIES = ("Inter", "PingFang SC", "Microsoft YaHei", "sans-serif")
MONO_FONT_FAMILIES = (
    "JetBrains Mono",
    "Cascadia Code",
    "Consolas",
    "Noto Sans Mono CJK SC",
    "monospace",
)

T1 = 14
T2 = 13
T3 = 13
T4 = 12
T5 = 12
T6 = 11

WEIGHT_REGULAR = QFont.Weight.Normal
WEIGHT_MEDIUM = QFont.Weight.Medium
WEIGHT_SEMIBOLD = QFont.Weight.DemiBold

SPACE_1 = 4
SPACE_2 = 8
SPACE_3 = 12
SPACE_4 = 16
SPACE_5 = 20
SPACE_6 = 24
SPACE_7 = 28
SPACE_8 = 32

RADIUS_SMALL = 6
RADIUS_CONTROL = 8
RADIUS_CARD = 10
RADIUS_BUBBLE = 12
RADIUS_COMPOSER = 14
RADIUS_PREVIEW = 14
RADIUS_MESSAGE_ACTION = 7
RADIUS_PILL = 9
MESSAGE_ACTION_HEIGHT = 28
COPY_FEEDBACK_MS = 1500
COPY_SUCCESS_BACKGROUND = "#E7F7EC"
COPY_SUCCESS_FOREGROUND = "#15803D"

BORDER_WIDTH = 1
FOCUS_WIDTH = 2
SCROLLBAR_WIDTH = 8
STATUS_DOT_SIZE = 8
SESSION_DOT_SIZE = 7
LOGO_SIZE = 22
AVATAR_SIZE = 32
TOOL_ICON_SIZE = 24
WINDOW_CONTROL_WIDTH = 40
TITLE_BAR_HEIGHT = 40
TOOLBAR_HEIGHT = 52
STATUS_BAR_HEIGHT = 30
SIDEBAR_WIDTH = 268
SIDEBAR_COLLAPSED_WIDTH = 56
WORKSPACE_PANEL_WIDTH = 300
WORKSPACE_PANEL_MIN_WIDTH = 220
WORKSPACE_PANEL_MAX_WIDTH = 480
WORKSPACE_REFRESH_MS = 250
TOOL_HEADER_HEIGHT = 38
INPUT_MIN_HEIGHT = 64
INPUT_MAX_HEIGHT = 120
COMPOSER_MIN_HEIGHT = 132
MESSAGE_MAX_WIDTH = 820
MESSAGE_MIN_WIDTH = 320
LOG_MIN_HEIGHT = 88
LOG_MAX_HEIGHT = 260
PREVIEW_DEFAULT_WIDTH = 780
PREVIEW_DEFAULT_HEIGHT = 520
PREVIEW_LINE_NUMBER_WIDTH = 52
PREVIEW_MAX_TEXT_BYTES = 2 * 1024 * 1024
PREVIEW_MAX_TEXT_LINES = 2000
IMAGE_PREVIEW_BACKGROUND = "#1E2026"
DEFAULT_WIDTH = 1280
DEFAULT_HEIGHT = 820
MIN_WIDTH = 960
MIN_HEIGHT = 640
MAX_PROMPT_CHARS = 8192
ELAPSED_TIMER_MS = 100
MAX_PROGRESS_HEIGHT = 28


@dataclass(frozen=True, slots=True)
class Palette:
    primary: str
    primary_hover: str
    primary_soft: str
    on_primary: str
    selection_background: str
    selection_foreground: str
    sidebar: str
    sidebar_input: str
    sidebar_hover: str
    sidebar_selected: str
    sidebar_border: str
    sidebar_text: str
    sidebar_muted: str
    workspace: str
    card: str
    border: str
    input_border: str
    text: str
    secondary: str
    muted: str
    success: str
    success_bg: str
    failure: str
    failure_bg: str
    terminal: str
    terminal_text: str
    terminal_path: str
    terminal_comment: str
    terminal_error: str
    shadow: str
    primary_shadow: str


LIGHT = Palette(
    primary="#4F46E5",
    primary_hover="#4338CA",
    primary_soft="#EEF0FF",
    on_primary="#FFFFFF",
    selection_background="#C7CEF7",
    selection_foreground="#1F232E",
    sidebar="#1F2128",
    sidebar_input="#2A2D36",
    sidebar_hover="#2A2D36",
    sidebar_selected="#2E313A",
    sidebar_border="#3A3D47",
    sidebar_text="#E7E9EF",
    sidebar_muted="#8B90A0",
    workspace="#F5F6F8",
    card="#FFFFFF",
    border="#E8EAEF",
    input_border="#E2E4EA",
    text="#2B2E38",
    secondary="#6B7280",
    muted="#9AA0AE",
    success="#15803D",
    success_bg="#E7F7EC",
    failure="#B91C1C",
    failure_bg="#FDECEC",
    terminal="#17181C",
    terminal_text="#B8BEC9",
    terminal_path="#5C6370",
    terminal_comment="#5C6370",
    terminal_error="#F87171",
    shadow="rgba(23, 25, 35, 18)",
    primary_shadow="rgba(79, 70, 229, 32)",
)

DARK = Palette(
    primary="#6366F1",
    primary_hover="#818CF8",
    primary_soft="#302E5B",
    on_primary="#FFFFFF",
    selection_background="#4A4E78",
    selection_foreground="#F2F4F8",
    sidebar="#1F2128",
    sidebar_input="#2A2D36",
    sidebar_hover="#2A2D36",
    sidebar_selected="#2E313A",
    sidebar_border="#3A3D47",
    sidebar_text="#E7E9EF",
    sidebar_muted="#8B90A0",
    workspace="#17181C",
    card="#23252C",
    border="#353841",
    input_border="#42454F",
    text="#E7E9EF",
    secondary="#A7ACB8",
    muted="#737986",
    success="#4ADE80",
    success_bg="#173525",
    failure="#F87171",
    failure_bg="#3B2025",
    terminal="#111216",
    terminal_text="#B8BEC9",
    terminal_path="#7C8494",
    terminal_comment="#5C6370",
    terminal_error="#F87171",
    shadow="rgba(0, 0, 0, 45)",
    primary_shadow="rgba(99, 102, 241, 45)",
)


def palette() -> Palette:
    return DARK if isDarkTheme() else LIGHT


def font(size: int, weight: QFont.Weight = WEIGHT_REGULAR, *, mono: bool = False) -> QFont:
    result = QFont()
    result.setFamilies(MONO_FONT_FAMILIES if mono else UI_FONT_FAMILIES)
    result.setPixelSize(size)
    result.setWeight(weight)
    if mono:
        result.setStyleHint(QFont.StyleHint.TypeWriter)
    return result


def state_colors(state: str) -> tuple[str, str]:
    colors = palette()
    if state in {"failed", "failure", "error", "cancelled"}:
        return colors.failure, colors.failure_bg
    if state in {"succeeded", "completed", "healthy", "正常"}:
        return colors.success, colors.success_bg
    return colors.primary, colors.primary_soft
