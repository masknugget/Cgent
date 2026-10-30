# 快速开始

## 环境要求

- Python 3.13 或 3.14
- 一个 OpenAI-compatible 的模型服务(API key + base URL + 模型 ID)
- Windows、Linux 或 macOS

## 安装与启动

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell:
.venv\Scripts\Activate.ps1

pip install -r requirements-dev.txt
```

复制并编辑环境文件：

```bash
cp .env.example .env
# Windows PowerShell: Copy-Item .env.example .env
```

`.env` 最少需要填写三项：

```dotenv
HARNESS_WORKSPACES={"project":"/absolute/path/to/workspace"}
HARNESS_MODEL=your-model-id
HARNESS_MODEL_API_KEY=your-provider-key
```

从项目根目录启动：

```bash
python -m cgent
```

启动时会自动加载 `.env`(已存在的系统环境变量优先),并做 fail-fast 校验:workspace 目录、skills 目录、allowlist 可执行文件缺失时服务拒绝启动。

默认监听 `127.0.0.1:8000`，单 worker。必须用本机回环地址访问，服务启动时会拒绝 `0.0.0.0` 等非 loopback 配置。

## 验证服务

```bash
curl http://127.0.0.1:8000/health
# {"status":"healthy"}

curl http://127.0.0.1:8000/v1/tools
# 工具与输入 schema 发现
```

Swagger UI:`http://127.0.0.1:8000/docs`

## 第一个 Agent 调用

```bash
curl http://127.0.0.1:8000/v1/agent/invocations \
  -H 'X-Workspace-ID: project' \
  -H 'Content-Type: application/json' \
  -d '{"input":"列出当前目录结构并总结项目用途","timeout_seconds":600}'
```

响应：

```json
{
  "invocation_id": "inv_...",
  "status": "succeeded",
  "output": "...",
  "tool_calls": [
    {"name": "ls", "status": "completed", "exit_code": null, "error": null}
  ],
  "usage": {"input_tokens": 1234, "output_tokens": 567, "total_tokens": 1801}
}
```

- `X-Workspace-ID` 必须是 `HARNESS_WORKSPACES` 中预配置的 key。
- `timeout_seconds` 可选，上限受 `HARNESS_AGENT_TIMEOUT_SECONDS` 约束。
- 调用是同步的：请求返回即 invocation 完成(成功或失败)。

## 下一步

- 配置全部可调项:[配置参考](configuration.md)
- 挂载 skills:[Skills 使用](skills.md)
- 各端点细节:[REST API](api.md)
