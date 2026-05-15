<div align="center">

# ⚡ Gangge Code

**Local AI Coding Assistant — Plan, Execute, Verify, All on Your Machine**

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11+-blue?logo=python" />
  <img src="https://img.shields.io/badge/license-MIT-green" />
  <img src="https://img.shields.io/badge/LLM-DeepSeek%20%7C%20Claude%20%7C%20OpenAI%20%7C%20Ollama-orange" />
</p>

**CLI · TUI · Desktop GUI · Interactive REPL**

English | [中文](./README.md)

> Type a sentence, and the AI automatically plans modules, builds files one by one, runs tests, and commits to Git — fully visible, always controllable.

</div>

---

## ✨ Highlights

| | Gangge Code | ChatGPT / Copilot | Claude Code |
|--|--|--|--|
| Autonomous tool use | ✅ | ❌ Code only | ✅ |
| Runs 100% locally | ✅ | ❌ | ❌ Subscription |
| DeepSeek native | ✅ 10x cheaper | ❌ | ❌ |
| Desktop GUI | ✅ PyQt6 | ❌ | ❌ |
| Shadow Git rollback | ✅ | ❌ | ✅ |
| Memory Bank | ✅ | ❌ | ✅ |
| LSP syntax check | ✅ | ❌ | ❌ |
| Batch task queue | ✅ | ❌ | ❌ |
| MCP integration | ✅ | ❌ | ✅ |
| Fully open source | ✅ | ❌ | ❌ |

---

## 🚀 Quick Start

### 1. Clone

```bash
git clone https://github.com/ydsgangge-ux/gangge-code.git
cd gangge-code
```

### 2. Install (pick one)

```bash
# Option A: Minimal (CLI + TUI)
pip install -e .

# Option B: With Desktop GUI
pip install -e ".[gui]"

# Option C: Everything (GUI + dev tools)
pip install -e ".[all]"
```

### 3. Configure API Key

```bash
cp .env.example .env
# Edit .env with your API key
```

Minimal config (DeepSeek):
```ini
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-xxx
```

### 4. Run

```bash
# One-shot task
gangge "Create a FastAPI project with user authentication"

# Interactive REPL
gangge

# Desktop GUI (requires [gui] install)
python desktop/app.py
# Or on Windows: double-click desktop/run.bat
```

---

## 🎬 Demo

<p align="center">
  <img src="docs/screenshots/1.png" alt="Gangge Code Desktop GUI" width="90%" />
  <br/>
  <em>Desktop GUI — Session management, code output, file preview</em>
</p>

<p align="center">
  <img src="docs/screenshots/2.png" alt="Gangge Code Task Execution" width="90%" />
  <br/>
  <em>AI automatically plans, executes, and verifies — fully visible</em>
</p>

```
📋 Task Analysis
Tech stack: FastAPI + SQLAlchemy + SQLite

✅ Task List (0/6)
1. [ ] Project structure — app/, routes/, models/
2. [ ] Data models     — models/user.py
3. [ ] Auth module     — routes/auth.py
...

▶ Executing step 1
  ▶ bash(mkdir -p app/routes app/models)
  ✓ write_file: wrote app/models/user.py (42 lines)
✅ 1/6 done
```

---

## 🛠️ Features

### Agent Engine
- **30-round Plan & Execute loop** — Analyze → Call tools → Review → Continue
- **Plan on first round** — Module list + task steps + file structure
- **ask_user pause** — AI pauses to ask questions, resumes after your answer
- **Test verification** — Auto-runs pytest after file changes, auto-fixes failures
- **Context management** — Sliding window + tool result truncation + lazy file index

### 9 Coding Tools
`bash` · `read_file` · `write_file` · `edit_file` · `grep` · `glob` · `list_dir` · `web_fetch` · `ask_user`

### Safety & Rollback
- **Shadow Git Checkpoint** — Auto-creates Git checkpoint before AI modifications, one-click rollback
- **LSP Syntax Check** — Auto-runs pyright/ruff after code changes, fixes errors immediately
- **Permission Control** — Rule engine + danger detection, system directory writes blocked
- **Critic Self-Check** — Built-in self-check in System Prompt (syntax / logic / deps / style)

### Project Management
- **Memory Bank** — `.gangge/` directory stores project progress + decision log across sessions
- **Decision Log** — Records "why", not just "what", preventing AI from repeating mistakes
- **Session Persistence** — SQLite storage, resume any past session
- **File Change Diff** — Auto-generates unified diff for every modification

### Four Usage Modes

| Mode | Command | Best For |
|------|---------|----------|
| **One-shot** | `gangge "task"` | Quick tasks, CI/CD |
| **Pipe** | `cat error.log \| gangge "analyze"` | Log analysis, shell scripts |
| **REPL** | `gangge` | Multi-turn, ongoing development |
| **Desktop GUI** | `python desktop/app.py` | Full project dev, diff viewing |

### Desktop GUI Features
- **VSCode-style 3-panel layout** — Left (sessions+files) | Center (chat+input) | Right (preview+tools)
- **Standalone file preview** — Click files to preview in right panel, keeps chat clean
- **Stop button** — Red stop button appears during execution, cancel anytime
- **Batch task queue** — Multi-line input, executes sequentially
- **Plan confirmation** — Review AI's plan before it executes
- **Diff rollback** — View diffs and roll back to pre-modification state

### Extensibility
- **`.ganggerules`** — Define coding standards, test requirements, architecture conventions per project
- **MCP Protocol** — Connect any MCP Server (AutoCAD, FreeCAD, databases, browsers...)

---

## 📐 Architecture

```
UI Layer (Layer 1)
  CLI gangge "task"   ──┐
  Pipe cat x | gangge ──┤
  REPL gangge          ─┤──► AgenticLoop (Core Engine, Layer 3)
  TUI terminal.py      ─┤       │
  GUI desktop/app.py   ─┘       ├─ Tool Layer (Layer 3 tools)
                                │    bash · file_ops · search · web · ask_user
                                ├─ Session Layer (Layer 2)
                                │    Persistence · Memory Bank · Compression
                                ├─ Permission Layer (Layer 4)
                                │    Rules · Danger Detection · Shadow Git
                                └─ LLM Layer (Layer 5)
                                     DeepSeek · OpenAI · Claude · Ollama
```

---

## ⚙️ Configuration

**`.env` Environment Variables**

```ini
LLM_PROVIDER=deepseek          # deepseek / openai / anthropic / ollama
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_MODEL=deepseek-chat

MAX_ROUNDS=30                  # Max tool-call rounds
MAX_TOKENS=8192
TEMPERATURE=0.0
```

**`.ganggerules` Project Rules** (place in project root)

```markdown
# Coding Standards
- All comments in English
- Every new function must have a pytest test
- Database operations only in repositories/ directory
```

---

## 📁 Project Structure

```
gangge-code/
├── desktop/
│   ├── app.py              # PyQt6 desktop application
│   ├── run.bat             # Windows one-click launcher
│   └── run.ps1             # PowerShell launcher
├── src/gangge/
│   ├── cli.py              # CLI entry point
│   ├── cli_repl.py         # Interactive REPL
│   ├── layer1_ui/          # TUI interface
│   ├── layer2_session/     # Session management (SQLite + Memory Bank)
│   ├── layer3_agent/       # Core engine
│   │   ├── loop.py         #   Agentic Loop
│   │   ├── planner.py      #   Plan & Execute planner
│   │   ├── prompts/        #   System Prompt
│   │   └── tools/          #   9 tools + lint_check
│   ├── layer4_permission/  # Permission & safety
│   ├── layer4_tools/       # Shadow Git + MCP Client
│   └── layer5_llm/         # LLM adapters (4 providers)
├── tests/
│   └── test_core.py        # Core module tests (14 cases)
├── .env.example            # Environment variable template
├── pyproject.toml          # Project configuration
└── requirements.txt        # Dependency list
```

---

## 🧪 Testing

```bash
# Run all core tests
pytest tests/test_core.py -v

# Only AgenticLoop tests
pytest tests/test_core.py -v -k "test_loop"

# Only Windows compatibility tests
pytest tests/test_core.py -v -k "Windows"

# Only message chain integrity tests
pytest tests/test_core.py -v -k "TestMessageChain"

# With coverage
pytest tests/test_core.py --cov=src/gangge --cov-report=term-missing
```

---

## 🗺️ Roadmap

- [x] CLI / REPL / TUI / PyQt6 Desktop
- [x] Memory Bank cross-session context + Decision Log
- [x] Shadow Git checkpoints (rollback at any step)
- [x] LSP syntax check (pyright/ruff/pylint)
- [x] ask_user pause for user input
- [x] Context management (sliding window + truncation + lazy loading)
- [x] VSCode-style desktop GUI (3-panel layout + file preview + stop button)
- [x] Core module test coverage
- [ ] Internationalization (i18n) English language pack
- [ ] Web UI (remote access)
- [ ] Vector index (RAG) for local context

---

## 🤝 Contributing

PRs and Issues are welcome!

If you find this useful, please give it a ⭐ — it helps a lot.

---

## 📜 License

MIT © [ydsgangge-ux](https://github.com/ydsgangge-ux)
