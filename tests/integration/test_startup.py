import json
import os
from dataclasses import replace
from pathlib import Path

import pytest
from conftest import FakeToolCallingModel, app_client

from cgent.app import create_app
from cgent.config import Settings


def test_settings_load_independent_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HARNESS_WORKSPACES", json.dumps({"project": str(tmp_path)}))
    monkeypatch.setenv("HARNESS_HOST", "127.0.0.1")
    monkeypatch.setenv("HARNESS_MODEL", "model-id")
    monkeypatch.setenv("HARNESS_MODEL_API_KEY", "model-secret")

    settings = Settings.from_env()

    assert settings.workspaces == {"project": tmp_path.resolve()}
    assert settings.model == "model-id"


def test_settings_fail_fast_for_missing_configuration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "HARNESS_WORKSPACES",
        "HARNESS_MODEL",
        "HARNESS_MODEL_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ValueError, match="Missing required environment variables"):
        Settings.from_env(dotenv_path=tmp_path / ".env")


def test_settings_load_dotenv_and_preserve_process_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "HARNESS_WORKSPACES",
        "HARNESS_MODEL",
        "HARNESS_MODEL_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        f"HARNESS_WORKSPACES='{json.dumps({'project': workspace.as_posix()})}'\n"
        "HARNESS_MODEL=dotenv-model\n"
        "HARNESS_MODEL_API_KEY=dotenv-secret\n"
        "HARNESS_HOST=127.0.0.1\n",
        encoding="utf-8",
    )

    loaded = Settings.from_env(dotenv_path=dotenv_path)
    assert loaded.workspaces == {"project": workspace.resolve()}
    assert loaded.model == "dotenv-model"
    assert loaded.model_api_key == "dotenv-secret"

    monkeypatch.setenv("HARNESS_MODEL", "process-model")
    overridden = Settings.from_env(dotenv_path=dotenv_path)
    assert overridden.model == "process-model"


@pytest.mark.skipif(os.name != "nt", reason="Windows path syntax test")
def test_settings_load_unescaped_windows_workspace_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name in (
        "HARNESS_WORKSPACES",
        "HARNESS_MODEL",
        "HARNESS_MODEL_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    workspace = tmp_path / "docs"
    workspace.mkdir()
    windows_path = str(workspace).replace("/", "\\")
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        f'HARNESS_WORKSPACES={{"project":"{windows_path}"}}\n'
        "HARNESS_MODEL=dotenv-model\n"
        "HARNESS_MODEL_API_KEY=dotenv-secret\n",
        encoding="utf-8",
    )

    loaded = Settings.from_env(dotenv_path=dotenv_path)

    assert loaded.workspaces == {"project": workspace.resolve()}


def test_settings_reject_non_loopback_host(settings: Settings) -> None:
    with pytest.raises(ValueError, match="loopback"):
        replace(settings, host="0.0.0.0")


async def test_direct_tools_can_be_disabled(
    settings: Settings, workspace_headers: dict[str, str]
) -> None:
    app = create_app(
        replace(settings, enable_direct_tools=False),
        model=FakeToolCallingModel(messages=iter([])),
    )
    async with app_client(app) as client:
        tools = await client.get("/v1/tools", headers=workspace_headers)
        assert [tool["name"] for tool in tools.json()["tools"]] == ["agent_invoke"]
        assert (await client.get("/v1/files", headers=workspace_headers)).status_code == 404
        assert (
            await client.post(
                "/v1/shell/executions", json={"command": "x"}, headers=workspace_headers
            )
        ).status_code == 404
        assert (await client.get("/health")).status_code == 200
