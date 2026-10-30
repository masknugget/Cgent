"""FastAPI service assembly and owned resource lifecycle."""

import logging
import time
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from langchain_core.language_models import BaseChatModel

from cgent.agent.factory import AgentFactory
from cgent.agent.registry import InvocationRegistry
from cgent.agent.runner import AgentRunner
from cgent.api.errors import install_error_handlers
from cgent.api.router import create_api_router
from cgent.config import Settings
from cgent.execution.shell import ShellService
from cgent.execution.workspace import WorkspaceRegistry
from cgent.models.factory import ModelFactory
from cgent.telemetry.logging import log_event
from cgent.telemetry.request_id import normalize_request_id, reset_request_id, set_request_id

logger = logging.getLogger(__name__)


def create_app(settings: Settings, *, model: BaseChatModel | None = None) -> FastAPI:
    workspaces = WorkspaceRegistry(settings.workspaces)
    shell = ShellService(settings)
    model_factory = ModelFactory(settings) if model is None else None
    chat_model = model_factory.model if model_factory is not None else model
    if chat_model is None:
        raise ValueError("A chat model is required")
    factory = AgentFactory(settings, workspaces, shell, chat_model)
    runner = AgentRunner(settings, factory)
    invocations = InvocationRegistry(runner, settings.invocation_result_ttl_seconds)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        yield
        await invocations.close()
        await runner.close()
        await shell.close()
        if model_factory is not None:
            await model_factory.aclose()

    app = FastAPI(
        title="Cgent",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.workspaces = workspaces
    app.state.shell_service = shell
    app.state.agent_runner = runner
    app.state.invocations = invocations
    app.include_router(create_api_router(settings))
    install_error_handlers(app)

    @app.middleware("http")
    async def request_ids(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = normalize_request_id(request.headers.get("X-Request-ID"))
        request.state.request_id = request_id
        token = set_request_id(request_id)
        started = time.monotonic()
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            log_event(
                logger,
                logging.INFO,
                "HTTP request finished",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_seconds=round(time.monotonic() - started, 3),
            )
            return response
        finally:
            reset_request_id(token)

    return app
