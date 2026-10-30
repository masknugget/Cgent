r"""Minimal requests examples for every Cgent endpoint.

Run the service first, then execute this file from the project root:

    .venv\Scripts\python.exe tests\api_examples\requests_examples.py

Replace WORKSPACE_ID and BASE_URL with your local values if they differ.
"""

import requests

BASE_URL = "http://127.0.0.1:8000"
WORKSPACE_ID = "project"
HEADERS = {"X-Workspace-ID": WORKSPACE_ID}
FILE_PATH = "api-examples/requests-demo.txt"

# GET /health
response = requests.get(f"{BASE_URL}/health", timeout=10)
assert response.status_code == 200, response.text
print("GET /health:", response.json())

# GET /docs
response = requests.get(f"{BASE_URL}/docs", timeout=10)
assert response.status_code == 200, response.text
print("GET /docs:", response.status_code)

# GET /redoc
response = requests.get(f"{BASE_URL}/redoc", timeout=10)
assert response.status_code == 200, response.text
print("GET /redoc:", response.status_code)

# GET /openapi.json
response = requests.get(f"{BASE_URL}/openapi.json", timeout=10)
assert response.status_code == 200, response.text
print("GET /openapi.json:", response.json()["info"])

# GET /v1/tools
response = requests.get(f"{BASE_URL}/v1/tools", timeout=10)
assert response.status_code == 200, response.text
print("GET /v1/tools:", [tool["name"] for tool in response.json()["tools"]])

# PUT /v1/files/{path}
response = requests.put(
    f"{BASE_URL}/v1/files/{FILE_PATH}",
    headers=HEADERS,
    json={"content": "before\nsecond line\n"},
    timeout=10,
)
assert response.status_code == 200, response.text
print("PUT /v1/files/{path}:", response.json())

# GET /v1/files/{path}
response = requests.get(f"{BASE_URL}/v1/files/{FILE_PATH}", headers=HEADERS, timeout=10)
assert response.status_code == 200, response.text
print("GET /v1/files/{path}:", response.json()["content"])

# PATCH /v1/files/{path}
response = requests.patch(
    f"{BASE_URL}/v1/files/{FILE_PATH}",
    headers=HEADERS,
    json={"old_string": "before", "new_string": "after", "replace_all": False},
    timeout=10,
)
assert response.status_code == 200, response.text
print("PATCH /v1/files/{path}:", response.json())

# GET /v1/files?mode=list
response = requests.get(
    f"{BASE_URL}/v1/files",
    headers=HEADERS,
    params={"mode": "list", "path": "/api-examples"},
    timeout=10,
)
assert response.status_code == 200, response.text
print("GET /v1/files list:", response.json())

# GET /v1/files?mode=glob
response = requests.get(
    f"{BASE_URL}/v1/files",
    headers=HEADERS,
    params={"mode": "glob", "path": "/", "pattern": "*.txt"},
    timeout=10,
)
assert response.status_code == 200, response.text
print("GET /v1/files glob:", response.json())

# GET /v1/files?mode=grep
response = requests.get(
    f"{BASE_URL}/v1/files",
    headers=HEADERS,
    params={"mode": "grep", "path": "/api-examples", "pattern": "after"},
    timeout=10,
)
assert response.status_code == 200, response.text
print("GET /v1/files grep:", response.json())

# POST /v1/shell/executions
response = requests.post(
    f"{BASE_URL}/v1/shell/executions",
    headers=HEADERS,
    json={"command": "python -c \"print('hello from requests')\"", "timeout_seconds": 30},
    timeout=40,
)
assert response.status_code == 200, response.text
print("POST /v1/shell/executions:", response.json())

# POST /v1/agent/invocations
response = requests.post(
    f"{BASE_URL}/v1/agent/invocations",
    headers=HEADERS,
    json={"input": "Reply exactly: ready", "timeout_seconds": 120},
    timeout=180,
)
assert response.status_code == 200, response.text
print("POST /v1/agent/invocations:", response.json()["output"])

# DELETE /v1/files/{path}
response = requests.delete(f"{BASE_URL}/v1/files/{FILE_PATH}", headers=HEADERS, timeout=10)
assert response.status_code == 204, response.text
print("DELETE /v1/files/{path}:", response.status_code)

# GET /v1/files/{path} after deletion
response = requests.get(f"{BASE_URL}/v1/files/{FILE_PATH}", headers=HEADERS, timeout=10)
assert response.status_code == 404, response.text
print("GET deleted file:", response.json()["error"]["code"])
