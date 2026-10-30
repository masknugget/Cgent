# 运维与排障

## 日志

- 结构化 JSON 日志，按 `X-Request-ID` 关联一次请求的处理过程。
- 日志**不记录**请求正文、命令正文或文件正文。
- 排障时先用响应里的 `request_id` 在日志中定位对应请求。

## 启动失败

启动即退出说明配置校验失败，常见报错与处理:

| 报错 | 原因与处理 |
|---|---|
| `Missing required environment variables: ...` | 补齐 `.env` 中的必填项 |
| `HARNESS_WORKSPACES must be a non-empty JSON object` | JSON 格式错误；Windows 路径建议正斜杠 `F:/path` |
| `Invalid workspace ID: ...` | ID 只能以字母数字开头，含字母数字、`-`、`_`,最长 64 字符 |
| `Workspace '...' is not an existing directory` | 创建该目录或修正路径 |
| `Skills directory does not exist: ...` | 创建 skills 目录或从 `HARNESS_SKILLS_DIRS` 移除 |
| `Skill file exceeds the configured size limit` | 精简该 skill 文件，或调大 `HARNESS_MAX_FILE_BYTES` |
| `host must be a loopback address` | `HARNESS_HOST` 只能是 `127.0.0.1`/`localhost`/`::1` |
| `model_adapter must be http or openai` | 修正 `HARNESS_MODEL_ADAPTER` |
| `X must be an integer / a number / a boolean / positive` | 修正对应数值配置 |
| `shell_timeout_seconds must not exceed shell_max_timeout_seconds` | 调整两个超时配置 |

## 请求级错误

| HTTP | code | 场景 |
|---|---|---|
| 400 | `path_outside_workspace` 等 | 虚拟路径非法、超出 workspace、PATCH 字符串不唯一等输入错误 |
| 404 | `workspace_not_found` 等 | `X-Workspace-ID` 未预配置，或路径不存在 |
| 413 | `body_too_large` | 请求体超过 `HARNESS_MAX_BODY_BYTES` |
| 429 | `shell_queue_timeout` 等 | Shell 并发达到 `HARNESS_MAX_CONCURRENT_SHELLS` 且排队超时 |
| 500/502/504 | 视 Provider 而定 | 模型调用失败或整体 invocation 超时 |

## 行为约定备忘

- **Shell 不是 shell**:`execute` 直接启动 allowlist 可执行文件；管道、重定向、shell 内建不可用。报错 `program_not_allowlisted` 类错误时，把程序加入 `HARNESS_SHELL_ALLOWLIST` 并重启。
- **非零退出码不是 HTTP 错误**:`status="failed"` + `exit_code`,调用方自行判断。
- **副作用不回滚**:文件写入和进程执行有真实副作用；invocation 超时不会撤销已完成的修改。
- **Agent 看不到 skills 虚拟路径之外的宿主机路径**;skills 只读，修改需重启服务。

## 安全部署建议

Cgent 是**仅面向本机**的无认证受控执行器，不是多租户 Sandbox:

1. 只监听 loopback(启动强制),不要反向代理到局域网/公网。
2. 使用专用低权限 OS 用户运行，只授予 workspace 目录写权限；不要以 root/Administrator 运行。
3. 按需收窄 `HARNESS_SHELL_ALLOWLIST` 与 `HARNESS_SHELL_ENV_ALLOWLIST`。
4. 模型 key 只存在于 `HARNESS_MODEL_API_KEY`,不进子进程环境、不进日志。
5. 单进程内存态设计，不支持多 worker/多副本水平扩容；需要更高吞吐时按多实例整体重新设计。

## 开发自检

```bash
ruff check cgent tests
ruff format --check cgent tests
ty check
pytest
```

默认测试不访问真实模型或外部服务;E2E 测试使用 fake chat model 驱动真实 DeepAgents 工具循环。
