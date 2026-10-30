import os
import shlex
import subprocess
import sys
from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Self

import httpx
import pytest
from fastapi import FastAPI
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

from cgent.config import Settings


class FakeToolCallingModel(GenericFakeChatModel):
    def bind_tools(
        self,
        tools: Sequence[object],
        *,
        tool_choice: str | None = None,
        **kwargs: object,
    ) -> Self:
        return self


def python_command(code: str) -> str:
    argv = [Path(sys.executable).name, "-c", code]
    return subprocess.list2cmdline(argv) if os.name == "nt" else shlex.join(argv)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        workspaces={"test": tmp_path},
        model="fake-model",
        model_api_key="test-model-secret",
        model_timeout_seconds=2,
        agent_timeout_seconds=2,
        shell_allowlist=(str(Path(sys.executable).resolve()),),
        shell_timeout_seconds=2,
        shell_max_timeout_seconds=3,
        shell_kill_grace_seconds=0.05,
        shell_queue_timeout_seconds=0.05,
        max_concurrent_shells=2,
    )


@pytest.fixture
def workspace_headers() -> dict[str, str]:
    return {"X-Workspace-ID": "test"}


@asynccontextmanager
async def app_client(app: FastAPI) -> AsyncGenerator[httpx.AsyncClient]:
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
