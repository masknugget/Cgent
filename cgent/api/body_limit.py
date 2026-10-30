"""Streaming request-body limits for API routes.

The bounded-body route pattern is adapted from Open SWE (MIT).
"""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request, Response
from fastapi.routing import APIRoute

from cgent.errors import PayloadTooLargeError


class BoundedBodyRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        original = super().get_route_handler()

        async def bounded(request: Request) -> Response:
            limit = request.app.state.settings.max_body_bytes
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > limit:
                    raise PayloadTooLargeError()

            async def receive() -> dict[str, object]:
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            return await original(Request(request.scope, receive))

        return bounded
