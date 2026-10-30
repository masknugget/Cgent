"""Execution-domain result types, independent of HTTP and DeepAgents."""

from dataclasses import dataclass, field
from typing import Literal


@dataclass(frozen=True, slots=True)
class FileEntry:
    path: str
    is_dir: bool
    size: int | None = None
    modified_at: str | None = None


@dataclass(frozen=True, slots=True)
class ReadResult:
    path: str
    content: str
    encoding: str = "utf-8"
    total_lines: int = 0
    start_line: int | None = None
    end_line: int | None = None
    next_offset: int | None = None
    no_lines_requested: bool = False
    created_at: str | None = None
    modified_at: str | None = None


@dataclass(frozen=True, slots=True)
class WriteResult:
    path: str
    size: int
    occurrences: int | None = None


@dataclass(frozen=True, slots=True)
class GrepMatch:
    path: str
    line: int
    text: str


@dataclass(frozen=True, slots=True)
class SearchResult:
    entries: list[FileEntry] = field(default_factory=list)
    matches: list[GrepMatch] = field(default_factory=list)
    truncated: bool = False
    truncation_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ShellExecution:
    execution_id: str
    status: Literal["completed", "failed", "timed_out", "stopped"]
    exit_code: int | None
    output: str
    truncated: bool
    duration_seconds: float
