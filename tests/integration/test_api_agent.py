import asyncio

from conftest import FakeToolCallingModel, app_client
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from cgent.app import create_app
from cgent.config import Settings


class GatedModel(FakeToolCallingModel):
    """A model that waits on an asyncio.Event before responding."""

    def __init__(self, gate: asyncio.Event) -> None:
        super().__init__(messages=iter([]))
        self._gate = gate

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        await self._gate.wait()
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="done"))])


async def _wait_for_finished(client, invocation_id: str) -> dict:
    for _ in range(500):
        response = await client.get(f"/v1/agent/invocations/{invocation_id}")
        assert response.status_code == 200
        result = response.json()
        if result["status"] != "pending":
            return result
        await asyncio.sleep(0.01)
    raise AssertionError("The invocation did not finish in time")


async def test_agent_invocation_submit_and_poll_succeeded(
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

        assert response.status_code == 202
        accepted = response.json()
        assert accepted["invocation_id"].startswith("inv_")
        assert accepted["status"] == "pending"

        result = await _wait_for_finished(client, accepted["invocation_id"])
        assert result["status"] == "succeeded"
        assert result["output"] == "completed"
        assert result["tool_calls"] == []
        assert result["usage"] == {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}
        assert result["error"] is None


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


async def test_agent_invocation_status_unknown_id_returns_404(
    settings: Settings, workspace_headers: dict[str, str]
) -> None:
    app = create_app(settings, model=FakeToolCallingModel(messages=iter([])))
    async with app_client(app) as client:
        response = await client.get("/v1/agent/invocations/inv_missing")
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "invocation_not_found"


async def test_agent_invocation_cancel_pending_and_finished_conflict(
    settings: Settings, workspace_headers: dict[str, str]
) -> None:
    gate = asyncio.Event()
    app = create_app(settings, model=GatedModel(gate))
    async with app_client(app) as client:
        response = await client.post(
            "/v1/agent/invocations", json={"input": "hang"}, headers=workspace_headers
        )
        assert response.status_code == 202
        invocation_id = response.json()["invocation_id"]

        cancel = await client.delete(f"/v1/agent/invocations/{invocation_id}")
        assert cancel.status_code == 204
        gate.set()

        result = await _wait_for_finished(client, invocation_id)
        assert result["status"] == "cancelled"

        again = await client.delete(f"/v1/agent/invocations/{invocation_id}")
        assert again.status_code == 409
        assert again.json()["error"]["code"] == "invocation_not_cancellable"
