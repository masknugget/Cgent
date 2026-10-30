"""DeepAgents graph assembly with fixed local tools and no persistence."""

from collections.abc import Sequence
from importlib.resources import files
from typing import Any, Protocol, cast

from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    create_deep_agent,
    register_harness_profile,
)
from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig

from cgent.agent.backend import CgentBackend
from cgent.agent.middleware import ModelCallTimeoutMiddleware
from cgent.agent.skills import load_skills_middleware
from cgent.config import Settings
from cgent.execution.files import FileService
from cgent.execution.shell import ShellService
from cgent.execution.workspace import WorkspaceRegistry


class AgentGraph(Protocol):
    async def ainvoke(
        self, input: dict[str, list[HumanMessage]], config: RunnableConfig
    ) -> dict[str, object]: ...


class AgentFactory:
    def __init__(
        self,
        settings: Settings,
        workspaces: WorkspaceRegistry,
        shell: ShellService,
        model: BaseChatModel,
    ) -> None:
        self._settings = settings
        self._workspaces = workspaces
        self._shell = shell
        self._model = model
        self._skills = load_skills_middleware(settings)
        self._prompt = (
            files("cgent").joinpath("resources/prompts/system.md").read_text(encoding="utf-8")
        )
        provider = model._get_ls_params().get("ls_provider") or "cgent-openai"
        register_harness_profile(
            provider,
            HarnessProfile(
                general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
                tool_description_overrides={
                    "delete": (
                        "Delete one UTF-8 text or binary file inside the workspace. "
                        "Directories are never deleted recursively."
                    ),
                    "execute": (
                        "Execute one allowlisted program directly in the workspace. "
                        "This is not a command shell: pipes, redirection and shell built-ins "
                        "are unavailable. Commands have bounded time and output."
                    ),
                },
            ),
        )

    def create(self, workspace_id: str) -> AgentGraph:
        workspace = self._workspaces.get(workspace_id)
        file_service = FileService(
            workspace,
            max_file_bytes=self._settings.max_file_bytes,
            max_results=self._settings.max_search_results,
        )
        backend = CgentBackend(workspace, file_service, self._shell)
        middleware = [
            item
            for item in (
                self._skills,
                ModelCallTimeoutMiddleware(self._settings.model_timeout_seconds),
            )
            if item is not None
        ]
        return create_deep_agent(
            model=self._model,
            system_prompt=self._prompt,
            backend=backend,
            middleware=cast(Sequence[AgentMiddleware[Any, None]], tuple(middleware)),
            checkpointer=None,
        )
