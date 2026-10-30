from pathlib import Path

import pytest

from cgent.errors import InvalidPathError, PathOutsideWorkspaceError
from cgent.execution.workspace import Workspace


def test_workspace_resolves_virtual_paths(tmp_path: Path) -> None:
    workspace = Workspace("test", tmp_path)

    assert workspace.resolve() == tmp_path.resolve()
    assert workspace.resolve("/src/main.py") == tmp_path.resolve() / "src" / "main.py"
    assert workspace.virtual_path(tmp_path / "src" / "main.py") == "/src/main.py"
    assert workspace.virtual_path(tmp_path) == "/"


@pytest.mark.parametrize("value", ["../secret.txt", "/../secret.txt", "a/../../secret.txt"])
def test_workspace_rejects_parent_traversal(tmp_path: Path, value: str) -> None:
    with pytest.raises(PathOutsideWorkspaceError):
        Workspace("test", tmp_path).resolve(value)


@pytest.mark.parametrize("value", ["C:/secret.txt", "a\\b.txt", "bad:path"])
def test_workspace_rejects_non_virtual_paths(tmp_path: Path, value: str) -> None:
    with pytest.raises(InvalidPathError):
        Workspace("test", tmp_path).resolve(value)


def test_workspace_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("secret", encoding="utf-8")
    try:
        (tmp_path / "link").symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Directory symlinks are unavailable: {exc}")

    with pytest.raises(PathOutsideWorkspaceError):
        Workspace("test", tmp_path).resolve("/link/secret.txt")
