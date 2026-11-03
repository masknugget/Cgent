"""Single application theme entry point."""

import qdarktheme
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, qconfig, setTheme

from cgent_desktop.theme.tokens import T2, font, palette

_BASE_STYLE_PROPERTY = "_cgentBaseStyleSheet"
_SELECTION_CONNECTED_PROPERTY = "_cgentSelectionThemeConnected"


def apply_text_selection_theme(app: QApplication) -> None:
    colors = palette()
    application_palette = app.palette()
    for group in (
        QPalette.ColorGroup.Active,
        QPalette.ColorGroup.Inactive,
        QPalette.ColorGroup.Disabled,
    ):
        application_palette.setColor(
            group, QPalette.ColorRole.Highlight, QColor(colors.selection_background)
        )
        application_palette.setColor(
            group, QPalette.ColorRole.HighlightedText, QColor(colors.selection_foreground)
        )
    app.setPalette(application_palette)
    base_style = app.property(_BASE_STYLE_PROPERTY) or ""
    app.setStyleSheet(
        f"{base_style}\n"
        f"QLineEdit, QTextEdit, QPlainTextEdit, QLabel {{ "
        f"selection-background-color: {colors.selection_background}; "
        f"selection-color: {colors.selection_foreground}; }}"
    )


def setup_app_theme(app: QApplication) -> None:
    qdarktheme.setup_theme("auto")
    setTheme(Theme.AUTO)
    app.setFont(font(T2))
    app.setProperty(_BASE_STYLE_PROPERTY, app.styleSheet())
    apply_text_selection_theme(app)
    if not app.property(_SELECTION_CONNECTED_PROPERTY):
        qconfig.themeChanged.connect(lambda: apply_text_selection_theme(app))
        app.setProperty(_SELECTION_CONNECTED_PROPERTY, True)
