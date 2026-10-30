r"""Create F:\templates\coding\docs\hello.py through the Agent REST API.

The current service maps the "project" workspace ID to F:/templates/coding/docs.
WORKSPACE_ID must be the configured ID, not the filesystem path.
"""

import time

import requests

BASE_URL = "http://127.0.0.1:8000"
WORKSPACE_ID = "project"
HEADERS = {"X-Workspace-ID": WORKSPACE_ID}
EXPECTED_CONTENT = 'print("hello")\n'

# POST /v1/agent/invocations accepts asynchronously and returns 202.
response = requests.post(
    f"{BASE_URL}/v1/agent/invocations",
    headers=HEADERS,
    json={
        "input": (
            "Create a file at /hello.py with exactly this content and nothing else:\n"
            'print("hello")\n'
            "Do not use Shell. Reply after the write_file tool succeeds."
        ),
        "timeout_seconds": 120,
    },
    timeout=30,
)
assert response.status_code == 202, response.text
invocation_id = response.json()["invocation_id"]

# GET /v1/agent/invocations/{invocation_id} polls until the invocation finishes.
deadline = time.monotonic() + 180
while True:
    response = requests.get(
        f"{BASE_URL}/v1/agent/invocations/{invocation_id}",
        headers=HEADERS,
        timeout=30,
    )
    assert response.status_code == 200, response.text
    invocation = response.json()
    if invocation["status"] != "pending":
        break
    assert time.monotonic() < deadline, "The invocation did not finish in time"
    time.sleep(2)

print(invocation)
assert invocation["status"] == "succeeded", invocation
print("POST /v1/agent/invocations:", invocation["status"], invocation["output"])

# GET /v1/files/{path}
response = requests.get(f"{BASE_URL}/v1/files/hello.py", headers=HEADERS, timeout=10)
assert response.status_code == 200, response.text
created = response.json()
assert created["path"] == "/hello.py", created
assert created["content"] == EXPECTED_CONTENT, created
print("GET /v1/files/hello.py:", created)
