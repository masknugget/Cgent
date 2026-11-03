"""Chat view: user prompts, agent status lines and the final output."""

from rich.text import Text
from textual.containers import VerticalScroll
from textual.widgets import Markdown, Static

from cgent_tui.sanitize import sanitize_display_text

_STYLE_BY_KIND = {
    "info": "bold cyan",
    "success": "bold green",
    "error": "bold red",
    "warning": "bold yellow",
}


class ChatView(VerticalScroll):
    """Scrollable conversation area."""

    def add_user(self, text: str) -> None:
        self.mount(Static(Text(f"● You  {sanitize_display_text(text)}"), markup=False))

    def add_status(self, text: str, kind: str = "info") -> None:
        style = _STYLE_BY_KIND.get(kind, "bold")
        self.mount(Static(Text(f"{text}", style=style), markup=False))

    def add_output(self, text: str) -> None:
        """Render the final agent output as Markdown (display only)."""
        self.mount(Markdown(sanitize_display_text(text)))

    def clear(self) -> None:
        for child in list(self.children):
            child.remove()
