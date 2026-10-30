r"""List F:\templates\coding\docs and describe each file through the Agent REST API.

The current service maps the "project" workspace ID to F:/templates/coding/docs.
WORKSPACE_ID must be the configured ID, not the filesystem path.
"""

import requests

BASE_URL = "http://127.0.0.1:8000"
WORKSPACE_ID = "project"
HEADERS = {"X-Workspace-ID": WORKSPACE_ID}

# POST /v1/agent/invocations
response = requests.post(
    f"{BASE_URL}/v1/agent/invocations",
    headers=HEADERS,
    json={
        "input": (
            "Recursively traverse the entire workspace starting at / using the file tools. "
            "Enumerate every directory and every file at every depth; do not list only the "
            "top level and do not omit nested files. For each file, inspect enough content "
            "to infer its purpose. Reply in Chinese as a flat recursive Markdown list. "
            "Use one bullet per file or directory in this exact format:\n"
            "- `/full/virtual/path/file-or-dir` — 简洁说明。\n"
            "For directories, summarize what they contain; for files, explain their role. "
            "Do not modify or delete any file."
        ),
        "timeout_seconds": 600,
    },
    timeout=660,
)
assert response.status_code == 200, response.text
invocation = response.json()
assert invocation["status"] == "succeeded", invocation
assert invocation["output"].strip(), invocation
print("POST /v1/agent/invocations:", invocation["status"])
print(invocation["output"])
