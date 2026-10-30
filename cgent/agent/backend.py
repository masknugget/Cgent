"""DeepAgents backend backed by Cgent's guarded execution services."""

from deepagents.backends.protocol import (
    DeleteResult,
    EditResult,
    ExecuteResponse,
    FileData,
    FileInfo,
    GlobResult,
    GrepMatch,
    GrepResult,
    LsResult,
    ReadResult,
    SandboxBackendProtocol,
    WriteResult,
)

from cgent.errors import HarnessError
from cgent.execution.files import FileService
from cgent.execution.models import FileEntry
from cgent.execution.models import GrepMatch as DomainGrepMatch
from cgent.execution.shell import ShellService
from cgent.execution.workspace import Workspace


def _file_info(entry: FileEntry) -> FileInfo:
    info = FileInfo(path=entry.path, is_dir=entry.is_dir)
    if entry.size is not None:
        info["size"] = entry.size
    if entry.modified_at is not None:
        info["modified_at"] = entry.modified_at
    return info


def _grep_match(match: DomainGrepMatch) -> GrepMatch:
    return GrepMatch(path=match.path, line=match.line, text=match.text)


class CgentBackend(SandboxBackendProtocol):
    def __init__(self, workspace: Workspace, files: FileService, shell: ShellService) -> None:
        self.workspace = workspace
        self.files = files
        self.shell = shell

    @property
    def id(self) -> str:
        return f"cgent-{self.workspace.id}"

    def ls(self, path: str) -> LsResult:
        try:
            result = self.files.list(path)
            return LsResult(entries=[_file_info(entry) for entry in result.entries])
        except HarnessError as exc:
            return LsResult(error=exc.message)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        try:
            result = self.files.read(file_path, offset, limit)
            has_window = result.start_line is not None
            file_data = FileData(content=result.content, encoding=result.encoding)
            if result.created_at is not None:
                file_data["created_at"] = result.created_at
            if result.modified_at is not None:
                file_data["modified_at"] = result.modified_at
            return ReadResult(
                file_data=file_data,
                total_lines=result.total_lines if has_window else None,
                start_line=result.start_line,
                end_line=result.end_line,
                next_offset=result.next_offset,
                no_lines_requested=result.no_lines_requested,
            )
        except HarnessError as exc:
            return ReadResult(error=exc.message)

    def grep(
        self,
        pattern: str,
        path: str | None = None,
        glob: str | None = None,
        *,
        max_count: int | None = None,
    ) -> GrepResult:
        try:
            result = self.files.grep(pattern, path, glob, max_count)
            return GrepResult(
                matches=[_grep_match(match) for match in result.matches],
                truncated=result.truncated,
            )
        except HarnessError as exc:
            return GrepResult(error=exc.message)

    def glob(self, pattern: str, path: str | None = None) -> GlobResult:
        try:
            result = self.files.glob(pattern, path)
            return GlobResult(
                matches=[_file_info(entry) for entry in result.entries],
                truncated=result.truncated,
                truncation_reason="budget" if result.truncated else None,
            )
        except HarnessError as exc:
            return GlobResult(error=exc.message)

    def write(self, file_path: str, content: str) -> WriteResult:
        try:
            result = self.files.write(file_path, content)
            return WriteResult(path=result.path)
        except HarnessError as exc:
            return WriteResult(error=exc.message)

    def edit(
        self, file_path: str, old_string: str, new_string: str, replace_all: bool = False
    ) -> EditResult:
        try:
            result = self.files.edit(file_path, old_string, new_string, replace_all)
            return EditResult(path=result.path, occurrences=result.occurrences)
        except HarnessError as exc:
            return EditResult(error=exc.message)

    def delete(self, file_path: str) -> DeleteResult:
        try:
            path = self.workspace.resolve(file_path)
            self.files.delete(file_path)
            return DeleteResult(path=self.workspace.virtual_path(path))
        except HarnessError as exc:
            return DeleteResult(error=exc.message)

    def execute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        raise NotImplementedError("Cgent Shell execution is asynchronous")

    async def aexecute(self, command: str, *, timeout: int | None = None) -> ExecuteResponse:
        try:
            result = await self.shell.execute(self.workspace, command, timeout)
            return ExecuteResponse(
                output=result.output,
                exit_code=result.exit_code,
                truncated=result.truncated,
            )
        except HarnessError as exc:
            return ExecuteResponse(output=f"Error: {exc.message}", exit_code=126)
