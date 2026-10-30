"""File operation API contracts."""

from typing import Literal

from pydantic import BaseModel, Field


class FileSearchQuery(BaseModel):
    mode: Literal["list", "glob", "grep"] = "list"
    path: str = "/"
    pattern: str | None = None
    glob: str | None = None
    max_results: int | None = Field(default=None, ge=1)


class FileReadQuery(BaseModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=2000, ge=1, le=10_000)


class FilePathRequest(BaseModel):
    path: str


class WriteRequest(BaseModel):
    content: str


class EditRequest(BaseModel):
    old_string: str = Field(min_length=1)
    new_string: str
    replace_all: bool = False


class FileEntryResponse(BaseModel):
    path: str
    is_dir: bool
    size: int | None = None
    modified_at: str | None = None


class GrepMatchResponse(BaseModel):
    path: str
    line: int
    text: str


class SearchResponse(BaseModel):
    entries: list[FileEntryResponse]
    matches: list[GrepMatchResponse]
    truncated: bool
    truncation_reason: str | None = None


class ReadResponse(BaseModel):
    path: str
    content: str
    encoding: str
    total_lines: int
    start_line: int | None = None
    end_line: int | None = None
    next_offset: int | None = None
    no_lines_requested: bool = False
    created_at: str | None = None
    modified_at: str | None = None


class WriteResponse(BaseModel):
    path: str
    size: int
    occurrences: int | None = None
