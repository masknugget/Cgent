from pathlib import Path

import pytest

from cgent.errors import (
    FileConflictError,
    InvalidTextError,
    PayloadTooLargeError,
)
from cgent.errors import (
    FileNotFoundError as HarnessFileNotFoundError,
)
from cgent.execution.files import FileService
from cgent.execution.workspace import Workspace


def file_service(tmp_path: Path, *, max_file_bytes: int = 1024) -> FileService:
    return FileService(Workspace("test", tmp_path), max_file_bytes=max_file_bytes, max_results=100)


def test_file_crud_pagination_and_search(tmp_path: Path) -> None:
    service = file_service(tmp_path)
    service.write("/note.txt", "first\nsecond\nfirst\n")
    (tmp_path / "src").mkdir()
    service.write("/src/main.py", "print('first')\n")

    page = service.read("/note.txt", offset=1, limit=1)
    assert page.content == "second\n"
    assert (page.total_lines, page.start_line, page.end_line, page.next_offset) == (3, 2, 2, 2)

    with pytest.raises(FileConflictError, match="not unique"):
        service.edit("/note.txt", "first", "updated")
    changed = service.edit("/note.txt", "first", "updated", replace_all=True)
    assert changed.occurrences == 2
    assert service.read("/note.txt").content == "updated\nsecond\nupdated\n"

    assert [entry.path for entry in service.list("/").entries] == ["/note.txt", "/src"]
    assert [entry.path for entry in service.glob("*.py").entries] == ["/src/main.py"]
    matches = service.grep("updated", glob="*.txt").matches
    assert [(match.path, match.line) for match in matches] == [("/note.txt", 1), ("/note.txt", 3)]

    service.delete("/note.txt")
    with pytest.raises(HarnessFileNotFoundError):
        service.read("/note.txt")


def test_failed_edit_preserves_original_content(tmp_path: Path) -> None:
    service = file_service(tmp_path)
    service.write("/note.txt", "original")

    with pytest.raises(FileConflictError, match="not found"):
        service.edit("/note.txt", "missing", "replacement")

    assert service.read("/note.txt").content == "original"


def test_file_size_and_utf8_limits(tmp_path: Path) -> None:
    service = file_service(tmp_path, max_file_bytes=4)

    with pytest.raises(PayloadTooLargeError):
        service.write("/large.txt", "12345")
    assert not (tmp_path / "large.txt").exists()

    (tmp_path / "large.txt").write_bytes(b"12345")
    with pytest.raises(PayloadTooLargeError):
        service.read("/large.txt")

    (tmp_path / "binary.dat").write_bytes(b"\xff")
    with pytest.raises(InvalidTextError):
        service.read("/binary.dat")


def test_directory_is_not_recursively_deleted(tmp_path: Path) -> None:
    service = file_service(tmp_path)
    (tmp_path / "directory").mkdir()

    with pytest.raises(FileConflictError, match="not supported"):
        service.delete("/directory")

    assert (tmp_path / "directory").is_dir()
