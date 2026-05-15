<div align="center">

# ⚡ Gangge Code

**本地 AI 编程助手 — 自主规划、调用工具、逐步完成复杂任务**

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-blue?logo=python" />
  <img src="https://img.shields.io/badge/license-MIT-green" />
  <img src="https://img.shields.io/badge/LLM-DeepSeek%20%7C%20Claude%20%7C%20OpenAI%20%7C%20Ollama-orange" />
  <img src="https://img.shields.io/github/stars/ydsgangge-ux/gangge-code?style=social" />
</p>

**CLI 终端 · 桌面 GUI · 交互式 REPL**

> 输入一句话，AI 自动规划模块、逐文件构建、跑测试验证、提交 Git — 全程可见，随时可控。

<!-- 📸 建议在这里放一张 demo GIF，录制：gangge "创建一个 FastAPI 用户管理系统" 的完整执行过程 -->
<!-- ![demo](assets/demo.gif) -->

</div>

---

## ✨ 和其他 AI 编程工具有什么不同？

| | Gangge Code | ChatGPT / Copilot | Claude Code |
|--|--|--|--|
| 自主调用工具 | ✅ | ❌ 只输出代码 | ✅ |
| 本地完全运行 | ✅ | ❌ | ❌ 需订阅 |
| DeepSeek 原生支持 | ✅ 成本低 10x | ❌ | ❌ |
| 桌面 GUI | ✅ PyQt6 | ❌ | ❌ |
| Memory Bank 跨会话 | ✅ | ❌ | ✅ |
| 批量任务队列 | ✅ | ❌ | ❌ |
| MCP 外部工具接入 | ✅ | ❌ | ✅ |
| 完全开源可改 | ✅ | ❌ | ❌ |

---

## 🎬 快速上手

```bash
# 安装
pip install -e ".[dev]"

# 配置 .env
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxx

# 立刻开始
gangge "创建一个带用户认证的 FastAPI 项目"
```

执行后 AI 会自动输出规划 → 创建任务清单 → 逐步写文件 → 跑测试验证，**全程可见进度**：

```
📋 任务分析
技术栈：FastAPI + SQLAlchemy + SQLite

✅ 任务清单 (0/6)
1. [ ] 创建项目结构 — app/, routes/, models/
2. [ ] 数据模型层   — models/user.py
3. [ ] 认证模块     — routes/auth.py
...

▶ 开始执行第 1 步
  ▶ bash(mkdir -p app/routes app/models)
  ✓ write_file: 已写入 app/models/user.py (42 行)
✅ 1/6 已完成
```

---

## 🛠️ 核心功能

### Agent 引擎
- **30 轮 Plan & Execute 循环** — 分析 → 调工具 → 看结果 → 继续，直到完成
- **首轮必出规划** — 模块清单 + 任务步骤 + 文件结构，让你知道 AI 要做什么
- **测试验证保障** — 文件写完自动运行 pytest，失败自动修复
- **历史压缩** — 每 5 轮自动压缩旧对话，节省 token

### 8 个编程工具
`bash` · `read_file` · `write_file` · `edit_file` · `grep` · `glob` · `list_dir` · `web_fetch`

### 项目管理
- **Memory Bank** — `.gangge/` 目录跨会话记录项目进度，续接任务不丢上下文
- **会话持久化** — SQLite 存储，随时恢复历史会话
- **文件变更 Diff** — 每次修改自动生成 unified diff，绿色新增 / 红色删除
- **Git 自动提交** — 任务完成自动 `git add + commit`
- **项目文件索引** — 自动扫描 .py 文件提取类/函数名注入上下文

### 三种使用形态

| 形态 | 命令 | 适合场景 |
|------|------|---------|
| **单次执行** | `gangge "任务描述"` | 快速任务，CI/CD |
| **管道模式** | `cat error.log \| gangge "分析"` | 日志分析，Shell 脚本 |
| **交互 REPL** | `gangge` | 多轮对话，持续开发 |
| **桌面 GUI** | `python desktop/app.py` | 完整项目开发，文件 Diff 查看 |

### 桌面 GUI 专属功能
- IDE 风格布局（会话列表 · 对话区 · 工具调用记录 · Diff 面板）
- **批量任务队列** — 多行输入，依次自动执行
- **计划确认** — 规划模式下先出方案，你批准后再执行
- 配置持久化（Provider / API Key / 高级参数）

### 可扩展性
- **`.ganggerules`** — 项目根目录定义编码规范、测试要求、架构约定，跟着项目走
- **MCP 协议支持** — 接入任意 MCP Server（AutoCAD、FreeCAD、数据库、浏览器...）

---

## 📐 架构

```
用户界面层
  CLI gangge "任务"  ──┐
  管道 cat x | gangge ─┤
  REPL gangge         ─┤──► AgenticLoop（核心引擎）
  TUI terminal.py     ─┤       │
  GUI desktop/app.py  ─┘       ├─ 工具执行层
                               │    bash · file_ops · search · web
                               ├─ 会话管理层（SQLite）
                               │    持久化 · Memory Bank · 压缩
                               ├─ 权限安全层
                               └─ LLM 适配层
                                    DeepSeek · OpenAI · Claude · Ollama
```

---

## ⚙️ 配置

**`.env` 环境变量**

```ini
LLM_PROVIDER=deepseek          # deepseek / openai / anthropic / ollama
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_MODEL=deepseek-chat

MAX_ROUNDS=30                  # 最大工具调用轮数
MAX_TOKENS=8192
TEMPERATURE=0.0
```

**`.ganggerules` 项目规则**（放项目根目录）

```markdown
# 编码规范
- 所有注释用中文
- 每个新函数必须写 pytest 测试
- 数据库操作只在 repositories/ 目录
```

---

## 📁 项目结构

```
gangge-code/
├── desktop/
│   ├── app.py              # PyQt6 桌面主程序
│   ├── run.bat             # Windows 启动
│   └── run.ps1             # PowerShell 启动
└── src/gangge/
    ├── cli.py              # CLI 入口（路由到各模式）
    ├── cli_repl.py         # 交互式 REPL
    ├── layer2_session/     # 会话管理（SQLite + Memory Bank）
    ├── layer3_agent/       # 核心引擎
    │   ├── loop.py         #   Agentic Loop
    │   ├── planner.py      #   Plan & Execute 规划器
    │   ├── prompts/        #   System Prompt
    │   └── tools/          #   8 个工具
    ├── layer4_permission/  # 权限安全
    └── layer5_llm/         # LLM 适配（4 种 provider）
```

---

## 🗺️ Roadmap

- [x] CLI / REPL / TUI / PyQt6 桌面端
- [x] Memory Bank 跨会话上下文
- [x] 文件变更 Diff 面板
- [x] 批量任务队列
- [x] MCP 协议客户端
- [ ] Shadow Git 检查点（每步可回滚）
- [ ] Textual TUI 完善
- [ ] Web UI（远程访问）

---

## 🤝 Contributing

欢迎 PR 和 Issue！

如果觉得有用，请点个 ⭐ — 这对项目帮助很大。

---

## 📜 License

MIT © [ydsgangge-ux](https://github.com/ydsgangge-ux)
