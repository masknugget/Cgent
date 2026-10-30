# REST API

本机无认证模式。文件、Shell 和 Agent 调用需要 `X-Workspace-ID: <预配置 ID>` 头；健康检查和文档端点不需要。

- 所有响应带 `X-Request-ID`;调用方也可以传入符合 `req_<uuid>` 格式的请求 ID。
- 请求体上限 `HARNESS_MAX_BODY_BYTES`(默认 4 MiB)。
- 统一错误结构见下文。

## 端点总览

| 方法与路径 | 功能 | 需要 workspace 头 |
|---|---|---|
| `GET /health` | 健康检查 | 否 |
| `GET /docs` | Swagger UI | 否 |
| `GET /redoc` | ReDoc | 否 |
| `GET /openapi.json` | OpenAPI schema | 否 |
| `GET /v1/tools` | 工具与输入 schema 发现 | 否 |
| `POST /v1/agent/invocations` | 同步 Agent 调用 | 是 |
| `GET /v1/files` | `mode=list\|glob\|grep` | 是 |
| `GET /v1/files/{path}` | 文本读取，支持分页 | 是 |
| `PUT /v1/files/{path}` | 创建或原子覆盖文本 | 是 |
| `PATCH /v1/files/{path}` | 精确字符串编辑 | 是 |
| `DELETE /v1/files/{path}` | 删除单文件(不递归删目录) | 是 |
| `POST /v1/shell/executions` | 同步程序执行 | 是 |

`HARNESS_ENABLE_DIRECT_TOOLS=false` 时，文件与 Shell 端点不暴露，只剩健康检查、文档、tools 和 Agent invocation。

## Agent 调用

### `POST /v1/agent/invocations`

请求体:

| 字段 | 类型 | 说明 |
|---|---|---|
| `input` | string，必填，1–1,000,000 字符 | 自然语言任务描述 |
| `timeout_seconds` | number，可选，>0 | 本次调用上限，受 `HARNESS_AGENT_TIMEOUT_SECONDS` 约束 |

```bash
curl http://127.0.0.1:8000/v1/agent/invocations \
  -H 'X-Workspace-ID: project' \
  -H 'Content-Type: application/json' \
  -d '{"input":"阅读项目并修复一个聚焦问题，运行相关验证","timeout_seconds":600}'
```

响应:

```json
{
  "invocation_id": "inv_...",
  "status": "succeeded",
  "output": "最终回复文本",
  "tool_calls": [
    {"name": "read_file", "status": "completed", "exit_code": null, "error": null},
    {"name": "execute", "status": "completed", "exit_code": 0, "error": null}
  ],
  "usage": {"input_tokens": 1234, "output_tokens": 567, "total_tokens": 1801}
}
```

- `status` 固定为 `succeeded`(失败走错误响应)。
- `tool_calls[].status` ∈ `pending | completed | failed`。
- `usage` 在 Provider 返回 token 用量时存在，否则为 `null`。

## 文件操作

路径均为 workspace 内的虚拟相对路径:拒绝绝对宿主机路径、`..` 和 symlink 逃逸。

### `GET /v1/files` — 搜索

查询参数:

| 参数 | 说明 |
|---|---|
| `mode` | `list`(默认) / `glob` / `grep` |
| `path` | 起始目录，默认 `/` |
| `pattern` | `glob` 或 `grep` 模式(对应模式下必填) |
| `glob` | grep 时的文件名过滤(可选) |
| `max_results` | 结果上限(可选，受全局上限约束) |

```bash
# 列出目录
curl 'http://127.0.0.1:8000/v1/files?mode=list&path=/' -H 'X-Workspace-ID: project'

# glob 查找 Python 文件
curl 'http://127.0.0.1:8000/v1/files?mode=glob&pattern=**/*.py' -H 'X-Workspace-ID: project'

# grep 字面量搜索
curl 'http://127.0.0.1:8000/v1/files?mode=grep&pattern=TODO' -H 'X-Workspace-ID: project'
```

响应包含 `entries`(文件列表)、`matches`(grep 命中)、`truncated` 与 `truncation_reason`。

### `GET /v1/files/{path}` — 读取

查询参数:`offset`(起始行，默认 0)、`limit`(1–10000，默认 2000)。

```bash
curl 'http://127.0.0.1:8000/v1/files/src/app.py?offset=0&limit=200' \
  -H 'X-Workspace-ID: project'
```

响应含 `content`、`total_lines`、`start_line`/`end_line`、`next_offset`(分页游标)。

### `PUT /v1/files/{path}` — 写入

```bash
curl -X PUT 'http://127.0.0.1:8000/v1/files/note.txt' \
  -H 'X-Workspace-ID: project' \
  -H 'Content-Type: application/json' \
  -d '{"content":"hello"}'
```

原子覆盖;文件超过 `HARNESS_MAX_FILE_BYTES` 时报错。

### `PATCH /v1/files/{path}` — 精确编辑

```bash
curl -X PATCH 'http://127.0.0.1:8000/v1/files/note.txt' \
  -H 'X-Workspace-ID: project' \
  -H 'Content-Type: application/json' \
  -d '{"old_string":"hello","new_string":"world","replace_all":false}'
```

- `old_string` 非空；默认要求唯一匹配，`replace_all=true` 可替换多处。
- 匹配不到或多处匹配时返回错误。

### `DELETE /v1/files/{path}`

删除单个文件，返回 `204 No Content`。不递归删除目录。

## Shell 执行

### `POST /v1/shell/executions`

请求体:

| 字段 | 类型 | 说明 |
|---|---|---|
| `command` | string，必填，1–100,000 字符 | 要执行的程序 |
| `timeout_seconds` | number，可选，>0 | 命令超时，受 `HARNESS_SHELL_MAX_TIMEOUT_SECONDS` 约束 |

```bash
curl http://127.0.0.1:8000/v1/shell/executions \
  -H 'X-Workspace-ID: project' \
  -H 'Content-Type: application/json' \
  -d '{"command":"python.exe -m pytest tests/unit -q","timeout_seconds":300}'
```

响应:

```json
{
  "execution_id": "exe_...",
  "status": "completed",
  "exit_code": 0,
  "output": "...",
  "truncated": false,
  "duration_seconds": 12.3
}
```

- `status` ∈ `completed | failed | timed_out | stopped`。
- **非零退出码仍以 HTTP 200 返回**，用 `status="failed"` 表达。
- 超时返回 `status="timed_out"` 和 `exit_code=124`。
- 输出按首尾字节窗口截断，超出时 `truncated=true`。

重要:`execute` **不启动 shell**(不是 `cmd`/`sh`/PowerShell),因此管道、重定向和 shell 内建命令不可用，只能直接启动 allowlist 中的可执行文件。需要组合多个步骤时，把它们作为多次调用，或用一个脚本文件 + 单个解释器调用。

## 统一错误结构

所有错误(含 4xx/5xx)使用同一结构:

```json
{
  "error": {
    "code": "path_outside_workspace",
    "message": "The requested path is outside the workspace"
  },
  "request_id": "req_..."
}
```

排障时把 `request_id` 与服务端结构化日志关联。

## 工具发现

`GET /v1/tools` 返回可用工具列表，每项含 `name`、`description`、`method`、`path` 和 JSON `input_schema`,适合动态生成调用方 UI 或 CLI。
