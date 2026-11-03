"""Prompt input: a multiline TextArea where Enter submits.

Enter submits the current text; Shift+Enter (where the terminal can report
it) or Ctrl+J inserts a newline. When the input is empty, Up/Down recall
prompt history instead of moving the cursor.
"""

from typing import Any

from textual import events
from textual.message import Message
from textual.widgets import TextArea

from cgent_tui.sanitize import sanitize_display_text


class PromptInput(TextArea):
    """Multiline prompt editor with submit/history messages."""

    class PromptSubmitted(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    class HistoryPrev(Message):
        """Request the previous prompt from history."""

    class HistoryNext(Message):
        """Request the next prompt from history."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(placeholder="输入任务描述，Enter 提交", **kwargs)
        self.show_line_numbers = False

    async def _on_key(self, event: events.Key) -> None:
        if self.read_only:
            await super()._on_key(event)
            return
        if event.key == "enter":
            event.stop()
            event.prevent_default()
            text = sanitize_display_text(self.text).strip()
            self.clear()
            if text:
                self.post_message(self.PromptSubmitted(text))
            return
        if event.key in ("ctrl+j", "shift+enter"):
            event.stop()
            event.prevent_default()
            self.insert("\n")
            return
        if event.key == "up" and not self.text:
            event.stop()
            event.prevent_default()
            self.post_message(self.HistoryPrev())
            return
        if event.key == "down" and not self.text:
            event.stop()
            event.prevent_default()
            self.post_message(self.HistoryNext())
            return
        await super()._on_key(event)

    def set_prompt(self, text: str) -> None:
        """Replace the current content (used by history recall)."""
        self.clear()
        if text:
            self.insert(sanitize_display_text(text))
