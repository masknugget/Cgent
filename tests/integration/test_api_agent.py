from conftest import FakeToolCallingModel, app_client
from langchain_core.messages import AIMessage

from cgent.app import create_app
from cgent.config import Settings


async def test_agent_rest_invocation_returns_final_message(
    settings: Settings, workspace_headers: dict[str, str]
) -> None:
    model = FakeToolCallingModel(
        messages=iter(
            [
                AIMessage(
                    content="completed",
                    usage_metadata={
                        "input_tokens": 3,
                        "output_tokens": 2,
                        "total_tokens": 5,
                    },
                )
            ]
        )
    )
    app = create_app(settings, model=model)
    async with app_client(app) as client:
        response = await client.post(
            "/v1/agent/invocations", json={"input": "do the task"}, headers=workspace_headers
        )

        assert response.status_code == 200
        result = response.json()
        assert result["invocation_id"].startswith("inv_")
        assert result["status"] == "succeeded"
        assert result["output"] == "completed"
        assert result["tool_calls"] == []
        assert result["usage"] == {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}


async def test_agent_rest_validates_workspace_and_input(
    settings: Settings, workspace_headers: dict[str, str]
) -> None:
    app = create_app(settings, model=FakeToolCallingModel(messages=iter([])))
    async with app_client(app) as client:
        unknown = await client.post(
            "/v1/agent/invocations",
            json={"input": "task"},
            headers={**workspace_headers, "X-Workspace-ID": "unknown"},
        )
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "workspace_not_found"

        invalid = await client.post(
            "/v1/agent/invocations", json={"input": ""}, headers=workspace_headers
        )
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "validation_error"
