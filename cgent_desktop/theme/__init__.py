"""Single application theme entry point."""

import qdarktheme
from PySide6.QtWidgets import QApplication
from qfluentwidgets import Theme, setTheme

from cgent_desktop.theme.tokens import T2, font


def setup_app_theme(app: QApplication) -> None:
    qdarktheme.setup_theme("auto")
    setTheme(Theme.AUTO)
    app.setFont(font(T2))
