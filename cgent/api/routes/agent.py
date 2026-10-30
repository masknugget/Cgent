"""Synchronous Agent invocation route."""

from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Header

from cgent.agent.runner import AgentRunner
from cgent.api.body_limit import BoundedBodyRoute
from cgent.api.dependencies import runner
from cgent.api.schemas.agent import InvocationRequest, InvocationResponse
from cgent.api.schemas.common import ToolCallSummary, UsageResponse

router = APIRouter(route_class=BoundedBodyRoute)


@router.post("/agent/invocations", response_model=InvocationResponse)
async def invoke(
    body: InvocationRequest,
    x_workspace_id: Annotated[str, Header(min_length=1)],
    service: Annotated[AgentRunner, Depends(runner)],
) -> InvocationResponse:
    result = await service.invoke(x_workspace_id, body.input, body.timeout_seconds)
    usage = UsageResponse(**asdict(result.usage)) if result.usage is not None else None
    return InvocationResponse(
        invocation_id=result.invocation_id,
        status=result.status,
        output=result.output,
        tool_calls=[ToolCallSummary(**asdict(call)) for call in result.tool_calls],
        usage=usage,
    )
