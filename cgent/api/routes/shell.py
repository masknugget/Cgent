"""Controlled direct process execution route."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends

from cgent.api.body_limit import BoundedBodyRoute
from cgent.api.dependencies import ExecutionContext, execution_context, shell
from cgent.api.schemas.shell import ExecutionRequest, ExecutionResponse
from cgent.execution.shell import ShellService

router = APIRouter(route_class=BoundedBodyRoute)


@router.post("/shell/executions", response_model=ExecutionResponse)
async def execute(
    body: ExecutionRequest,
    context: Annotated[ExecutionContext, Depends(execution_context)],
    service: Annotated[ShellService, Depends(shell)],
) -> ExecutionResponse:
    result = await service.execute(context.workspace, body.command, body.timeout_seconds)
    return ExecutionResponse(**asdict(result))
