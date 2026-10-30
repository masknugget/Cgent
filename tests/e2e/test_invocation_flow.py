import asyncio
from pathlib import Path

from conftest import FakeToolCallingModel, app_client, python_command
from langchain_core.messages import AIMessage

from cgent.app import create_app
from cgent.config import Settings


async def _wait_for_finished(client, invocation_id: str) -> dict:
    for _ in range(500):
        response = await client.get(f"/v1/agent/invocations/{invocation_id}")
        assert response.status_code == 200
        result = response.json()
        if result["status"] != "pending":
            return result
        await asyncio.sleep(0.01)
    raise AssertionError("The invocation did not finish in time")


async def test_agent_reads_edits_executes_and_summarizes(
    settings: Settings, workspace_headers: dict[str, str], tmp_path: Path
) -> None:
    (tmp_path / "note.txt").write_text("before", encoding="utf-8")
    model = FakeToolCallingModel(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "read_file",
                            "args": {"file_path": "/note.txt"},
                            "id": "call-read",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "edit_file",
                            "args": {
                                "file_path": "/note.txt",
                                "old_string": "before",
                                "new_string": "after",
                            },
                            "id": "call-edit",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "execute",
                            "args": {
                                "command": python_command(
                                    "from pathlib import Path; "
                                    "print(Path('note.txt').read_text(encoding='utf-8'))"
                                )
                            },
                            "id": "call-execute",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="read-edit-execute-verified"),
            ]
        )
    )
    app = create_app(settings, model=model)

    async with app_client(app) as client:
        response = await client.post(
            "/v1/agent/invocations",
            json={"input": "Read, update and verify note.txt"},
            headers=workspace_headers,
        )
        assert response.status_code == 202
        invocation_id = response.json()["invocation_id"]

        result = await _wait_for_finished(client, invocation_id)

    assert result["status"] == "succeeded"
    assert result["output"] == "read-edit-execute-verified"
    assert [call["name"] for call in result["tool_calls"]] == [
        "read_file",
        "edit_file",
        "execute",
    ]
    assert [call["status"] for call in result["tool_calls"]] == [
        "completed",
        "completed",
        "completed",
    ]
    assert result["tool_calls"][2]["exit_code"] == 0
    assert (tmp_path / "note.txt").read_text(encoding="utf-8") == "after"
