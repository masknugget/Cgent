"""Bounded UTF-8 file operations shared by REST and Agent tools."""

import fnmatch
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from cgent.errors import (
    FileConflictError,
    InvalidEditError,
    InvalidPathError,
    InvalidTextError,
    PayloadTooLargeError,
)
from cgent.errors import (
    FileNotFoundError as HarnessFileNotFoundError,
)
from cgent.execution.models import (
    FileEntry,
    GrepMatch,
    ReadResult,
    SearchResult,
    WriteResult,
)
from cgent.execution.workspace import Workspace


def _timestamp(value: float) -> str:
    return datetime.fromtimestamp(value, UTC).isoformat()


def _created_at(stat: os.stat_result) -> str | None:
    value = getattr(stat, "st_birthtime", None)
    return _timestamp(value) if isinstance(value, int | float) else None


class FileService:
    def __init__(self, workspace: Workspace, *, max_file_bytes: int, max_results: int) -> None:
        self.workspace = workspace
        self.max_file_bytes = max_file_bytes
        self.max_results = max_results

    def _entry(self, path: Path) -> FileEntry:
        stat = path.stat()
        return FileEntry(
            path=self.workspace.virtual_path(path),
            is_dir=path.is_dir(),
            size=None if path.is_dir() else stat.st_size,
            modified_at=_timestamp(stat.st_mtime),
        )

    def _read_text(self, path: Path) -> str:
        if not path.exists() or not path.is_file():
            raise HarnessFileNotFoundError()
        with path.open("rb") as stream:
            content = stream.read(self.max_file_bytes + 1)
        if len(content) > self.max_file_bytes:
            raise PayloadTooLargeError("The file exceeds the configured size limit")
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise InvalidTextError() from exc

    def _atomic_write(self, path: Path, content: str) -> int:
        encoded = content.encode("utf-8")
        if len(encoded) > self.max_file_bytes:
            raise PayloadTooLargeError("The content exceeds the configured file size limit")
        if not path.parent.is_dir():
            raise HarnessFileNotFoundError()
        if path.exists() and path.is_dir():
            raise FileConflictError("is_directory", "The target path is a directory")
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
                temporary = stream.name
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None:
                Path(temporary).unlink(missing_ok=True)
        return len(encoded)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        path = self.workspace.resolve(file_path)
        text = self._read_text(path)
        stat = path.stat()
        if limit <= 0:
            return ReadResult(
                path=self.workspace.virtual_path(path),
                content="",
                no_lines_requested=True,
                created_at=_created_at(stat),
                modified_at=_timestamp(stat.st_mtime),
            )
        lines = text.splitlines(keepends=True)
        start = max(0, offset)
        end = min(len(lines), start + limit)
        selected = lines[start:end]
        has_window = bool(selected)
        return ReadResult(
            path=self.workspace.virtual_path(path),
            content="".join(selected),
            total_lines=len(lines),
            start_line=start + 1 if has_window else None,
            end_line=end if has_window else None,
            next_offset=end if has_window and end < len(lines) else None,
            created_at=_created_at(stat),
            modified_at=_timestamp(stat.st_mtime),
        )

    def write(self, file_path: str, content: str) -> WriteResult:
        path = self.workspace.resolve(file_path)
        size = self._atomic_write(path, content)
        return WriteResult(self.workspace.virtual_path(path), size)

    def edit(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> WriteResult:
        if not old_string:
            raise InvalidEditError("old_string must not be empty")
        if old_string == new_string:
            raise InvalidEditError("new_string must be different from old_string")
        path = self.workspace.resolve(file_path)
        text = self._read_text(path)
        occurrences = text.count(old_string)
        if occurrences == 0:
            raise FileConflictError("edit_conflict", "old_string was not found")
        if occurrences > 1 and not replace_all:
            raise FileConflictError("edit_conflict", "old_string is not unique")
        updated = (
            text.replace(old_string, new_string)
            if replace_all
            else text.replace(old_string, new_string, 1)
        )
        size = self._atomic_write(path, updated)
        return WriteResult(
            self.workspace.virtual_path(path), size, occurrences if replace_all else 1
        )

    def delete(self, file_path: str) -> None:
        path = self.workspace.resolve(file_path)
        if not path.exists():
            raise HarnessFileNotFoundError()
        if path.is_dir():
            raise FileConflictError("is_directory", "Recursive directory deletion is not supported")
        path.unlink()

    def list(self, path: str = "/", max_results: int | None = None) -> SearchResult:
        root = self.workspace.resolve(path)
        if not root.exists():
            raise HarnessFileNotFoundError()
        if not root.is_dir():
            raise FileConflictError("not_directory", "The requested path is not a directory")
        limit = self._limit(max_results)
        entries: list[FileEntry] = []
        truncated = False
        for candidate in sorted(root.iterdir(), key=lambda item: item.name.lower()):
            if len(entries) >= limit:
                truncated = True
                break
            resolved = candidate.resolve(strict=False)
            if resolved.is_relative_to(self.workspace.root):
                entries.append(self._entry(resolved))
        return SearchResult(
            entries=entries,
            truncated=truncated,
            truncation_reason="max_results" if truncated else None,
        )

    def glob(
        self, pattern: str, path: str | None = None, max_results: int | None = None
    ) -> SearchResult:
        if not pattern or "\x00" in pattern:
            raise InvalidPathError("A non-empty glob pattern is required")
        root = self.workspace.resolve(path)
        if not root.is_dir():
            raise FileConflictError("not_directory", "The search root is not a directory")
        normalized = pattern.lstrip("/")
        if "/" not in normalized:
            normalized = f"**/{normalized}"
        limit = self._limit(max_results)
        entries: list[FileEntry] = []
        truncated = False
        try:
            candidates = root.glob(normalized)
            for candidate in candidates:
                resolved = candidate.resolve(strict=False)
                if not resolved.is_relative_to(self.workspace.root) or not resolved.is_file():
                    continue
                if len(entries) >= limit:
                    truncated = True
                    break
                entries.append(self._entry(resolved))
        except (ValueError, OSError) as exc:
            raise InvalidPathError("The glob pattern is invalid") from exc
        entries.sort(key=lambda item: item.path)
        return SearchResult(
            entries=entries,
            truncated=truncated,
            truncation_reason="max_results" if truncated else None,
        )

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        max_count: int | None = None,
    ) -> SearchResult:
        if not pattern:
            raise InvalidPathError("A non-empty literal search pattern is required")
        root = self.workspace.resolve(path)
        if not root.exists():
            raise HarnessFileNotFoundError()
        candidates = [root] if root.is_file() else root.rglob("*")
        limit = self._limit(max_count)
        matches: list[GrepMatch] = []
        truncated = False
        for candidate in candidates:
            if len(matches) >= limit:
                truncated = True
                break
            try:
                resolved = candidate.resolve(strict=False)
                if (
                    not resolved.is_relative_to(self.workspace.root)
                    or not resolved.is_file()
                    or resolved.stat().st_size > self.max_file_bytes
                    or not self._matches_glob(resolved, glob)
                ):
                    continue
                text = self._read_text(resolved)
            except (OSError, InvalidTextError):
                continue
            for line_number, line in enumerate(text.splitlines(), 1):
                if pattern in line:
                    matches.append(
                        GrepMatch(self.workspace.virtual_path(resolved), line_number, line)
                    )
                    if len(matches) >= limit:
                        truncated = True
                        break
        return SearchResult(
            matches=matches,
            truncated=truncated,
            truncation_reason="max_results" if truncated else None,
        )

    def _matches_glob(self, path: Path, pattern: str | None) -> bool:
        if pattern is None:
            return True
        normalized = pattern.lstrip("/")
        if "/" not in normalized:
            return fnmatch.fnmatch(path.name, normalized)
        relative = path.relative_to(self.workspace.root).as_posix()
        return fnmatch.fnmatch(relative, normalized)

    def _limit(self, requested: int | None) -> int:
        return self.max_results if requested is None else min(max(1, requested), self.max_results)
