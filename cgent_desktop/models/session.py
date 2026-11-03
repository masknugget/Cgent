"""Desktop session history data transfer objects."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SessionRecord:
    prompt: str
    state: str
    started_at: str
    detail: str
    input_tokens: int = 0
    output_tokens: int = 0
    title: str = ""
    session_id: str = ""

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def display_title(self) -> str:
        return self.title.strip() or self.prompt
