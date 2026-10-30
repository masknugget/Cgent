"""Bounded text-file REST routes."""

import asyncio
from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status

from cgent.api.body_limit import BoundedBodyRoute
from cgent.api.dependencies import ExecutionContext, execution_context
from cgent.api.schemas.files import (
    EditRequest,
    FileEntryResponse,
    FileReadQuery,
    FileSearchQuery,
    GrepMatchResponse,
    ReadResponse,
    SearchResponse,
    WriteRequest,
    WriteResponse,
)
from cgent.errors import InvalidPathError
from cgent.execution.models import SearchResult

router = APIRouter(route_class=BoundedBodyRoute)
Context = Annotated[ExecutionContext, Depends(execution_context)]


def _search_response(result: SearchResult) -> SearchResponse:
    return SearchResponse(
        entries=[FileEntryResponse(**asdict(entry)) for entry in result.entries],
        matches=[GrepMatchResponse(**asdict(match)) for match in result.matches],
        truncated=result.truncated,
        truncation_reason=result.truncation_reason,
    )


@router.get("/files", response_model=SearchResponse)
async def search_files(
    context: Context,
    query: Annotated[FileSearchQuery, Query()],
) -> SearchResponse:
    if query.mode == "list":
        result = await asyncio.to_thread(context.files.list, query.path, query.max_results)
    elif query.mode == "glob":
        if query.pattern is None:
            raise InvalidPathError("pattern is required for glob mode")
        result = await asyncio.to_thread(
            context.files.glob, query.pattern, query.path, query.max_results
        )
    else:
        if query.pattern is None:
            raise InvalidPathError("pattern is required for grep mode")
        result = await asyncio.to_thread(
            context.files.grep,
            query.pattern,
            query.path,
            query.glob,
            query.max_results,
        )
    return _search_response(result)


@router.get("/files/{path:path}", response_model=ReadResponse)
async def read_file(
    path: str,
    context: Context,
    query: Annotated[FileReadQuery, Query()],
) -> ReadResponse:
    result = await asyncio.to_thread(context.files.read, path, query.offset, query.limit)
    return ReadResponse(**asdict(result))


@router.put("/files/{path:path}", response_model=WriteResponse)
async def write_file(path: str, body: WriteRequest, context: Context) -> WriteResponse:
    result = await asyncio.to_thread(context.files.write, path, body.content)
    return WriteResponse(**asdict(result))


@router.patch("/files/{path:path}", response_model=WriteResponse)
async def edit_file(path: str, body: EditRequest, context: Context) -> WriteResponse:
    result = await asyncio.to_thread(
        context.files.edit,
        path,
        body.old_string,
        body.new_string,
        body.replace_all,
    )
    return WriteResponse(**asdict(result))


@router.delete("/files/{path:path}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(path: str, context: Context) -> Response:
    await asyncio.to_thread(context.files.delete, path)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
