# Cgent 使用文档

Cgent 是一个独立、单进程的 Python REST Agent Harness：在 FastAPI 进程内运行 DeepAgents，通过同一个受控执行层向 REST 调用方和 Agent 提供 workspace 文件工具与本地程序执行能力。

## 文档导航

| 文档 | 内容 |
|---|---|
| [快速开始](quickstart.md) | 环境准备、配置、启动与第一个调用 |
| [配置参考](configuration.md) | 全部环境变量、校验规则与配置示例 |
| [Skills 使用](skills.md) | 编写 SKILL.md、挂载宿主机 skills 目录、覆盖规则 |
| [REST API](api.md) | 端点、请求/响应结构、curl 示例与错误码 |
| [运维与排障](troubleshooting.md) | 日志、常见错误、安全部署建议 |

## 一分钟概览

```bash
# 1. 安装依赖(Python 3.13/3.14)
python -m venv .venv
.venv\Scripts\Activate.ps1          # Windows PowerShell
pip install -r requirements-dev.txt

# 2. 配置
Copy-Item .env.example .env         # 然后编辑 .env

# 3. 启动
python -m cgent

# 4. 调用
curl http://127.0.0.1:8000/v1/agent/invocations \
  -H 'X-Workspace-ID: project' \
  -H 'Content-Type: application/json' \
  -d '{"input":"阅读项目并修复一个聚焦问题，运行相关验证"}'
```

关键特征：

- **同步调用**:Agent invocation 是一个同步 HTTP 请求，没有数据库、没有持久 thread、没有异步 run 轮询。
- **受控执行**:文件访问限定在预配置 workspace 根目录内;程序执行只允许启动时固定的 allowlist 可执行文件。
- **本机专用**:无认证、强制 loopback 监听，不得暴露到局域网或公网。
- **Skills**:支持挂载宿主机 skills 目录，Agent 按 `SKILL.md` 元数据按需读取。
