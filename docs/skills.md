# Skills 使用

Cgent 在创建 Agent 时把宿主机 skills 目录装载进 DeepAgents 的 skills middleware。Agent 会在系统 prompt 中看到 skills 的名称与描述，按需读取对应 `SKILL.md` 及辅助文件。

## 配置 skills 目录

通过 `HARNESS_SKILLS_DIRS` 指定一个或多个宿主机目录(逗号分隔):

```dotenv
HARNESS_SKILLS_DIRS=F:/shared/skills
```

多个目录:

```dotenv
HARNESS_SKILLS_DIRS=F:/shared/skills,F:/project/skills
```

规则：

- 目录在启动时必须存在，否则服务拒绝启动。
- 目录按从左到右顺序加载；不同目录存在同名 skill 时，**后面的目录覆盖前面的目录**。
- skills 在启动时读入内存，映射为 Agent 内部的只读虚拟文件(挂在 `/.cgent-skills/<n>/` 下):
  - 不会出现在 workspace 文件列表中;
  - Agent 的文件工具不能修改或删除;
  - 单个文件超过 `HARNESS_MAX_FILE_BYTES` 或文件总数超过 `HARNESS_MAX_SEARCH_RESULTS` 时启动失败;
  - 非 UTF-8 文本文件(如二进制资产)不会被挂载。
- **修改 skills 内容后需要重启服务**才会生效。

## 目录结构

每个 skill 是 skills 根目录下的一个子目录，必须包含 `SKILL.md`:

```text
skills/
└── demo-skill/
    ├── SKILL.md           # 必需
    └── helper.py          # 可选,SKILL.md 里可指导 Agent 读取/使用
```

## 编写 SKILL.md

`SKILL.md` 需要包含 Agent Skills 元数据 frontmatter:

```markdown
---
name: demo-skill
description: Describe when and how to use this skill
---

# Demo Skill

具体的执行说明。写清楚:
- 这个 skill 解决什么问题;
- 按什么步骤执行;
- 需要读取哪些辅助文件(相对本 skill 目录的路径)。
```

要点:

- `name` 应与目录名一致。
- `description` 决定 Agent 何时选择该 skill，要具体、可判断，例如 "Use when the user asks to generate a weekly report from CSV files"。
- 正文是执行说明。建议引用辅助文件时使用 skill 目录内相对路径，Agent 会按需读取。

## 一个完整示例

目录：

```text
F:/shared/skills/
└── weekly-report/
    ├── SKILL.md
    └── template.md
```

`SKILL.md`:

```markdown
---
name: weekly-report
description: Use when the user asks to generate a weekly report from notes in the workspace
---

# Weekly Report

1. 阅读工作区内本周的 notes/*.md。
2. 按 template.md 的结构汇总成周报草稿。
3. 写入 workspace 的 reports/weekly.md,然后向用户总结要点。
```

`.env`:

```dotenv
HARNESS_SKILLS_DIRS=F:/shared/skills
```

调用时只需自然语言提及:

```bash
curl http://127.0.0.1:8000/v1/agent/invocations \
  -H 'X-Workspace-ID: project' \
  -H 'Content-Type: application/json' \
  -d '{"input":"根据本周 notes 生成周报"}'
```

Agent 会识别 `weekly-report` skill 适用，按需读取 `SKILL.md` 和 `template.md` 执行。

## 多目录覆盖示例

```dotenv
HARNESS_SKILLS_DIRS=F:/shared/skills,F:/project/skills
```

`F:/shared/skills/review/` 和 `F:/project/skills/review/` 同名时，以 `F:/project/skills/review/` 为准。适合"团队公共 skills + 项目私有覆盖"的场景。

## 与其他挂载方式的关系

当前仅支持宿主机目录这一种默认方式。其他可行方式(workspace 内固定 `/skills/`、应用包内置 skills、REST 按 invocation 选择、远程 registry)尚未实现，需要时另行评审设计。
