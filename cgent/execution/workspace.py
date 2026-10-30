"""Fixed workspace roots and virtual-path containment."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath

from cgent.errors import (
    InvalidPathError,
    PathOutsideWorkspaceError,
    WorkspaceNotFoundError,
)


@dataclass(frozen=True, slots=True)
class Workspace:
    id: str
    root: Path

    def __post_init__(self) -> None:
        object.__setattr__(self, "root", self.root.resolve())

    def resolve(self, value: str | None = None) -> Path:
        path = "/" if value is None or value == "" else value
        if "\x00" in path or "\\" in path or ":" in path or path.startswith("//"):
            raise InvalidPathError()
        pure = PurePosixPath(path)
        if ".." in pure.parts or PureWindowsPath(path).drive:
            raise PathOutsideWorkspaceError()
        relative = path.lstrip("/")
        candidate = self.root.joinpath(relative).resolve(strict=False)
        if not candidate.is_relative_to(self.root):
            raise PathOutsideWorkspaceError()
        return candidate

    def virtual_path(self, path: Path) -> str:
        resolved = path.resolve(strict=False)
        if not resolved.is_relative_to(self.root):
            raise PathOutsideWorkspaceError()
        relative = resolved.relative_to(self.root).as_posix()
        return "/" if relative == "." else f"/{relative}"


class WorkspaceRegistry:
    def __init__(self, workspaces: Mapping[str, Path]) -> None:
        self._workspaces = {
            workspace_id: Workspace(workspace_id, root) for workspace_id, root in workspaces.items()
        }

    @property
    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._workspaces))

    def get(self, workspace_id: str) -> Workspace:
        try:
            return self._workspaces[workspace_id]
        except KeyError as exc:
            raise WorkspaceNotFoundError(workspace_id) from exc
