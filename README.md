# Cgent

Cgent 是一个独立、单进程的 Python REST Agent Harness。它在 FastAPI 进程内运行 DeepAgents，通过同一个受控执行层向 REST 调用方和 Agent 提供 workspace 文件工具与本地程序执行能力。

项目借鉴 Open SWE 的 Agent、模型超时和请求边界设计，但运行时不导入 `openswe`、`rt`、`runtime_api` 或 `managed_deepagents`，也不需要原仓库。

## P0 范围

- 同步 `POST /v1/agent/invocations`，无数据库、无持久 thread、无异步 run 轮询。
- 固定 `workspace_id` 映射，文件路径限制在对应根目录内。
- UTF-8 文本读取、分页、目录列表、glob、字面量 grep、原子写、精确编辑和单文件删除。
- Windows 与 POSIX 的直接程序执行：allowlist、环境白名单、超时、并发上限、首尾输出窗口和进程清理。
- OpenAI-compatible Chat Completions Provider，进程内 DeepAgents 工具循环。
- 可配置宿主机 skills 目录，Agent 按 `SKILL.md` 元数据按需读取。
- 本机无认证调用、`X-Request-ID`、统一错误结构、结构化 JSON 日志和 OpenAPI。
- 单 Python 进程 Web 应用，无需构建或安装应用包。

P0 明确不包含 UI、MDA Agent Server、云 Sandbox、SQLite/PostgreSQL、SSE/WebSocket、GitHub/Slack/Linear/MCP、子代理、动态技能、持久对话或多实例队列。

## 工程结构

```text
cgent/
├── app.py                 # FastAPI 组装与资源生命周期
├── config.py              # 启动配置与 fail-fast 校验
├── api/                   # REST schema、路由、请求体限制、错误映射
├── agent/                 # DeepAgents factory、guarded backend、同步 runner
├── execution/             # Workspace、文件、Shell、策略与输出窗口
├── models/                # OpenAI-compatible 模型适配与 client 生命周期
├── resources/prompts/     # 专用系统 Prompt
└── telemetry/             # 请求关联和结构化日志
tests/
├── unit/
├── integration/
└── e2e/                   # fake model 驱动的真实 DeepAgents 工具循环
requirements.txt           # 运行依赖
requirements-dev.txt       # 开发与测试依赖
pyproject.toml             # 仅包含 pytest、Ruff、ty 配置
```

## 本地运行

要求 Python 3.13 或 3.14。依赖安装到虚拟环境，应用本身不需要安装。

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

启动前复制并编辑环境文件：

```bash
cp .env.example .env
# Windows PowerShell: Copy-Item .env.example .env
# 编辑 .env，填写 workspace、模型 ID 和模型密钥
python -m cgent
```

`Settings.from_env()` 会先自动加载 `.env`，再执行配置校验；已经存在的系统环境变量优先于 `.env`。`.env` 已被 `.gitignore` 排除，真实密钥不要写入 `.env.example`。Windows 的 workspace 路径推荐使用 `F:/path/to/workspace` 正斜杠形式，Shell allowlist 中的 Python 通常写为 `python.exe`。所有 workspace 和 allowlist 可执行文件都会在启动时解析、校验，缺失时服务拒绝启动。

默认监听 `127.0.0.1:8000`，只运行一个 worker。必须从项目根目录启动，以便 Python 直接发现 `cgent/` 应用目录。

## 配置

| 环境变量 | 默认值 | 说明 |
|---|---:|---|
| `HARNESS_WORKSPACES` | 必填 | 非空 JSON 对象；例如 `{"project":"/absolute/root"}`，Windows 也可写 `{"project":"F:/path"}` 或未转义的 `{"project":"F:\path"}` |
| `HARNESS_MODEL` | 必填 | Provider 模型 ID |
| `HARNESS_MODEL_API_KEY` | 必填 | 只用于模型 client，不传给子进程 |
| `HARNESS_MODEL_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible API 地址 |
| `HARNESS_MODEL_ADAPTER` | `http` | `http` 使用 requests 直连；`openai` 使用官方 SDK |
| `HARNESS_SKILLS_DIRS` | 空 | 逗号分隔的宿主机 skills 根目录；多个目录按顺序加载，后者覆盖同名 skill |
| `HARNESS_HOST` | `127.0.0.1` | 监听地址，仅允许 `127.0.0.1`、`localhost` 或 `::1` |
| `HARNESS_PORT` | `8000` | 监听端口 |
| `HARNESS_MODEL_TIMEOUT_SECONDS` | `600` | 单次模型调用上限 |
| `HARNESS_MODEL_MAX_RETRIES` | `3` | Provider client 重试次数 |
| `HARNESS_AGENT_TIMEOUT_SECONDS` | `600` | 整体 invocation 上限 |
| `HARNESS_AGENT_MAX_STEPS` | `50` | LangGraph recursion limit |
| `HARNESS_SHELL_ALLOWLIST` | 空 | 逗号分隔的可执行文件名或路径 |
| `HARNESS_SHELL_TIMEOUT_SECONDS` | `300` | 默认命令超时 |
| `HARNESS_SHELL_MAX_TIMEOUT_SECONDS` | `600` | 请求可设置的最大命令超时 |
| `HARNESS_SHELL_MAX_OUTPUT_BYTES` | `1048576` | 合并 stdout/stderr 的首尾字节窗口 |
| `HARNESS_MAX_CONCURRENT_SHELLS` | `4` | 单服务实例的活动 Shell 上限 |
| `HARNESS_SHELL_QUEUE_TIMEOUT_SECONDS` | `1` | 等待 Shell 容量的上限 |
| `HARNESS_SHELL_KILL_GRACE_SECONDS` | `2` | 强制终止前的宽限时间 |
| `HARNESS_SHELL_ENV_ALLOWLIST` | 系统最小集合 | 可继承的环境变量名；`HARNESS_*` 和常见 secret 始终剔除 |
| `HARNESS_MAX_BODY_BYTES` | `4194304` | API 请求体上限 |
| `HARNESS_MAX_FILE_BYTES` | `2097152` | 单文本文件读写上限 |
| `HARNESS_MAX_SEARCH_RESULTS` | `1000` | 单次 glob/grep/list 的结果上限 |
| `HARNESS_ENABLE_DIRECT_TOOLS` | `true` | 是否暴露直接文件/Shell 路由 |

## Skills

Cgent 支持在创建 Agent 时装载 DeepAgents skills。推荐通过环境变量指定宿主机目录：

```dotenv
HARNESS_SKILLS_DIRS=F:/path/to/skills
```

目录结构为：

```text
skills/
└── demo-skill/
    ├── SKILL.md
    └── helper.py          # 可选
```

`SKILL.md` 需要包含 Agent Skills 元数据，例如：

```markdown
---
name: demo-skill
description: Describe when and how to use this skill
---

# Demo Skill

具体的执行说明。
```

多个目录可用逗号分隔：

```dotenv
HARNESS_SKILLS_DIRS=F:/shared/skills,F:/project/skills
```

目录按从左到右顺序加载；不同目录存在同名 skill 时，后面的目录覆盖前面的目录。配置目录会在启动时读取，并映射为 Agent 内部只读虚拟文件，不会出现在 workspace 文件列表中，也不能通过 Agent 文件工具修改。修改 skills 后需要重启服务。

其他可行但当前未作为默认实现的方式包括：workspace 内固定 `/skills/`、应用包内置 skills、REST 请求按 invocation 选择 skills，以及远程 skills registry。前两种适合后续作为本地扩展；后两种会引入额外 API、缓存和信任边界，建议单独评审后再做。

## REST API

当前为本机无认证模式，所有端点都不需要 `Authorization` 或 API key。文件、Shell 和 Agent 调用需要 `X-Workspace-ID: <预配置 ID>`。响应包含 `X-Request-ID`；调用方也可以传入符合 `req_<uuid>` 格式的请求 ID。

| 方法与路径 | 功能 |
|---|---|
| `GET /health` | 无认证健康检查 |
| `GET /docs` | Swagger UI 接口文档 |
| `GET /redoc` | ReDoc 接口文档 |
| `GET /openapi.json` | 机器可读 OpenAPI schema |
| `GET /v1/tools` | 工具与输入 schema 发现 |
| `POST /v1/agent/invocations` | 同步 Agent 调用 |
| `GET /v1/files` | `mode=list\|glob\|grep` |
| `GET /v1/files/{path}` | 文本读取，`offset`/`limit` 分页 |
| `PUT /v1/files/{path}` | 创建或原子覆盖文本 |
| `PATCH /v1/files/{path}` | 精确字符串编辑 |
| `DELETE /v1/files/{path}` | 删除单文件，不递归删目录 |
| `POST /v1/shell/executions` | 同步程序执行 |

Agent 示例：

```bash
curl http://127.0.0.1:8000/v1/agent/invocations \
  -H 'X-Workspace-ID: project' \
  -H 'Content-Type: application/json' \
  -d '{"input":"阅读项目并修复一个聚焦问题，运行相关验证","timeout_seconds":600}'
```

文件写入与精确编辑：

```bash
curl -X PUT 'http://127.0.0.1:8000/v1/files/note.txt' \
  -H 'X-Workspace-ID: project' \
  -H 'Content-Type: application/json' -d '{"content":"before"}'

curl -X PATCH 'http://127.0.0.1:8000/v1/files/note.txt' \
  -H 'X-Workspace-ID: project' \
  -H 'Content-Type: application/json' \
  -d '{"old_string":"before","new_string":"after","replace_all":false}'
```

直接程序执行：

```bash
curl http://127.0.0.1:8000/v1/shell/executions \
  -H 'X-Workspace-ID: project' \
  -H 'Content-Type: application/json' \
  -d '{"command":"pytest tests/unit -q","timeout_seconds":300}'
```

`execute` 不启动 `cmd`、`sh` 或 PowerShell，因此管道、重定向和 shell 内建命令不可用。非零退出码仍以 HTTP 200 返回，并使用 `status="failed"`；超时返回 `status="timed_out"` 和 `exit_code=124`。

统一错误示例：

```json
{
  "error": {
    "code": "path_outside_workspace",
    "message": "The requested path is outside the workspace"
  },
  "request_id": "req_..."
}
```

## 安全边界

Cgent 是仅面向本机的无认证受控执行器，**不是多租户 Sandbox**。任何能访问本机端口的人都能调用文件和 Shell 接口，不得将服务暴露到局域网或公网。

- 文件 API 使用虚拟路径并拒绝绝对宿主机路径、`..` 和 symlink 逃逸；这只是路径边界，不是完整 OS 隔离。
- Shell 只直接启动启动时固定的 allowlist 可执行文件，但被允许的程序本身仍能访问其 OS 用户有权访问的资源。
- 使用专用低权限 OS 用户，只授予必要 workspace 写权限，不要以 root/Administrator 运行。
- 启动配置强制使用 loopback；`0.0.0.0` 和非本机地址会被拒绝。需要远程访问时，必须先重新设计认证与隔离边界。
- 子进程环境不继承模型 key 或其他 `HARNESS_*` 变量。日志不记录请求正文、命令正文或文件正文。
- 单实例的内存并发和活动任务表不能用于多 worker/多副本直接水平扩容。
- 文件写入与本地进程具有真实副作用；请求超时不会回滚已完成的文件修改。

## 开发验证

```bash
ruff check cgent tests
ruff format --check cgent tests
ty check
pytest
```

默认测试不访问真实模型或外部服务。E2E 测试使用 fake chat model 驱动真实 DeepAgents，验证文件读取、修改、Shell 执行和最终响应。真实 Provider 的兼容性与凭据需要在部署环境中单独验证。

## 许可与来源

Cgent 使用 MIT License。少量模型超时和请求体限制模式改编自 Open SWE，相关源码保留来源注释；Open SWE 的 MIT 归属保留在 `LICENSE` 中。
