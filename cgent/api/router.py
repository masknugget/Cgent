"""API composition and capability discovery."""

from fastapi import APIRouter
from pydantic import BaseModel

from cgent.api.body_limit import BoundedBodyRoute
from cgent.api.routes import agent, files, health, shell
from cgent.api.schemas.agent import InvocationRequest
from cgent.api.schemas.common import ToolDescriptor, ToolsResponse
from cgent.api.schemas.files import (
    EditRequest,
    FilePathRequest,
    FileReadQuery,
    FileSearchQuery,
    WriteRequest,
)
from cgent.api.schemas.shell import ExecutionRequest
from cgent.config import Settings


def _tool(
    name: str, description: str, method: str, path: str, schema: type[BaseModel]
) -> ToolDescriptor:
    return ToolDescriptor(
        name=name,
        description=description,
        method=method,
        path=path,
        input_schema=schema.model_json_schema(),
    )


def create_api_router(settings: Settings) -> APIRouter:
    router = APIRouter(route_class=BoundedBodyRoute)
    router.include_router(health.router)
    v1 = APIRouter(prefix="/v1", route_class=BoundedBodyRoute)

    @v1.get("/tools", response_model=ToolsResponse)
    async def tools() -> ToolsResponse:
        descriptors = [
            _tool(
                "agent_invoke",
                "Run one synchronous coding Agent invocation.",
                "POST",
                "/v1/agent/invocations",
                InvocationRequest,
            )
        ]
        if settings.enable_direct_tools:
            descriptors.extend(
                [
                    _tool(
                        "file_search",
                        "List, glob or literally grep workspace files.",
                        "GET",
                        "/v1/files",
                        FileSearchQuery,
                    ),
                    _tool(
                        "file_read",
                        "Read a bounded UTF-8 text window.",
                        "GET",
                        "/v1/files/{path}",
                        FileReadQuery,
                    ),
                    _tool(
                        "file_write",
                        "Create or atomically replace a UTF-8 text file.",
                        "PUT",
                        "/v1/files/{path}",
                        WriteRequest,
                    ),
                    _tool(
                        "file_edit",
                        "Apply an exact string edit.",
                        "PATCH",
                        "/v1/files/{path}",
                        EditRequest,
                    ),
                    _tool(
                        "file_delete",
                        "Delete one file without recursive directory deletion.",
                        "DELETE",
                        "/v1/files/{path}",
                        FilePathRequest,
                    ),
                    _tool(
                        "shell_execute",
                        "Execute one allowlisted program directly.",
                        "POST",
                        "/v1/shell/executions",
                        ExecutionRequest,
                    ),
                ]
            )
        return ToolsResponse(tools=descriptors)

    v1.include_router(agent.router)
    if settings.enable_direct_tools:
        v1.include_router(files.router)
        v1.include_router(shell.router)
    router.include_router(v1)
    return router
