"""Unauthenticated process health."""

from fastapi import APIRouter

from cgent.api.body_limit import BoundedBodyRoute
from cgent.api.schemas.common import HealthResponse

router = APIRouter(route_class=BoundedBodyRoute)


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse()
