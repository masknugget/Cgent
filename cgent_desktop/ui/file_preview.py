"""Modal, reusable text and image preview for workspace files."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import qtawesome
from PySide6.QtCore import (
    QDir,
    QEvent,
    QFileInfo,
    QFileSystemWatcher,
    QObject,
    QProcess,
    QRect,
    QRegularExpression,
    QRunnable,
    QSize,
    Qt,
    QThreadPool,
    QUrl,
    Signal,
)
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QDesktopServices,
    QImage,
    QImageReader,
    QKeySequence,
    QMovie,
    QPainter,
    QPaintEvent,
    QPixmap,
    QResizeEvent,
    QShortcut,
    QSyntaxHighlighter,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import FluentIcon, PushButton, TransparentToolButton, qconfig

from cgent_desktop.settings import DesktopSettings
from cgent_desktop.theme.tokens import (
    IMAGE_PREVIEW_BACKGROUND,
    PREVIEW_DEFAULT_HEIGHT,
    PREVIEW_DEFAULT_WIDTH,
    PREVIEW_LINE_NUMBER_WIDTH,
    PREVIEW_MAX_TEXT_BYTES,
    PREVIEW_MAX_TEXT_LINES,
    RADIUS_PREVIEW,
    SPACE_1,
    SPACE_2,
    SPACE_3,
    SPACE_4,
    T2,
    T3,
    T4,
    T5,
    WEIGHT_SEMIBOLD,
    font,
    palette,
)

TEXT_SUFFIXES = {
    "bat",
    "c",
    "cfg",
    "conf",
    "cpp",
    "cs",
    "css",
    "csv",
    "go",
    "h",
    "hpp",
    "htm",
    "html",
    "ini",
    "java",
    "js",
    "json",
    "jsonl",
    "jsx",
    "log",
    "markdown",
    "md",
    "php",
    "ps1",
    "py",
    "rb",
    "rs",
    "scss",
    "sh",
    "sql",
    "toml",
    "ts",
    "tsx",
    "txt",
    "vue",
    "xml",
    "yaml",
    "yml",
}
IMAGE_SUFFIXES = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "svg"}
LANGUAGE_NAMES = {
    "md": "Markdown",
    "markdown": "Markdown",
    "py": "Python",
    "json": "JSON",
    "jsonl": "JSON Lines",
    "toml": "TOML",
    "yaml": "YAML",
    "yml": "YAML",
    "txt": "Plain Text",
    "js": "JavaScript",
    "ts": "TypeScript",
    "html": "HTML",
    "css": "CSS",
    "sh": "Shell",
}


def format_file_size(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _decode_text(data: bytes) -> tuple[str, str]:
    try:
        return data.decode("utf-8-sig"), "UTF-8"
    except UnicodeDecodeError:
        try:
            return data.decode("gbk"), "GBK"
        except UnicodeDecodeError as exc:
            raise ValueError("无法解码") from exc


@dataclass(slots=True)
class TextLoadResult:
    request_id: int
    path: str
    text: str = ""
    encoding: str = ""
    total_lines: int = 0
    truncated: bool = False
    error: str = ""


class TextWorkerSignals(QObject):
    finished = Signal(object)


class TextLoadWorker(QRunnable):
    def __init__(self, path: str, request_id: int) -> None:
        super().__init__()
        self.path = path
        self.request_id = request_id
        self.signals = TextWorkerSignals()

    def run(self) -> None:
        result = TextLoadResult(self.request_id, self.path)
        try:
            file_size = Path(self.path).stat().st_size
            if file_size > PREVIEW_MAX_TEXT_BYTES:
                lines: list[bytes] = []
                with Path(self.path).open("rb") as stream:
                    for line in stream:
                        result.total_lines += 1
                        if result.total_lines <= PREVIEW_MAX_TEXT_LINES:
                            lines.append(line)
                data = b"".join(lines)
                result.truncated = result.total_lines > PREVIEW_MAX_TEXT_LINES
            else:
                data = Path(self.path).read_bytes()
            result.text, result.encoding = _decode_text(data)
            if file_size <= PREVIEW_MAX_TEXT_BYTES:
                result.total_lines = len(result.text.splitlines())
        except (OSError, ValueError) as exc:
            result.error = str(exc)
        self.signals.finished.emit(result)


class PreviewHighlighter(QSyntaxHighlighter):
    def __init__(self, document, language: str = "") -> None:
        super().__init__(document)
        self.language = language
        self._rules: list[tuple[QRegularExpression, QTextCharFormat]] = []
        self.refresh_theme()

    def set_language(self, language: str) -> None:
        self.language = language
        self.rehighlight()

    def refresh_theme(self) -> None:
        colors = palette()
        self._rules = []

        def add(pattern: str, color: str, *, bold: bool = False) -> None:
            text_format = QTextCharFormat()
            text_format.setForeground(QColor(color))
            if bold:
                text_format.setFontWeight(font(T4, WEIGHT_SEMIBOLD).weight())
            self._rules.append((QRegularExpression(pattern), text_format))

        add(r"\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'", colors.success)
        add(r"\b\d+(?:\.\d+)?\b", colors.primary)
        if self.language in {"py", "yaml", "yml", "toml", "sh", "ini", "cfg", "conf"}:
            add(r"#.*$", colors.muted)
        if self.language in {"js", "ts", "tsx", "jsx", "java", "c", "cpp", "cs", "go", "rs"}:
            add(r"//.*$", colors.muted)
        if self.language == "py":
            add(
                r"\b(?:and|as|assert|async|await|break|class|continue|def|del|elif|else|except|"
                r"False|finally|for|from|global|if|import|in|is|lambda|None|nonlocal|not|or|"
                r"pass|raise|return|True|try|while|with|yield)\b",
                colors.primary,
                bold=True,
            )
        if self.language in {"json", "jsonl"}:
            add(r"\"(?:[^\"\\]|\\.)*\"(?=\s*:)", colors.primary)
        if self.language in {"md", "markdown"}:
            add(r"^#{1,6}\s+.*$", colors.primary, bold=True)
            add(r"`[^`]+`", colors.success)
            add(r"^\s*```.*$", colors.muted)
        if self.language in {"toml", "yaml", "yml", "ini", "cfg", "conf"}:
            add(r"^[\w.-]+(?=\s*[:=])", colors.primary)
        self.rehighlight()

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        for expression, text_format in self._rules:
            matches = expression.globalMatch(text)
            while matches.hasNext():
                match = matches.next()
                self.setFormat(match.capturedStart(), match.capturedLength(), text_format)


class LineNumberArea(QWidget):
    def __init__(self, editor: CodePreviewEdit) -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(PREVIEW_LINE_NUMBER_WIDTH, 0)

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        colors = palette()
        painter = QPainter(self)
        painter.fillRect(event.rect(), QColor(colors.workspace))
        painter.setPen(QColor(colors.muted))
        painter.setFont(self._editor.font())
        block = self._editor.firstVisibleBlock()
        block_number = block.blockNumber()
        top = self._editor.blockBoundingGeometry(block).translated(
            self._editor.contentOffset()
        ).top()
        bottom = top + self._editor.blockBoundingRect(block).height()
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(
                    0,
                    int(top),
                    self.width() - SPACE_2,
                    int(self._editor.fontMetrics().height()),
                    Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                    str(block_number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + self._editor.blockBoundingRect(block).height()
            block_number += 1


class CodePreviewEdit(QPlainTextEdit):
    def __init__(self) -> None:
        super().__init__()
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setFont(font(T4, mono=True))
        self.line_number_area = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_number_width)
        self.updateRequest.connect(self._update_line_number_area)
        self._update_line_number_width()

    def _update_line_number_width(self, _count: int = 0) -> None:
        self.setViewportMargins(PREVIEW_LINE_NUMBER_WIDTH, 0, 0, 0)

    def _update_line_number_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self.line_number_area.scroll(0, dy)
        else:
            self.line_number_area.update(0, rect.y(), self.line_number_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_number_width()

    def set_preview_text(self, text: str) -> None:
        self.setPlainText(text)
        cursor = QTextCursor(self.document())
        cursor.select(QTextCursor.SelectionType.Document)
        block_format = QTextBlockFormat()
        block_format.setLineHeight(
            185.0, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value
        )
        cursor.mergeBlockFormat(block_format)

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        rect = self.contentsRect()
        self.line_number_area.setGeometry(
            QRect(rect.left(), rect.top(), PREVIEW_LINE_NUMBER_WIDTH, rect.height())
        )


class ImageScrollArea(QScrollArea):
    ctrlZoomRequested = Signal(int)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.ctrlZoomRequested.emit(event.angleDelta().y())
            event.accept()
            return
        super().wheelEvent(event)


class ImagePreview(QWidget):
    scaleChanged = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self._image = QImage()
        self._movie: QMovie | None = None
        self._original_size = QSize()
        self._scale = 1.0
        self._fit = True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll = ImageScrollArea()
        self.scroll.setWidget(self.label)
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.ctrlZoomRequested.connect(self._on_ctrl_zoom)
        layout.addWidget(self.scroll)
        self.refresh_theme()

    @property
    def original_size(self) -> QSize:
        return self._original_size

    def set_file(self, path: str) -> None:
        self.stop()
        self._image = QImage()
        self._original_size = QSize()
        self.label.clear()
        if Path(path).suffix.lower().removeprefix(".") == "gif":
            movie = QMovie(path)
            movie.jumpToFrame(0)
            self._original_size = movie.currentImage().size()
            if not self._original_size.isValid() or self._original_size.isEmpty():
                raise ValueError("无法加载图片")
            self._movie = movie
            self.label.setMovie(movie)
            movie.start()
        else:
            reader = QImageReader(path)
            reader.setAutoTransform(True)
            self._image = reader.read()
            if self._image.isNull():
                raise ValueError(reader.errorString() or "无法加载图片")
            self._original_size = self._image.size()
            self.label.setPixmap(QPixmap.fromImage(self._image))
        self.fit_to_window()

    def _render(self) -> None:
        if self._original_size.isEmpty():
            return
        target = self._original_size * self._scale
        target = QSize(max(1, target.width()), max(1, target.height()))
        if self._movie is not None:
            self._movie.setScaledSize(target)
            self.label.resize(target)
        else:
            pixmap = QPixmap.fromImage(self._image).scaled(
                target,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.label.setPixmap(pixmap)
            self.label.resize(pixmap.size())
        self.scaleChanged.emit(round(self._scale * 100))

    def fit_to_window(self) -> None:
        if self._original_size.isEmpty():
            return
        available = self.scroll.viewport().size()
        if available.width() <= 0 or available.height() <= 0:
            return
        self._fit = True
        self._scale = max(
            0.05,
            min(
                available.width() / self._original_size.width(),
                available.height() / self._original_size.height(),
            ),
        )
        self._render()

    def zoom_in(self) -> None:
        self._set_scale(self._scale * 1.25)

    def zoom_out(self) -> None:
        self._set_scale(self._scale / 1.25)

    def _set_scale(self, scale: float) -> None:
        self._fit = False
        self._scale = max(0.1, min(8.0, scale))
        self._render()

    def _on_ctrl_zoom(self, delta: int) -> None:
        if delta > 0:
            self.zoom_in()
        elif delta < 0:
            self.zoom_out()

    def stop(self) -> None:
        if self._movie is not None:
            self._movie.stop()
            self.label.setMovie(None)
            self._movie = None

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self._fit:
            self.fit_to_window()

    def refresh_theme(self) -> None:
        self.setStyleSheet(
            f"QWidget, QScrollArea {{ background: {IMAGE_PREVIEW_BACKGROUND}; border: none; }}"
        )


class FilePreviewDialog(QDialog):
    def __init__(self, store: DesktopSettings, parent: QWidget) -> None:
        super().__init__(parent)
        self._store = store
        self._path = ""
        self._workspace_root = ""
        self._file_size = 0
        self._encoding = ""
        self._request_id = 0
        self._workers: set[TextLoadWorker] = set()
        self.setWindowTitle("文件预览")
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setModal(True)
        self.setMinimumSize(560, 360)
        saved_size = store.file_preview_size()
        self.resize(saved_size or QSize(PREVIEW_DEFAULT_WIDTH, PREVIEW_DEFAULT_HEIGHT))

        self._overlay = QWidget(parent)
        self._overlay.setObjectName("filePreviewOverlay")
        self._overlay.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._overlay.setStyleSheet(
            "QWidget#filePreviewOverlay { background: rgba(23, 25, 35, 97); }"
        )
        self._overlay.hide()
        parent.installEventFilter(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)
        self.card = QWidget()
        self.card.setObjectName("filePreviewCard")
        outer.addWidget(self.card)
        layout = QVBoxLayout(self.card)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(SPACE_4, SPACE_3, SPACE_4, SPACE_3)
        header_layout.setSpacing(SPACE_3)
        self.type_icon = QLabel()
        self.type_icon.setFixedSize(24, 24)
        title_layout = QVBoxLayout()
        title_layout.setSpacing(SPACE_1)
        self.file_name = QLabel()
        self.file_name.setFont(font(T2, WEIGHT_SEMIBOLD))
        self.subtitle = QLabel()
        self.subtitle.setFont(font(T5))
        title_layout.addWidget(self.file_name)
        title_layout.addWidget(self.subtitle)
        self.copy_button = PushButton(FluentIcon.COPY, "复制路径")
        self.folder_button = PushButton(FluentIcon.FOLDER, "所在文件夹")
        self.close_button = TransparentToolButton(FluentIcon.CLOSE)
        self.close_button.setToolTip("关闭 · Esc")
        header_layout.addWidget(self.type_icon)
        header_layout.addLayout(title_layout, stretch=1)
        header_layout.addWidget(self.copy_button)
        header_layout.addWidget(self.folder_button)
        header_layout.addWidget(self.close_button)
        layout.addWidget(header)

        self.changed_button = PushButton(FluentIcon.SYNC, "文件已变更，点击刷新")
        self.changed_button.setVisible(False)
        layout.addWidget(self.changed_button)

        self.loading_page = QLabel("正在加载…")
        self.loading_page.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.text_editor = CodePreviewEdit()
        self.highlighter = PreviewHighlighter(self.text_editor.document())
        self.image_preview = ImagePreview()
        self.unsupported_page = QWidget()
        unsupported_layout = QVBoxLayout(self.unsupported_page)
        unsupported_layout.setContentsMargins(SPACE_4, SPACE_4, SPACE_4, SPACE_4)
        self.unsupported_title = QLabel("该文件类型暂不支持预览")
        self.unsupported_title.setFont(font(T3, WEIGHT_SEMIBOLD))
        self.unsupported_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unsupported_detail = QLabel()
        self.unsupported_detail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.unsupported_detail.setWordWrap(True)
        self.open_button = QPushButton("用系统默认程序打开")
        unsupported_layout.addStretch()
        unsupported_layout.addWidget(self.unsupported_title)
        unsupported_layout.addSpacing(SPACE_2)
        unsupported_layout.addWidget(self.unsupported_detail)
        unsupported_layout.addSpacing(SPACE_3)
        unsupported_layout.addWidget(self.open_button)
        unsupported_layout.addStretch()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.loading_page)
        self.stack.addWidget(self.text_editor)
        self.stack.addWidget(self.image_preview)
        self.stack.addWidget(self.unsupported_page)
        layout.addWidget(self.stack, stretch=1)

        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(SPACE_4, SPACE_2, SPACE_4, SPACE_2)
        footer_layout.setSpacing(SPACE_2)
        self.file_info = QLabel()
        self.file_info.setFont(font(T5))
        self.language = QLabel()
        self.language.setFont(font(T5))
        self.zoom_out = TransparentToolButton(FluentIcon.ZOOM_OUT)
        self.zoom_percent = QLabel("100%")
        self.zoom_percent.setFont(font(T5, mono=True))
        self.zoom_in = TransparentToolButton(FluentIcon.ZOOM_IN)
        self.fit_button = TransparentToolButton(FluentIcon.FIT_PAGE, "适应窗口")
        self.escape_hint = QLabel("Esc  关闭")
        self.escape_hint.setFont(font(T5))
        footer_layout.addWidget(self.file_info)
        footer_layout.addStretch()
        footer_layout.addWidget(self.language)
        footer_layout.addWidget(self.zoom_out)
        footer_layout.addWidget(self.zoom_percent)
        footer_layout.addWidget(self.zoom_in)
        footer_layout.addWidget(self.fit_button)
        footer_layout.addWidget(self.escape_hint)
        layout.addWidget(footer)

        self.watcher = QFileSystemWatcher(self)
        self.watcher.fileChanged.connect(self._on_file_changed)
        self.close_button.clicked.connect(self.close)
        self.copy_button.clicked.connect(self.copy_path)
        self.folder_button.clicked.connect(self.reveal_in_file_manager)
        self.changed_button.clicked.connect(self.refresh)
        self.open_button.clicked.connect(self.open_with_default_app)
        self.zoom_out.clicked.connect(self.image_preview.zoom_out)
        self.zoom_in.clicked.connect(self.image_preview.zoom_in)
        self.fit_button.clicked.connect(self.image_preview.fit_to_window)
        self.image_preview.scaleChanged.connect(
            lambda value: self.zoom_percent.setText(f"{value}%")
        )
        self.escape_shortcut = QShortcut(QKeySequence("Esc"), self)
        self.escape_shortcut.activated.connect(self.close)
        qconfig.themeChanged.connect(self.refresh_theme)
        self.refresh_theme()

    @property
    def path(self) -> str:
        return self._path

    def show_file(self, path: str, workspace_root: str = "") -> None:
        self._request_id += 1
        self._path = QDir.cleanPath(path)
        self._workspace_root = workspace_root
        self._encoding = ""
        self.image_preview.stop()
        self.changed_button.hide()
        self._watch_file()
        self._update_header()
        self.stack.setCurrentWidget(self.loading_page)
        self.language.clear()
        self.file_info.setText(format_file_size(self._file_size))
        self._set_zoom_controls_visible(False)
        self._show_and_center()

        suffix = Path(self._path).suffix.lower().removeprefix(".")
        if suffix in IMAGE_SUFFIXES:
            try:
                self.image_preview.set_file(self._path)
            except ValueError as exc:
                self._show_unsupported("无法加载图片", str(exc))
            else:
                self.stack.setCurrentWidget(self.image_preview)
                size = self.image_preview.original_size
                self.file_info.setText(
                    f"{size.width()} × {size.height()} · {format_file_size(self._file_size)}"
                )
                self._set_zoom_controls_visible(True)
            return
        if not suffix or suffix in TEXT_SUFFIXES:
            worker = TextLoadWorker(self._path, self._request_id)
            self._workers.add(worker)
            worker.signals.finished.connect(
                lambda result, current=worker: self._on_text_loaded(result, current)
            )
            QThreadPool.globalInstance().start(worker)
            return
        self._show_unsupported("该文件类型暂不支持预览", self._relative_path())

    def _show_and_center(self) -> None:
        if not self.isVisible():
            parent = self.parentWidget()
            self._overlay.setGeometry(parent.rect())
            self._overlay.show()
            self._overlay.raise_()
            center = parent.mapToGlobal(parent.rect().center())
            self.move(center - self.rect().center())
            self.show()
        self.raise_()
        self.activateWindow()

    def _update_header(self, encoding: str = "") -> None:
        info = QFileInfo(self._path)
        self._file_size = info.size()
        suffix = info.suffix().lower()
        self.file_name.setText(info.fileName())
        if encoding:
            self._encoding = encoding
        format_name = self._encoding or suffix.upper() or "文本"
        self.subtitle.setText(
            f"{self._relative_path()} · {format_file_size(self._file_size)} · {format_name}"
        )
        icon_name = "fa5s.file-image" if suffix in IMAGE_SUFFIXES else "fa5s.file-code"
        if not suffix or suffix not in TEXT_SUFFIXES | IMAGE_SUFFIXES:
            icon_name = "fa5s.file-alt"
        self.type_icon.setPixmap(
            qtawesome.icon(icon_name, color=palette().secondary).pixmap(24, 24)
        )

    def _relative_path(self) -> str:
        if self._workspace_root:
            try:
                return Path(self._path).relative_to(self._workspace_root).as_posix()
            except ValueError:
                pass
        return self._path

    def _on_text_loaded(self, result: TextLoadResult, worker: TextLoadWorker) -> None:
        self._workers.discard(worker)
        if result.request_id != self._request_id or result.path != self._path:
            return
        if result.error:
            self._show_unsupported("无法解码" if result.error == "无法解码" else "无法读取文件", result.error)
            return
        self._update_header(result.encoding)
        self.text_editor.set_preview_text(result.text)
        self.highlighter.set_language(Path(self._path).suffix.lower().removeprefix("."))
        self.stack.setCurrentWidget(self.text_editor)
        details = f"共 {result.total_lines} 行 · 只读预览"
        if result.truncated:
            details += " · 文件过大，仅显示前 2000 行"
        self.file_info.setText(details)
        suffix = Path(self._path).suffix.lower().removeprefix(".")
        self.language.setText(LANGUAGE_NAMES.get(suffix, suffix.upper() or "Plain Text"))

    def _show_unsupported(self, title: str, detail: str) -> None:
        self.unsupported_title.setText(title)
        self.unsupported_detail.setText(detail)
        self.stack.setCurrentWidget(self.unsupported_page)
        self.file_info.setText(format_file_size(self._file_size))

    def _set_zoom_controls_visible(self, visible: bool) -> None:
        for widget in (self.zoom_out, self.zoom_percent, self.zoom_in, self.fit_button):
            widget.setVisible(visible)

    def _watch_file(self) -> None:
        watched = self.watcher.files()
        if watched:
            self.watcher.removePaths(watched)
        if QFileInfo(self._path).isFile():
            self.watcher.addPath(self._path)

    def _on_file_changed(self, path: str) -> None:
        if QDir.cleanPath(path) == self._path:
            self.changed_button.show()
            if QFileInfo(self._path).isFile() and self._path not in self.watcher.files():
                self.watcher.addPath(self._path)

    def refresh(self) -> None:
        if self._path:
            self.show_file(self._path, self._workspace_root)

    def copy_path(self) -> None:
        QApplication.clipboard().setText(QDir.toNativeSeparators(self._path))

    def reveal_in_file_manager(self) -> None:
        if not self._path:
            return
        if sys.platform == "win32":
            selected = QProcess.startDetached(
                "explorer.exe", [f"/select,{QDir.toNativeSeparators(self._path)}"]
            )
            if selected:
                return
        elif sys.platform == "darwin" and QProcess.startDetached("open", ["-R", self._path]):
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(QFileInfo(self._path).absolutePath()))

    def open_with_default_app(self) -> None:
        if self._path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._path))

    def eventFilter(self, watched, event: QEvent) -> bool:  # noqa: N802
        if watched is self.parentWidget() and event.type() == QEvent.Type.Resize:
            self._overlay.setGeometry(self.parentWidget().rect())
        return super().eventFilter(watched, event)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        self._store.set_file_preview_size(self.size())
        self._request_id += 1
        self.image_preview.stop()
        self._overlay.hide()
        super().closeEvent(event)

    def refresh_theme(self) -> None:
        colors = palette()
        self.card.setStyleSheet(
            f"QWidget#filePreviewCard {{ background: {colors.card}; "
            f"border: 1px solid {colors.border}; border-radius: {RADIUS_PREVIEW}px; }}"
        )
        self.file_name.setStyleSheet(f"color: {colors.text};")
        self.subtitle.setStyleSheet(f"color: {colors.secondary};")
        self.loading_page.setStyleSheet(f"color: {colors.secondary};")
        self.changed_button.setStyleSheet(
            f"PushButton {{ color: {colors.primary}; background: {colors.primary_soft}; "
            f"border: none; padding: {SPACE_1}px; }}"
        )
        self.text_editor.setStyleSheet(
            f"QPlainTextEdit {{ background: {colors.card}; color: {colors.text}; "
            f"border: none; selection-background-color: {colors.selection_background}; "
            f"selection-color: {colors.selection_foreground}; }}"
        )
        self.highlighter.refresh_theme()
        self.text_editor.line_number_area.update()
        self.image_preview.refresh_theme()
        self.unsupported_title.setStyleSheet(f"color: {colors.text};")
        self.unsupported_detail.setStyleSheet(f"color: {colors.secondary};")
        self.file_info.setStyleSheet(f"color: {colors.secondary};")
        self.language.setStyleSheet(f"color: {colors.secondary};")
        self.escape_hint.setStyleSheet(f"color: {colors.muted};")
        self.zoom_percent.setStyleSheet(f"color: {colors.secondary};")
        if self._path:
            self._update_header()
