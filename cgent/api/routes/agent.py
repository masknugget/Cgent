"""Asynchronous Agent invocation routes."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response

from cgent.agent.registry import InvocationRecord, InvocationRegistry
from cgent.api.body_limit import BoundedBodyRoute
from cgent.api.dependencies import invocation_registry, workspace_registry
from cgent.api.schemas.agent import (
    InvocationAcceptedResponse,
    InvocationRequest,
    InvocationStatusResponse,
)
from cgent.api.schemas.common import ErrorBody, ToolCallSummary, UsageResponse
from cgent.errors import InvocationNotCancellableError, InvocationNotFoundError
from cgent.execution.workspace import WorkspaceRegistry

router = APIRouter(route_class=BoundedBodyRoute)


def _to_response(record: InvocationRecord) -> InvocationStatusResponse:
    result = record.result
    return InvocationStatusResponse(
        invocation_id=record.invocation_id,
        status=record.status,
        output=result.output if result is not None else None,
        tool_calls=(
            [ToolCallSummary(**asdict(call)) for call in result.tool_calls]
            if result is not None
            else []
        ),
        usage=UsageResponse(**asdict(result.usage))
        if result is not None and result.usage
        else None,
        error=(
            ErrorBody(code=record.error_code, message=record.error_message)
            if record.error_code is not None and record.error_message is not None
            else None
        ),
    )


@router.post(
    "/agent/invocations",
    status_code=202,
    response_model=InvocationAcceptedResponse,
)
async def submit_invocation(
    body: InvocationRequest,
    x_workspace_id: Annotated[str, Header(min_length=1)],
    workspaces: Annotated[WorkspaceRegistry, Depends(workspace_registry)],
    invocations: Annotated[InvocationRegistry, Depends(invocation_registry)],
) -> InvocationAcceptedResponse:
    # Validate the workspace before accepting so a bad ID fails fast.
    workspaces.get(x_workspace_id)
    record = invocations.submit(x_workspace_id, body.input, body.timeout_seconds)
    return InvocationAcceptedResponse(invocation_id=record.invocation_id)


@router.get("/agent/invocations/{invocation_id}", response_model=InvocationStatusResponse)
async def get_invocation(
    invocation_id: str,
    invocations: Annotated[InvocationRegistry, Depends(invocation_registry)],
) -> InvocationStatusResponse:
    record = invocations.get(invocation_id)
    if record is None:
        raise InvocationNotFoundError()
    return _to_response(record)


@router.delete("/agent/invocations/{invocation_id}", status_code=204)
async def cancel_invocation(
    invocation_id: str,
    invocations: Annotated[InvocationRegistry, Depends(invocation_registry)],
) -> Response:
    record = invocations.get(invocation_id)
    if record is None:
        raise InvocationNotFoundError()
    if not invocations.cancel(invocation_id):
        raise InvocationNotCancellableError()
    return Response(status_code=204)
