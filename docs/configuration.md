# 配置参考

所有配置通过环境变量提供。`Settings.from_env()` 先自动加载 `.env`(系统已存在的环境变量优先于 `.env`),再执行校验，非法配置在启动时直接报错退出。

## 必填项

| 环境变量 | 说明 |
|---|---|
| `HARNESS_WORKSPACES` | 非空 JSON 对象,`workspace_id` 到宿主机根目录的映射。例如 `{"project":"/absolute/root"}`;Windows 推荐正斜杠 `{"project":"F:/path"}`，未转义反斜杠 `{"project":"F:\path"}` 也兼容。ID 须匹配 `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`，目录必须已存在 |
| `HARNESS_MODEL` | Provider 模型 ID |
| `HARNESS_MODEL_API_KEY` | 模型密钥。只用于模型 client，不会传给子进程，也不会写入日志 |

## 模型

| 环境变量 | 默认值 | 说明 |
|---|---:|---|
| `HARNESS_MODEL_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible API 地址 |
| `HARNESS_MODEL_ADAPTER` | `http` | `http` 使用 requests 直连;`openai` 使用官方 SDK |
| `HARNESS_MODEL_TIMEOUT_SECONDS` | `600` | 单次模型调用上限 |
| `HARNESS_MODEL_MAX_RETRIES` | `3` | Provider client 重试次数 |

## Skills

| 环境变量 | 默认值 | 说明 |
|---|---:|---|
| `HARNESS_SKILLS_DIRS` | 空 | 逗号分隔的宿主机 skills 根目录;多个目录按顺序加载，后者覆盖同名 skill。目录必须在启动时存在。详见 [Skills 使用](skills.md) |

## 网络

| 环境变量 | 默认值 | 说明 |
|---|---:|---|
| `HARNESS_HOST` | `127.0.0.1` | 仅允许 `127.0.0.1`、`localhost` 或 `::1` |
| `HARNESS_PORT` | `8000` | 监听端口，范围 1–65535 |

## Agent

| 环境变量 | 默认值 | 说明 |
|---|---:|---|
| `HARNESS_AGENT_TIMEOUT_SECONDS` | `600` | 整体 invocation 上限 |
| `HARNESS_AGENT_MAX_STEPS` | `50` | LangGraph recursion limit |

## Shell 执行

| 环境变量 | 默认值 | 说明 |
|---|---:|---|
| `HARNESS_SHELL_ALLOWLIST` | 空 | 逗号分隔的可执行文件名或绝对路径。不在 allowlist 中的程序拒绝执行 |
| `HARNESS_SHELL_TIMEOUT_SECONDS` | `300` | 默认命令超时，不得超过最大超时 |
| `HARNESS_SHELL_MAX_TIMEOUT_SECONDS` | `600` | 请求可设置的最大命令超时 |
| `HARNESS_SHELL_MAX_OUTPUT_BYTES` | `1048576` | 合并 stdout/stderr 的首尾字节窗口(1 MiB) |
| `HARNESS_MAX_CONCURRENT_SHELLS` | `4` | 单实例活动 Shell 上限 |
| `HARNESS_SHELL_QUEUE_TIMEOUT_SECONDS` | `1` | 等待 Shell 容量的上限(秒),超时返回失败 |
| `HARNESS_SHELL_KILL_GRACE_SECONDS` | `2` | 超时后强制终止前的宽限时间 |
| `HARNESS_SHELL_ENV_ALLOWLIST` | 见下 | 子进程可继承的环境变量名;`HARNESS_*` 与常见 secret 始终剔除 |

默认环境白名单(Windows 取向):`PATH`、`SYSTEMROOT`、`WINDIR`、`COMSPEC`、`PATHEXT`、`TEMP`、`TMP`。Linux/macOS 下按需追加，例如 `HARNESS_SHELL_ENV_ALLOWLIST=PATH,HOME,TEMP,TMP,SYSTEMROOT,LANG`。

## 请求与文件边界

| 环境变量 | 默认值 | 说明 |
|---|---:|---|
| `HARNESS_MAX_BODY_BYTES` | `4194304` | API 请求体上限(4 MiB) |
| `HARNESS_MAX_FILE_BYTES` | `2097152` | 单文本文件读写上限(2 MiB),skills 文件同样受约束 |
| `HARNESS_MAX_SEARCH_RESULTS` | `1000` | 单次 glob/grep/list 的结果上限 |
| `HARNESS_ENABLE_DIRECT_TOOLS` | `true` | 是否暴露直接文件/Shell 路由。只想要 Agent 接口时可设为 `false` |

## 完整 .env 示例

```dotenv
HARNESS_WORKSPACES={"project":"F:/work/demo"}
HARNESS_MODEL=your-model-id
HARNESS_MODEL_API_KEY=your-provider-key
HARNESS_MODEL_BASE_URL=https://api.openai.com/v1
HARNESS_MODEL_ADAPTER=http

HARNESS_SKILLS_DIRS=F:/shared/skills,F:/work/demo/skills

HARNESS_HOST=127.0.0.1
HARNESS_PORT=8000

HARNESS_MODEL_TIMEOUT_SECONDS=600
HARNESS_MODEL_MAX_RETRIES=3
HARNESS_AGENT_TIMEOUT_SECONDS=600
HARNESS_AGENT_MAX_STEPS=50

HARNESS_SHELL_ALLOWLIST=python.exe,pytest.exe,git.exe
HARNESS_SHELL_TIMEOUT_SECONDS=300
HARNESS_SHELL_MAX_TIMEOUT_SECONDS=600
HARNESS_SHELL_MAX_OUTPUT_BYTES=1048576
HARNESS_MAX_CONCURRENT_SHELLS=4
HARNESS_SHELL_QUEUE_TIMEOUT_SECONDS=1
HARNESS_SHELL_KILL_GRACE_SECONDS=2

HARNESS_MAX_BODY_BYTES=4194304
HARNESS_MAX_FILE_BYTES=2097152
HARNESS_MAX_SEARCH_RESULTS=1000
HARNESS_ENABLE_DIRECT_TOOLS=true
```

## 校验规则速记

启动时报错基本都是这几类：

- `Missing required environment variables` — 必填项缺失
- `HARNESS_WORKSPACES must be ...` — workspaces 不是非空 JSON 对象 / 路径不存在 / ID 非法
- `host must be a loopback address` — 监听地址不是回环地址
- `Skills directory does not exist: ...` — skills 目录不存在
- `Workspace '...' is not an existing directory` — workspace 目录不存在
- `shell_timeout_seconds must not exceed ...` — 超时配置矛盾
- `X must be an integer / a number / a boolean / positive` — 数值配置非法
