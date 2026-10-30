"""Load configured host skill directories into DeepAgents' skills middleware.

Configured directories contain one subdirectory per skill, each with a
``SKILL.md`` file. Files are mounted into a read-only virtual backend so the
Agent can discover and read skills without exposing host paths or allowing
skill content to be modified through workspace tools.
"""

import re
from pathlib import Path
from typing import Any

from deepagents.backends.protocol import (
    DeleteResult,
    EditResult,
    FileData,
    FileUploadResponse,
    WriteResult,
)
from deepagents.backends.state import StateBackend
from deepagents.backends.utils import create_file_data
from deepagents.middleware.skills import SkillsMiddleware, SkillSource

from cgent.config import Settings

_READ_ONLY = "Configured skills are read-only"


class _ConfiguredSkillsBackend(StateBackend):
    """Read-only in-memory backend for host-configured skill files."""

    def __init__(self, files: dict[str, FileData]) -> None:
        self._files = dict(files)

    def _read_files(self) -> dict[str, Any]:
        return dict(self._files)

    def write(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error=_READ_ONLY, path=file_path)

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,
    ) -> EditResult:
        return EditResult(error=_READ_ONLY, path=file_path)

    def delete(self, file_path: str) -> DeleteResult:
        return DeleteResult(error=_READ_ONLY, path=file_path)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [FileUploadResponse(path=path, error="permission_denied") for path, _ in files]


def load_skills_middleware(settings: Settings) -> SkillsMiddleware[None, Any] | None:
    """Load all configured host directories into one read-only skills middleware."""
    if not settings.skills_dirs:
        return None
    files: dict[str, FileData] = {}
    sources: list[SkillSource] = []
    labels: set[str] = set()
    for index, root in enumerate(settings.skills_dirs):
        virtual_root = f"/.cgent-skills/{index}"
        files.update(_load_source_files(root, virtual_root, settings))
        label = _source_label(root, index, labels)
        sources.append((f"{virtual_root}/", label))
    return SkillsMiddleware(
        backend=_ConfiguredSkillsBackend(files),
        sources=sources,
    )


def _load_source_files(
    root: Path,
    virtual_root: str,
    settings: Settings,
) -> dict[str, FileData]:
    loaded: dict[str, FileData] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size > settings.max_file_bytes:
            raise ValueError(
                f"Skill file exceeds the configured size limit ({settings.max_file_bytes} bytes): {path}"
            )
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # SKILL.md must be UTF-8 text. Binary helper assets are not mounted in P0.
            continue
        relative = path.relative_to(root).as_posix()
        if not relative or ".." in Path(relative).parts:
            raise ValueError(f"Invalid skill file path: {path}")
        virtual_path = f"{virtual_root}/{relative}"
        loaded[virtual_path] = create_file_data(content)
        if len(loaded) > settings.max_search_results:
            raise ValueError("Configured skills contain more files than HARNESS_MAX_SEARCH_RESULTS")
    return loaded


def _source_label(root: Path, index: int, labels: set[str]) -> str:
    stem = root.name or f"skills-{index + 1}"
    parts = [part for part in re.split(r"[-_]+", stem) if part]
    if parts and parts[-1].lower() == "skills":
        parts = parts[:-1]
    base = " ".join(part.capitalize() for part in parts) or f"Configured {index + 1}"
    label = base
    suffix = 2
    while label in labels:
        label = f"{base} {suffix}"
        suffix += 1
    labels.add(label)
    return label
