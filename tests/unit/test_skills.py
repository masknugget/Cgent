from dataclasses import replace
from pathlib import Path

import pytest
from conftest import FakeToolCallingModel
from deepagents.backends.utils import create_file_data
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatResult
from pydantic import Field

from cgent.agent.factory import AgentFactory
from cgent.agent.skills import _ConfiguredSkillsBackend, load_skills_middleware
from cgent.config import Settings
from cgent.execution.shell import ShellService
from cgent.execution.workspace import WorkspaceRegistry


def write_skill(root: Path, name: str, description: str = "A test skill") -> Path:
    skill = root / name
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\n"
        f"name: {name}\n"
        f"description: {description}\n"
        "---\n\n"
        "# Demo Skill\n\nUse this skill for tests.\n",
        encoding="utf-8",
    )
    return skill


class RecordingFakeModel(FakeToolCallingModel):
    system_contents: list[str] = Field(default_factory=list)

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: object,
    ) -> ChatResult:
        self.system_contents.extend(
            str(message.content) for message in messages if isinstance(message, SystemMessage)
        )
        return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)


def test_load_skills_middleware_mounts_host_directory(settings: Settings, tmp_path: Path) -> None:
    skills_root = tmp_path / "my-skills"
    write_skill(skills_root, "demo-skill", "Describe demo files")
    settings = replace(settings, skills_dirs=(skills_root,))

    middleware = load_skills_middleware(settings)

    assert middleware is not None
    assert middleware.sources == ["/.cgent-skills/0/"]
    assert middleware.source_labels == ["My"]
    responses = middleware._backend.download_files(["/.cgent-skills/0/demo-skill/SKILL.md"])
    assert len(responses) == 1
    assert responses[0].error is None
    assert responses[0].content is not None
    assert "Describe demo files" in responses[0].content.decode("utf-8")


def test_load_skills_middleware_gives_unique_labels_to_same_named_sources(
    settings: Settings, tmp_path: Path
) -> None:
    first = tmp_path / "one" / "team-skills"
    second = tmp_path / "two" / "team-skills"
    write_skill(first, "demo-skill")
    write_skill(second, "demo-skill", "Override demo behavior")
    settings = replace(settings, skills_dirs=(first, second))

    middleware = load_skills_middleware(settings)

    assert middleware is not None
    assert middleware.source_labels == ["Team", "Team 2"]


def test_configured_skills_backend_is_read_only() -> None:
    files = {"/.cgent-skills/0/demo/SKILL.md": create_file_data("demo")}
    backend = _ConfiguredSkillsBackend(files)

    listing = backend.ls("/.cgent-skills/0/")
    assert listing is not None and listing.entries is not None
    assert "demo" in listing.entries[0]["path"]
    assert backend.write("/x", "content").error is not None
    assert backend.edit("/x", "a", "b").error is not None
    assert backend.delete("/x").error is not None
    assert backend.upload_files([("/x", b"content")])[0].error is not None


def test_load_skills_middleware_returns_none_without_directories(
    settings: Settings,
) -> None:
    assert load_skills_middleware(settings) is None


def test_settings_reject_missing_skills_directory(settings: Settings, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Skills directory does not exist"):
        replace(settings, skills_dirs=(tmp_path / "missing",))


async def test_agent_factory_includes_configured_skills_in_system_prompt(
    settings: Settings, tmp_path: Path
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    skills_root = tmp_path / "project-skills"
    write_skill(skills_root, "demo-skill", "Describe project files")
    settings = replace(
        settings,
        workspaces={"test": workspace},
        skills_dirs=(skills_root,),
    )
    workspaces = WorkspaceRegistry(settings.workspaces)
    shell = ShellService(settings)
    model = RecordingFakeModel(messages=iter(["done"]))
    factory = AgentFactory(settings, workspaces, shell, model)
    try:
        graph = factory.create("test")
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content="hi")]},
            {"recursion_limit": settings.agent_max_steps},
        )
    finally:
        await shell.close()

    assert result["messages"]
    assert any(
        "demo-skill" in content and "Describe project files" in content
        for content in model.system_contents
    )
