from dataclasses import replace

from conftest import FakeToolCallingModel, app_client

from cgent.app import create_app
from cgent.config import Settings


async def test_health_discovery_and_openapi_without_authentication(
    settings: Settings, workspace_headers: dict[str, str]
) -> None:
    app = create_app(settings, model=FakeToolCallingModel(messages=iter([])))
    async with app_client(app) as client:
        health = await client.get("/health")
        assert health.status_code == 200
        assert health.json() == {"status": "healthy"}
        assert health.headers["x-request-id"].startswith("req_")

        request_id = "req_12345678-1234-1234-1234-123456789abc"
        tools = await client.get(
            "/v1/tools", headers={**workspace_headers, "X-Request-ID": request_id}
        )
        assert tools.status_code == 200
        assert tools.headers["x-request-id"] == request_id
        assert {tool["name"] for tool in tools.json()["tools"]} == {
            "agent_invoke",
            "file_search",
            "file_read",
            "file_write",
            "file_edit",
            "file_delete",
            "shell_execute",
        }

        public_tools = await client.get("/v1/tools")
        assert public_tools.status_code == 200
        assert public_tools.json()["tools"]
        assert public_tools.headers["x-request-id"].startswith("req_")
        assert (await client.get("/openapi.json")).status_code == 200

        schema = await client.get("/openapi.json")
        assert schema.status_code == 200
        assert "/v1/agent/invocations" in schema.json()["paths"]
        assert (await client.get("/docs")).status_code == 200
        assert (await client.get("/redoc")).status_code == 200


async def test_file_rest_crud_and_search(
    settings: Settings, workspace_headers: dict[str, str]
) -> None:
    app = create_app(settings, model=FakeToolCallingModel(messages=iter([])))
    async with app_client(app) as client:
        created = await client.put(
            "/v1/files/note.txt", json={"content": "alpha\nbeta\n"}, headers=workspace_headers
        )
        assert created.status_code == 200
        assert created.json()["path"] == "/note.txt"

        read = await client.get("/v1/files/note.txt?offset=1&limit=1", headers=workspace_headers)
        assert read.status_code == 200
        assert read.json()["content"] == "beta\n"
        assert read.json()["total_lines"] == 2

        edited = await client.patch(
            "/v1/files/note.txt",
            json={"old_string": "alpha", "new_string": "updated"},
            headers=workspace_headers,
        )
        assert edited.status_code == 200
        assert edited.json()["occurrences"] == 1

        found = await client.get(
            "/v1/files?mode=grep&pattern=updated&glob=*.txt", headers=workspace_headers
        )
        assert found.status_code == 200
        assert found.json()["matches"][0]["path"] == "/note.txt"

        deleted = await client.delete("/v1/files/note.txt", headers=workspace_headers)
        assert deleted.status_code == 204
        missing = await client.get("/v1/files/note.txt", headers=workspace_headers)
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "file_not_found"


async def test_file_rest_errors_and_body_limit(
    settings: Settings, workspace_headers: dict[str, str]
) -> None:
    settings = replace(settings, max_body_bytes=128)
    app = create_app(settings, model=FakeToolCallingModel(messages=iter([])))
    async with app_client(app) as client:
        unknown = await client.get(
            "/v1/files", headers={**workspace_headers, "X-Workspace-ID": "unknown"}
        )
        assert unknown.status_code == 404
        assert unknown.json()["error"]["code"] == "workspace_not_found"

        invalid = await client.get("/v1/files/note.txt?offset=-1", headers=workspace_headers)
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "validation_error"

        oversized = await client.put(
            "/v1/files/note.txt", json={"content": "x" * 256}, headers=workspace_headers
        )
        assert oversized.status_code == 413
        assert oversized.json()["error"]["code"] == "payload_too_large"
