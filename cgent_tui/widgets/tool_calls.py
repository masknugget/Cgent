"""Tool call summary table, shown after an invocation completes."""

from typing import Any

from textual.widgets import DataTable

from cgent_tui.models import ToolCallSummary
from cgent_tui.sanitize import sanitize_display_text

_MAX_ERROR_CHARS = 80
_STATUS_ICONS = {"pending": "◌", "completed": "✓", "failed": "✗"}


class ToolCalls(DataTable):
    """Table of tool calls: status icon, name, exit code and truncated error."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.cursor_type = "row"
        self.add_columns("状态", "工具", "退出码", "错误")

    def update_calls(self, calls: tuple[ToolCallSummary, ...]) -> None:
        self.clear()
        for call in calls:
            error = sanitize_display_text(call.error or "")
            if len(error) > _MAX_ERROR_CHARS:
                error = f"{error[:_MAX_ERROR_CHARS]}…"
            self.add_row(
                _STATUS_ICONS.get(call.status, "?"),
                sanitize_display_text(call.name),
                "-" if call.exit_code is None else str(call.exit_code),
                error,
            )
