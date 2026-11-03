"""Status bar: server address, workspace, state, elapsed time and usage."""

from typing import Any

from textual.widgets import Static

from cgent_tui.models import Usage


class StatusBar(Static):
    """One-line status strip above the prompt input."""

    def __init__(self, base_url: str, workspace_id: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._base_url = base_url
        self._workspace_id = workspace_id
        self._state = "就绪"
        self._elapsed: float | None = None
        self._usage: Usage | None = None
        self._refresh_text()

    def set_state(self, text: str) -> None:
        self._state = text
        self._refresh_text()

    def set_elapsed(self, seconds: float | None) -> None:
        self._elapsed = seconds
        self._refresh_text()

    def set_usage(self, usage: Usage | None) -> None:
        self._usage = usage
        self._refresh_text()

    def _refresh_text(self) -> None:
        parts = [
            f"Cgent TUI ─ {self._base_url} ─ workspace: {self._workspace_id}",
            self._state,
        ]
        if self._elapsed is not None:
            parts.append(f"已耗时 {self._elapsed:.0f}s")
        if self._usage is not None:
            parts.append(
                f"tokens: in {self._usage.input_tokens} / out {self._usage.output_tokens} / total {self._usage.total_tokens}"
            )
        self.update(" ─ ".join(parts))
