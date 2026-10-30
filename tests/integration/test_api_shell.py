from pathlib import Path

from conftest import FakeToolCallingModel, app_client, python_command

from cgent.app import create_app
from cgent.config import Settings


async def test_shell_rest_executes_in_selected_workspace(
    settings: Settings, workspace_headers: dict[str, str], tmp_path: Path
) -> None:
    app = create_app(settings, model=FakeToolCallingModel(messages=iter([])))
    async with app_client(app) as client:
        response = await client.post(
            "/v1/shell/executions",
            json={
                "command": python_command("from pathlib import Path; print(Path.cwd().resolve())")
            },
            headers=workspace_headers,
        )

        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "completed"
        assert result["exit_code"] == 0
        assert Path(result["output"].strip()) == tmp_path.resolve()
        assert result["execution_id"].startswith("cmd_")


async def test_shell_rest_returns_nonzero_exit_and_policy_errors(
    settings: Settings, workspace_headers: dict[str, str]
) -> None:
    app = create_app(settings, model=FakeToolCallingModel(messages=iter([])))
    async with app_client(app) as client:
        failed = await client.post(
            "/v1/shell/executions",
            json={"command": python_command("raise SystemExit(9)")},
            headers=workspace_headers,
        )
        assert failed.status_code == 200
        assert failed.json()["status"] == "failed"
        assert failed.json()["exit_code"] == 9

        rejected = await client.post(
            "/v1/shell/executions",
            json={"command": "not-allowlisted --version"},
            headers=workspace_headers,
        )
        assert rejected.status_code == 403
        assert rejected.json()["error"]["code"] == "command_rejected"
