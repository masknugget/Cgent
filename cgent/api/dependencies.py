"""Authentication and per-request execution dependencies."""

from dataclasses import dataclass
from typing import cast

from fastapi import Header, Request

from cgent.agent.registry import InvocationRegistry
from cgent.agent.runner import AgentRunner
from cgent.config import Settings
from cgent.execution.files import FileService
from cgent.execution.shell import ShellService
from cgent.execution.workspace import Workspace, WorkspaceRegistry


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    workspace: Workspace
    files: FileService


def execution_context(
    request: Request,
    x_workspace_id: str = Header(min_length=1),
) -> ExecutionContext:
    settings = cast(Settings, request.app.state.settings)
    registry = cast(WorkspaceRegistry, request.app.state.workspaces)
    workspace = registry.get(x_workspace_id)
    return ExecutionContext(
        workspace=workspace,
        files=FileService(
            workspace,
            max_file_bytes=settings.max_file_bytes,
            max_results=settings.max_search_results,
        ),
    )


def runner(request: Request) -> AgentRunner:
    return cast(AgentRunner, request.app.state.agent_runner)


def workspace_registry(request: Request) -> WorkspaceRegistry:
    return cast(WorkspaceRegistry, request.app.state.workspaces)


def invocation_registry(request: Request) -> InvocationRegistry:
    return cast(InvocationRegistry, request.app.state.invocations)


def shell(request: Request) -> ShellService:
    return cast(ShellService, request.app.state.shell_service)
