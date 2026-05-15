"""
Gangge Code Desktop — PyQt6 GUI for the AI Coding Assistant.

Features:
  - 4 LLM providers (DeepSeek, OpenAI, Anthropic, Ollama)
  - Streaming output with syntax highlighting
  - Session persistence (SQLite — save/resume conversations)
  - File diff panel (see exactly what changed)
  - Project context auto-injection (ARCH.md + directory structure)
  - Test verification (auto-prompt after file modifications)
  - Batch task queue (multi-line input, sequential execution)
  - Plan confirmation dialog (approve/reject LLM's plan)
  - File browser with click-to-preview
"""

import asyncio
import difflib
import json
import logging
import os
import sqlite3
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QSettings, QSize, Qt, QThread, pyqtSignal
from PyQt6.QtGui import (
    QAction,
    QColor,
    QFont,
    QKeySequence,
    QSyntaxHighlighter,
    QTextCharFormat,
    QTextCursor,
)
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtGui import QShortcut

# ── Fix import path ──────────────────────────────────────────────
_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from gangge.layer3_agent.loop import AgenticLoop, LoopConfig, ToolExecution
from gangge.layer3_agent.prompts.system import build_system_prompt
from gangge.layer3_agent.tools.registry import ToolRegistry
from gangge.layer5_llm.base import (
    BaseLLM,
    ContentBlock,
    ContentType,
    Message,
    Role,
)
from gangge.layer5_llm.registry import create_llm
from gangge.layer4_permission.guard import PermissionDecision, PermissionGuard, PermissionRequest

# ── LLM Provider definitions ─────────────────────────────────────
PROVIDER_CONFIGS: dict[str, dict[str, Any]] = {
    "deepseek": {
        "label": "DeepSeek",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model_default": "deepseek-chat",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "base_url_editable": True,
        "base_url_default": "https://api.deepseek.com/v1",
    },
    "openai": {
        "label": "OpenAI",
        "api_key_env": "OPENAI_API_KEY",
        "model_default": "gpt-4o",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "base_url_editable": False,
        "base_url_default": "https://api.openai.com/v1",
    },
    "anthropic": {
        "label": "Anthropic Claude",
        "api_key_env": "ANTHROPIC_API_KEY",
        "model_default": "claude-sonnet-4-20250514",
        "models": [
            "claude-sonnet-4-20250514",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
        ],
        "base_url_editable": False,
        "base_url_default": "",
    },
    "ollama": {
        "label": "Ollama (本地)",
        "api_key_env": "OLLAMA_API_KEY",
        "model_default": "llama3.1",
        "models": ["llama3.1", "llama3", "mistral", "qwen2.5", "codellama", "deepseek-coder"],
        "base_url_editable": True,
        "base_url_default": "http://localhost:11434/v1",
    },
}

DARK_STYLESHEET = """
QMainWindow,QDialog,QWidget{background-color:#0d1117;color:#c9d1d9;font-family:"Segoe UI","Microsoft YaHei UI",sans-serif;font-size:13px}
QLabel{color:#c9d1d9;background:transparent;border:none}
QLabel[heading="true"]{color:#58a6ff;font-size:15px;font-weight:bold;padding:4px 0}
QGroupBox{border:1px solid #30363d;border-radius:8px;margin-top:14px;padding:16px 12px 12px;font-weight:600;color:#8b949e}
QGroupBox::title{subcontrol-origin:margin;left:14px;padding:0 6px;color:#58a6ff}
QPushButton{background-color:#238636;color:#fff;border:1px solid rgba(240,246,252,0.1);border-radius:6px;padding:6px 16px;font-size:13px;font-weight:500;min-height:28px}
QPushButton:hover{background-color:#2ea043}
QPushButton:disabled{background-color:#21262d;color:#484f58;border-color:#30363d}
QPushButton[primary="true"]{background-color:#1f6feb}
QPushButton[primary="true"]:hover{background-color:#388bfd}
QPushButton[danger="true"]{background-color:#da3633}
QPushButton[danger="true"]:hover{background-color:#f85149}
QLineEdit,QSpinBox,QPlainTextEdit,QTextEdit,QTextBrowser,QComboBox{background-color:#161b22;color:#c9d1d9;border:1px solid #30363d;border-radius:6px;padding:6px 10px;selection-background-color:#264f78}
QLineEdit:focus,QComboBox:focus,QPlainTextEdit:focus{border-color:#58a6ff}
QComboBox::drop-down{border:none;width:24px}
QComboBox::down-arrow{image:none;border-left:5px solid transparent;border-right:5px solid transparent;border-top:6px solid #8b949e;margin-right:6px}
QComboBox QAbstractItemView{background-color:#161b22;color:#c9d1d9;border:1px solid #30363d;selection-background-color:#1f6feb}
QTabWidget::pane{border:1px solid #30363d;border-radius:6px;background:#0d1117}
QTabBar::tab{background:#161b22;color:#8b949e;border:1px solid #30363d;border-bottom:none;border-top-left-radius:6px;border-top-right-radius:6px;padding:8px 18px;margin-right:2px;font-size:12px}
QTabBar::tab:selected{background:#0d1117;color:#f0f6fc;border-bottom:2px solid #f78166}
QTabBar::tab:hover:!selected{background:#21262d;color:#c9d1d9}
QTableWidget{background-color:#0d1117;alternate-background-color:#161b22;border:1px solid #30363d;gridline-color:#21262d}
QTableWidget::item{padding:4px 8px}
QHeaderView::section{background-color:#161b22;color:#8b949e;padding:6px 8px;border:none;border-bottom:1px solid #30363d;font-weight:600;font-size:12px}
QTreeWidget{background-color:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9}
QScrollBar:vertical{background:#0d1117;width:12px;border:none}
QScrollBar::handle:vertical{background:#30363d;border-radius:6px;min-height:30px}
QScrollBar::handle:vertical:hover{background:#484f58}
QProgressBar{background:#161b22;border:1px solid #30363d;border-radius:6px;text-align:center;color:#c9d1d9;height:20px}
QProgressBar::chunk{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #238636,stop:1 #2ea043);border-radius:5px}
QSplitter::handle{background:#21262d;width:2px}
QSplitter::handle:hover{background:#58a6ff}
QCheckBox{color:#c9d1d9;spacing:6px}
QCheckBox::indicator{width:16px;height:16px;border-radius:3px;border:1px solid #30363d;background:#21262d}
QCheckBox::indicator:checked{background:#238636;border-color:#238636}
QStatusBar{background:#161b22;border-top:1px solid #21262d;color:#8b949e;font-size:12px}
QMenuBar{background:#161b22;border-bottom:1px solid #21262d;color:#c9d1d9;padding:2px}
QMenuBar::item:selected{background:#1f6feb}
QMenu{background:#161b22;border:1px solid #30363d;color:#c9d1d9}
QMenu::item:selected{background:#1f6feb}
QListWidget{background-color:#0d1117;border:1px solid #30363d;border-radius:6px;color:#c9d1d9;outline:none}
QListWidget::item{padding:8px 10px;border-bottom:1px solid #21262d}
QListWidget::item:selected{background-color:#1f6feb;color:#fff}
"""


# ═════════════════════════════════════════════════════════════════
# 4. Session: SQLite-backed conversation persistence
# ═════════════════════════════════════════════════════════════════
class SessionDB:
    """SQLite session store — saves/loads conversation history."""

    MAX_LOAD_MESSAGES = 500  # Only load recent N messages to prevent UI freeze

    def __init__(self, db_path: str = ""):
        if not db_path:
            # Try project-local first, fallback to home dir
            local_dir = Path(__file__).resolve().parent.parent / ".gangge_data"
            try:
                local_dir.mkdir(parents=True, exist_ok=True)
                db_path = str(local_dir / "sessions.db")
                # Test write access
                test_path = local_dir / ".write_test"
                test_path.touch()
                test_path.unlink()
            except (OSError, PermissionError):
                # Fallback to home directory
                home_dir = Path.home() / ".gangge"
                home_dir.mkdir(parents=True, exist_ok=True)
                db_path = str(home_dir / "sessions.db")
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def connect(self):
        try:
            self._conn = sqlite3.connect(
                self._db_path,
                check_same_thread=False,  # 允许跨线程访问（Qt 多线程场景）
            )
            self._conn.row_factory = sqlite3.Row

            # ── FIX 1: 性能 PRAGMA ───────────────────────────────
            pragmas = [
                "PRAGMA journal_mode=WAL",          # WAL 模式（已有，保留）
                "PRAGMA synchronous=NORMAL",        # 从 FULL 降为 NORMAL，写入快 3-5x
                "PRAGMA cache_size=-8000",          # 缓存 8MB（默认只有 2MB）
                "PRAGMA temp_store=MEMORY",         # 临时表走内存，不走磁盘
                "PRAGMA mmap_size=268435456",       # 256MB 内存映射 I/O
                "PRAGMA busy_timeout=5000",         # 锁等待超时 5 秒，防止 OperationalError
                "PRAGMA foreign_keys=ON",
            ]
            for pragma in pragmas:
                self._conn.execute(pragma)
            # ────────────────────────────────────────────────────
            self._init_tables()
        except sqlite3.OperationalError as e:
            # Last resort: use a temp file
            import tempfile
            fallback = Path(tempfile.gettempdir()) / "gangge_sessions.db"
            self._db_path = str(fallback)
            self._conn = sqlite3.connect(self._db_path)
            self._conn.execute("PRAGMA journal_mode=DELETE")  # safer mode
            self._init_tables()

    def close(self):
        if self._conn:
            try:
                self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            except Exception:
                pass
            self._conn.close()
            self._conn = None

    def _init_tables(self):
        c = self._conn.cursor()
        c.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '新会话',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                workspace TEXT DEFAULT '',
                provider TEXT DEFAULT '',
                model TEXT DEFAULT '',
                task_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                content_type TEXT NOT NULL DEFAULT 'text',
                tool_use_id TEXT,
                is_error INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS tool_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                round_num INTEGER DEFAULT 0,
                tool_name TEXT NOT NULL,
                tool_input TEXT DEFAULT '',
                tool_output TEXT DEFAULT '',
                is_error INTEGER DEFAULT 0,
                diff TEXT DEFAULT '',
                created_at TEXT NOT NULL
            );
        """)
        self._conn.commit()
        # 如果已有旧库，补全新字段
        self._migrate_if_needed()

    def _migrate_if_needed(self):
        """为旧库补上 content_type / tool_use_id / is_error 字段。"""
        try:
            self._conn.execute(
                "ALTER TABLE messages ADD COLUMN content_type TEXT NOT NULL DEFAULT 'text'"
            )
        except Exception:
            pass  # 字段已存在
        try:
            self._conn.execute(
                "ALTER TABLE messages ADD COLUMN tool_use_id TEXT"
            )
        except Exception:
            pass
        try:
            self._conn.execute(
                "ALTER TABLE messages ADD COLUMN is_error INTEGER NOT NULL DEFAULT 0"
            )
        except Exception:
            pass

    def create_session(self, title: str = "新会话", workspace: str = "") -> str:
        sid = uuid.uuid4().hex[:8]
        now = datetime.now().isoformat()
        self._conn.execute(
            "INSERT INTO sessions (id, title, created_at, updated_at, workspace) VALUES (?,?,?,?,?)",
            (sid, title, now, now, workspace),
        )
        self._conn.commit()
        return sid

    def list_sessions(self, limit: int = 50, workspace: str = "") -> list[dict]:
        """列出会话，可选按 workspace 过滤。"""
        if workspace:
            rows = self._conn.execute(
                "SELECT id, title, created_at, updated_at, workspace, task_count "
                "FROM sessions WHERE workspace=? ORDER BY updated_at DESC LIMIT ?",
                (workspace, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, title, created_at, updated_at, workspace, task_count "
                "FROM sessions ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": r[0],
                "title": r[1],
                "created_at": r[2],
                "updated_at": r[3],
                "workspace": r[4] or "",
                "task_count": r[5] or 0,
            }
            for r in rows
        ]

    def get_session(self, sid: str) -> dict | None:
        r = self._conn.execute(
            "SELECT id, title, created_at, updated_at, workspace, provider, model, task_count FROM sessions WHERE id=?",
            (sid,),
        ).fetchone()
        if not r:
            return None
        return {"id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3],
                "workspace": r[4] or "", "provider": r[5] or "", "model": r[6] or "",
                "task_count": r[7] or 0}

    def update_session(self, sid: str, **kw):
        sets = ", ".join(f"{k}=?" for k in kw)
        vals = list(kw.values()) + [sid]
        self._conn.execute(f"UPDATE sessions SET {sets} WHERE id=?", vals)
        self._conn.commit()

    # ── CHANGE: 方案C — save_turn 替换 save_message ────────────
    def save_turn(self, sid: str, messages: list[dict]):
        """
        保存一轮对话的所有聚合消息。

        messages 格式：
        [
          {"role": "user", "content": "帮我写SaaS"},
          {"role": "assistant", "content": [...]},  # list=含tool_use，str=纯文字
          {"role": "tool", "tool_use_id": "...", "content": "...", "is_error": False},
        ]
        """
        now = datetime.now().isoformat()
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            tool_use_id = msg.get("tool_use_id", None)

            # content 如果是 list（assistant 含 tool_use），序列化为 JSON
            if isinstance(content, list):
                content_str = json.dumps(content, ensure_ascii=False)
                content_type = "json"
            else:
                content_str = str(content)
                content_type = "text"

            is_error = 1 if msg.get("is_error", False) else 0

            self._conn.execute(
                "INSERT INTO messages (session_id, role, content, content_type, tool_use_id, is_error, created_at) VALUES (?,?,?,?,?,?,?)",
                (sid, role, content_str, content_type, tool_use_id, is_error, now),
            )
        self._conn.execute("UPDATE sessions SET updated_at=? WHERE id=?", (now, sid))
        self._conn.commit()

    def count_messages(self, sid: str) -> int:
        """快速查询总消息数（不加载内容），用于 UI 提示"""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM messages WHERE session_id=?", (sid,)
        ).fetchone()
        return row[0] if row else 0

    # ── CHANGE: 方案C — load_turns 替换 load_messages ───────────
    def load_turns(self, sid: str, limit: int = 200) -> list[dict]:
        """
        加载会话消息，重建成 LLM API 标准消息格式。

        返回的消息可直接作为 LLM 的 messages 参数。
        tool 角色的消息显示简短摘要，不展开完整输出。
        limit: 最多加载多少条
        """
        # 取最近 limit 条，按时间正序排列
        rows = self._conn.execute(
            """
            SELECT role, content, content_type, tool_use_id, is_error
            FROM (
                SELECT id, role, content, content_type, tool_use_id, is_error
                FROM messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
            ) ORDER BY id ASC
            """,
            (sid, limit),
        ).fetchall()

        messages = []
        for r in rows:
            role = r["role"]
            content_str = r["content"]
            content_type = r["content_type"]
            tool_use_id = r["tool_use_id"]
            is_error = r["is_error"]

            if content_type == "json":
                content = json.loads(content_str)
            else:
                content = content_str

            msg = {"role": role, "content": content}
            if tool_use_id:
                msg["tool_use_id"] = tool_use_id
                msg["is_error"] = bool(is_error)

            messages.append(msg)

        return messages

    def save_tool_call(self, sid: str, round_num: int, tool_name: str, tool_input: str,
                       tool_output: str, is_error: bool, diff: str = ""):
        self._conn.execute(
            "INSERT INTO tool_calls (session_id, round_num, tool_name, tool_input, tool_output, is_error, diff, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (sid, round_num, tool_name, tool_input, tool_output, 1 if is_error else 0, diff, datetime.now().isoformat()),
        )
        self._conn.commit()

    def load_tool_calls(self, sid: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT round_num, tool_name, tool_input, tool_output, is_error, diff FROM tool_calls WHERE session_id=? ORDER BY id",
            (sid,),
        ).fetchall()
        return [{"round": r[0], "tool_name": r[1], "input": r[2], "output": r[3],
                 "is_error": bool(r[4]), "diff": r[5]} for r in rows]

    def delete_session(self, sid: str):
        self._conn.execute("DELETE FROM tool_calls WHERE session_id=?", (sid,))
        self._conn.execute("DELETE FROM messages WHERE session_id=?", (sid,))
        self._conn.execute("DELETE FROM sessions WHERE id=?", (sid,))
        self._conn.commit()

    def increment_task_count(self, sid: str):
        self._conn.execute("UPDATE sessions SET task_count=task_count+1, updated_at=? WHERE id=?",
                           (datetime.now().isoformat(), sid))
        self._conn.commit()


# ═════════════════════════════════════════════════════════════════
#  Output Syntax Highlighter
# ═════════════════════════════════════════════════════════════════
class OutputHighlighter(QSyntaxHighlighter):
    def __init__(self, parent=None):
        super().__init__(parent)
        fmt1 = QTextCharFormat()
        fmt1.setForeground(QColor("#d29922"))
        fmt1.setFontWeight(QFont.Weight.Bold)
        self._rules = [(r"[⚡✓✗🔧📁📝🌐ℹ⚠❌✅]", fmt1)]

        fmt_err = QTextCharFormat()
        fmt_err.setForeground(QColor("#f85149"))
        self._rules.append((r"错误|失败|Error|ERROR|Failed|Exception|Traceback", fmt_err))

        fmt_ok = QTextCharFormat()
        fmt_ok.setForeground(QColor("#3fb950"))
        self._rules.append((r"成功|完成|OK|Done|Success|✓|全部通过", fmt_ok))

        fmt_path = QTextCharFormat()
        fmt_path.setForeground(QColor("#79c0ff"))
        self._rules.append((r"`[^`]+`", fmt_path))

    def highlightBlock(self, text: str) -> None:
        import re
        for pattern, fmt in self._rules:
            for m in re.finditer(pattern, text):
                self.setFormat(m.start(), m.end() - m.start(), fmt)


# ═════════════════════════════════════════════════════════════════
#  Plan Confirmation Dialog
# ═════════════════════════════════════════════════════════════════
class PlanConfirmDialog(QDialog):
    """Shows LLM's plan and lets user approve/reject/modify."""

    def __init__(self, plan_text: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📋 确认执行计划")
        self.setMinimumSize(600, 400)
        self.approved = False
        self._setup_ui(plan_text)

    def _setup_ui(self, plan_text: str):
        layout = QVBoxLayout(self)

        title = QLabel("📋 LLM 生成的执行计划")
        title.setProperty("heading", True)
        layout.addWidget(title)

        self._plan_view = QTextBrowser()
        self._plan_view.setPlainText(plan_text)
        self._plan_view.setStyleSheet("background: #161b22; padding: 12px; font-family: Consolas, monospace;")
        layout.addWidget(self._plan_view, 1)

        info = QLabel("请检查计划，确认后 LLM 将按此计划执行。如需调整，可修改上方文本。")
        info.setWordWrap(True)
        info.setStyleSheet("color: #8b949e; padding: 4px 0;")
        layout.addWidget(info)

        btn_row = QHBoxLayout()
        self._edit_btn = QPushButton("✏️ 编辑计划")
        self._edit_btn.clicked.connect(self._toggle_edit)
        btn_row.addWidget(self._edit_btn)

        btn_row.addStretch()

        reject_btn = QPushButton("❌ 拒绝")
        reject_btn.setProperty("danger", True)
        reject_btn.clicked.connect(self.reject)
        btn_row.addWidget(reject_btn)

        approve_btn = QPushButton("✅ 批准执行")
        approve_btn.setProperty("primary", True)
        approve_btn.clicked.connect(self.approve)
        btn_row.addWidget(approve_btn)

        layout.addLayout(btn_row)

    def _toggle_edit(self):
        if self._plan_view.isReadOnly():
            self._plan_view.setReadOnly(False)
            self._edit_btn.setText("💾 保存修改")
        else:
            self._plan_view.setReadOnly(True)
            self._edit_btn.setText("✏️ 编辑计划")

    def approve(self):
        self.approved = True
        self.accept()

    def reject(self):
        self.approved = False
        self.accept()

    def get_plan_text(self) -> str:
        return self._plan_view.toPlainText()


# ═════════════════════════════════════════════════════════════════
#  Diff Viewer Widget
# ═════════════════════════════════════════════════════════════════
class DiffViewer(QTextBrowser):
    """Displays unified diffs with green/red highlighting."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet("font-family: 'Consolas','Courier New',monospace; font-size: 12px; background: #0d1117;")

    def show_diff(self, diff_text: str):
        self.clear()
        if not diff_text.strip():
            self.setPlainText("(无变更)")
            return

        html = []
        for line in diff_text.splitlines():
            escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if line.startswith("+"):
                html.append(f'<span style="background:#1b3a1b;color:#3fb950">{escaped}</span>')
            elif line.startswith("-"):
                html.append(f'<span style="background:#3a1b1b;color:#f85149">{escaped}</span>')
            elif line.startswith("@@"):
                html.append(f'<span style="color:#58a6ff;font-weight:bold">{escaped}</span>')
            elif line.startswith("---") or line.startswith("+++"):
                html.append(f'<span style="color:#d29922;font-weight:bold">{escaped}</span>')
            else:
                html.append(f'<span style="color:#8b949e">{escaped}</span>')
        self.setHtml("<pre>" + "<br>".join(html) + "</pre>")


# ═════════════════════════════════════════════════════════════════
#  Async Worker Thread
# ═════════════════════════════════════════════════════════════════
class GanggeWorker(QThread):
    """Runs the AgenticLoop asynchronously in a background thread."""

    text_block = pyqtSignal(str, str)       # (text, role)
    tool_call_sig = pyqtSignal(str, str, bool, str)  # (tool_name, output, is_error, diff)
    finished = pyqtSignal(dict)             # summary
    status = pyqtSignal(str)                # status message
    plan_ready = pyqtSignal(str)            # plan text for confirmation
    # ── CHANGE: 方案C — 每轮聚合消息信号 ──
    turn_complete = pyqtSignal(list)        # list[dict] 聚合后的消息列表

    def __init__(self, llm: BaseLLM, task: str, workspace: str,
                 max_rounds: int = 30, plan_mode: bool = False,
                 project_context: str = "", system_prompt_extra: str = "",
                 auto_allow: bool = True, batch_index: int = 0,
                 batch_total: int = 1,
                 project_map: str = "",
                 file_registry: dict | None = None,
                 ganggerules: str = "",
                 memory_bank_progress: str = "",
                 memory_bank_changelog: str = "",
                 provider: str = "",
                 model_name: str = "",
                 previous_messages: list | None = None):
        super().__init__()
        self.llm = llm
        self.task = task
        self.workspace = workspace
        self.previous_messages = previous_messages or []
        self.max_rounds = max_rounds
        self.plan_mode = plan_mode
        self.project_context = project_context
        self.system_prompt_extra = system_prompt_extra
        self.auto_allow = auto_allow
        self.batch_index = batch_index
        self.batch_total = batch_total
        self.project_map = project_map
        self.file_registry = file_registry or {}
        self.ganggerules = ganggerules
        self.memory_bank_progress = memory_bank_progress
        self.memory_bank_changelog = memory_bank_changelog
        self._provider = provider
        self._model = model_name or getattr(llm, "model", "")
        self._cancel = False
        self._approved_plan = ""

    def cancel(self):
        self._cancel = True

    def set_approved_plan(self, plan: str):
        self._approved_plan = plan

    # ── CHANGE: 方案C — 消息聚合 ──────────────────────────────
    def _aggregate_turn_messages(self, messages: list, start_idx: int = 0) -> list[dict]:
        """
        把 AgenticLoop 产出的标准 Message 列表聚合成 DB 格式。

        按轮次分组：USER → ASSISTANT(含 tool_use+text) → TOOL 结果
        返回符合 LLM API 协议的消息列表。
        """
        from gangge.layer5_llm.base import ContentType
        turn_msgs = []
        new_msgs = messages[start_idx:]  # 只取本轮新增的消息

        i = 0
        while i < len(new_msgs):
            msg = new_msgs[i]
            role = msg.role

            if role.value == "user":
                text = msg.get_text()
                turn_msgs.append({"role": "user", "content": text})

            elif role.value == "assistant":
                content_blocks = msg.content if hasattr(msg, "content") else []
                blocks = []
                for b in content_blocks:
                    if b.type == ContentType.TEXT and b.text.strip():
                        blocks.append({"type": "text", "text": b.text})
                    elif b.type == ContentType.TOOL_USE:
                        blocks.append({
                            "type": "tool_use",
                            "id": getattr(b, "tool_call_id", "") or getattr(b, "id", ""),
                            "name": getattr(b, "tool_name", ""),
                            "input": getattr(b, "tool_input", {}),
                        })
                if blocks:
                    turn_msgs.append({"role": "assistant", "content": blocks})

            elif role.value == "tool":
                for b in msg.content if hasattr(msg, "content") else []:
                    if b.type == ContentType.TOOL_RESULT:
                        turn_msgs.append({
                            "role": "tool",
                            "tool_use_id": getattr(b, "tool_call_id", ""),
                            "content": b.text if hasattr(b, "text") else "",
                            "is_error": False,
                        })

            i += 1

        return turn_msgs
    # ────────────────────────────────────────────────────────────

    def run(self):
        try:
            asyncio.run(self._run_async())
        except Exception as e:
            import traceback
            self.text_block.emit(f"❌ 执行异常: {e}\n{traceback.format_exc()}", "error")
            self.finished.emit({"error": str(e)})

    async def _run_async(self):
        async def ask_callback(req: PermissionRequest) -> PermissionDecision:
            if self.auto_allow and req.risk.level.value in ("safe", "low"):
                return PermissionDecision.ALLOW
            if self._cancel:
                return PermissionDecision.DENY
            return PermissionDecision.ALLOW

        guard = PermissionGuard(ask_callback=ask_callback)

        from gangge.layer3_agent.tools.bash import BashTool
        from gangge.layer3_agent.tools.file_ops import ReadFileTool, WriteFileTool, EditFileTool
        from gangge.layer3_agent.tools.search import GrepTool, GlobTool, ListDirTool
        from gangge.layer3_agent.tools.web import WebFetchTool

        registry = ToolRegistry()
        # BashTool gets workspace lock so commands run in project dir
        registry.register(BashTool(workspace=self.workspace))
        registry.register(ReadFileTool(workspace=self.workspace))
        registry.register(WriteFileTool(workspace=self.workspace))
        registry.register(EditFileTool(workspace=self.workspace))
        for cls in [GrepTool, GlobTool, ListDirTool, WebFetchTool]:
            registry.register(cls())

        extra = self.system_prompt_extra
        system_text = build_system_prompt(
            workspace_dir=self.workspace,
            project_context=self.project_context,
            plan_mode=self.plan_mode,
        )
        if extra:
            system_text += f"\n\n## 额外指令\n\n{extra}"

        # If plan_mode is on, inject a clear instruction to first generate a plan
        if self.plan_mode:
            system_text += (
                "\n\n## 当前模式: 先计划后执行\n"
                "请先输出一个清晰的执行计划，包含步骤、涉及文件、风险。\n"
                "输出格式:\n"
                "### Plan\n"
                "1. [步骤描述] — 文件: xxx\n"
                "2. [步骤描述] — 文件: xxx\n"
                "...\n"
                "输出完计划后等待用户确认，不要自动执行。\n"
            )

        config = LoopConfig(
            max_tool_rounds=self.max_rounds,
            workspace_dir=self.workspace,
            system_prompt=system_text,
            plan_mode=self.plan_mode,
            project_map=self.project_map,
            file_registry=self.file_registry,
            memory_bank_progress=self.memory_bank_progress,
            memory_bank_changelog=self.memory_bank_changelog,
            ganggerules=self.ganggerules,
        )

        # ── 3. Create loop ──
        loop = AgenticLoop(llm=self.llm, tools=registry, permission_guard=guard, config=config)

        # Streaming callback
        async def stream_cb(block: ContentBlock):
            if self._cancel:
                return
            if block.type == ContentType.TEXT:
                self.text_block.emit(block.text, "assistant")
            elif block.type == ContentType.THINKING:
                self.text_block.emit(f"🤔 {block.text}", "system")
            elif block.type == ContentType.TOOL_USE:
                inp = json.dumps(block.tool_input, ensure_ascii=False)[:200]
                self.text_block.emit(f"\n🔧 调用工具: {block.tool_name}({inp})\n", "tool")

        loop.set_stream_callback(stream_cb)

        # ── 4. Build messages ──
        batch_prefix = f"[{self.batch_index + 1}/{self.batch_total}] " if self.batch_total > 1 else ""
        full_task = f"{batch_prefix}{self.task}"
        # Restore previous session context if any
        messages = list(self.previous_messages)
        messages.append(Message(role=Role.USER, content=full_task))

        self.text_block.emit(f"\n📋 任务: {full_task}\n", "user")
        if self.batch_total > 1:
            self.text_block.emit(f"📌 批处理进度: {self.batch_index + 1}/{self.batch_total}\n", "system")
        self.text_block.emit(f"📁 工作目录: {self.workspace}\n", "system")
        self.text_block.emit("─" * 60 + "\n", "system")

        # If there's a pre-approved plan, inject it after the first LLM response
        plan_injected = False

        # ── 5. Run loop ──
        result = await loop.run(messages)

        # ── CHANGE: 方案C — 聚合消息并发射到主线程 ──────────
        # messages 现在的格式：USER, ASSISTANT(含tool_use+text), TOOL 交替
        # 按 LLM API 协议格式聚合后通过 turn_complete 信号发射
        turn_msgs = self._aggregate_turn_messages(messages, len(self.previous_messages))
        if turn_msgs:
            self.turn_complete.emit(turn_msgs)
        # ─────────────────────────────────────────────────────

        # ── 6. Summary ──
        self.text_block.emit("\n" + "═" * 60 + "\n", "system")

        mb_update = result.extra.get("memory_bank_update", "")
        cost_display = ""
        try:
            from gangge.pricing import estimate_cost
            cost_display = estimate_cost(self._provider, self._model,
                                          result.total_tokens.get("input", 0),
                                          result.total_tokens.get("output", 0))
        except Exception:
            pass
        summary = {
            "rounds": result.total_rounds,
            "tool_calls": len(result.tool_executions),
            "tokens": result.total_tokens,
            "final_response": result.final_response,
            "memory_bank_update": mb_update,
            "cost": cost_display,
        }

        for exc in result.tool_executions:
            diff = exc.metadata.get("diff", "")
            self.tool_call_sig.emit(exc.tool_name, exc.output[:300], exc.is_error, diff)

        inp = result.total_tokens.get("input", 0)
        out = result.total_tokens.get("output", 0)
        cost_part = f" | 费用: {cost_display}" if cost_display else ""
        self.text_block.emit(
            f"\n✅ 完成 ({result.total_rounds} 轮, {len(result.tool_executions)} 次工具调用, "
            f"Token: 输入={inp}, 输出={out}{cost_part})\n",
            "system",
        )
        if result.final_response:
            self.text_block.emit(f"\n{result.final_response}\n", "assistant")

        self.finished.emit(summary)


# ═════════════════════════════════════════════════════════════════
#  File Browser Widget
# ═════════════════════════════════════════════════════════════════
class FileBrowserWidget(QWidget):
    file_selected = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(True)
        self._tree.setIndentation(18)
        self._tree.itemExpanded.connect(self._on_expand)
        self._tree.itemClicked.connect(self._on_click)
        layout.addWidget(self._tree)
        self._root_path = ""

    def set_root(self, path: str):
        self._root_path = path
        self._tree.clear()
        if not path or not os.path.isdir(path):
            return
        root_item = QTreeWidgetItem([os.path.basename(path) or path])
        root_item.setData(0, Qt.ItemDataRole.UserRole, path)
        f = root_item.font(0)
        f.setBold(True)
        root_item.setFont(0, f)
        self._tree.addTopLevelItem(root_item)
        root_item.setExpanded(True)
        self._populate(root_item, path, 0)

    def _populate(self, parent_item, dir_path, depth):
        if depth > 4:
            return
        try:
            entries = sorted(Path(dir_path).iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        except PermissionError:
            return
        hidden = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".idea"}
        for entry in entries:
            if entry.name.startswith(".") and entry.name != ".env":
                continue
            if entry.name in hidden:
                continue
            child = QTreeWidgetItem([entry.name])
            child.setData(0, Qt.ItemDataRole.UserRole, str(entry))
            if entry.is_dir():
                child.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                child.addChild(QTreeWidgetItem(["(loading)"]))
            parent_item.addChild(child)

    def _on_expand(self, item):
        path = item.data(0, Qt.ItemDataRole.UserRole) or ""
        if not path or not os.path.isdir(path):
            return
        if item.childCount() == 1 and item.child(0).text(0) == "(loading)":
            item.removeChild(item.child(0))
        if item.childCount() == 0:
            self._populate(item, path, self._depth(item))

    def _depth(self, item):
        d = 0
        while item.parent():
            d += 1
            item = item.parent()
        return d

    def _on_click(self, item, col):
        path = item.data(0, Qt.ItemDataRole.UserRole) or ""
        if path and os.path.isfile(path):
            self.file_selected.emit(path)


# ═════════════════════════════════════════════════════════════════
#  Tool Call Table + Diff Tab
# ═════════════════════════════════════════════════════════════════
class DiffTabWidget(QWidget):
    """Combined tool call table + diff viewer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Table
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["#", "工具", "状态", "输出"])
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.setColumnWidth(0, 40)
        self._table.setColumnWidth(1, 100)
        self._table.setColumnWidth(2, 60)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        layout.addWidget(self._table)

        # Diff viewer
        diff_label = QLabel("📝 文件变更 (Diff)")
        diff_label.setProperty("heading", True)
        layout.addWidget(diff_label)

        self._diff_viewer = DiffViewer()
        self._diff_viewer.setMinimumHeight(150)
        layout.addWidget(self._diff_viewer)

        self._diffs: list[str] = []

    def add_entry(self, tool_name: str, output: str, is_error: bool, diff: str = ""):
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self._table.setItem(row, 1, QTableWidgetItem(tool_name))
        s = QTableWidgetItem("❌" if is_error else "✅")
        s.setForeground(QColor("#f85149" if is_error else "#3fb950"))
        self._table.setItem(row, 2, s)
        o = QTableWidgetItem(output[:200])
        o.setToolTip(output)
        self._table.setItem(row, 3, o)
        self._diffs.append(diff)
        self._table.scrollToBottom()

    def _on_selection_changed(self):
        rows = self._table.selectionModel().selectedRows()
        if rows:
            idx = rows[0].row()
            if 0 <= idx < len(self._diffs):
                self._diff_viewer.show_diff(self._diffs[idx])
            else:
                self._diff_viewer.clear()
        else:
            self._diff_viewer.clear()

    def clear_entries(self):
        self._table.setRowCount(0)
        self._diffs.clear()
        self._diff_viewer.clear()


# ═════════════════════════════════════════════════════════════════
#  Project Context Scanner
# ═════════════════════════════════════════════════════════════════
def scan_project_context(workspace: str) -> str:
    """Scan workspace for ARCH.md, README.md, .ganggerules, and directory structure."""
    parts = []
    ws = Path(workspace)
    if not ws.is_dir():
        return ""

    # 1. Read ARCH.md if exists
    arch_path = ws / "ARCH.md"
    if arch_path.exists():
        try:
            content = arch_path.read_text(encoding="utf-8", errors="replace")[:3000]
            parts.append(f"## 架构文档 (ARCH.md)\n{content}")
        except Exception:
            pass

    # 2. Read README.md if exists (first 100 lines)
    readme_path = ws / "README.md"
    if readme_path.exists():
        try:
            lines = readme_path.read_text(encoding="utf-8", errors="replace").splitlines()[:100]
            parts.append(f"## 项目说明 (README.md)\n" + "\n".join(lines))
        except Exception:
            pass

    # 3. Read .ganggerules if exists
    rules_path = ws / ".ganggerules"
    if rules_path.exists():
        try:
            content = rules_path.read_text(encoding="utf-8", errors="replace")[:3000]
            parts.append(f"## 项目规则 (.ganggerules)\n{content}")
        except Exception:
            pass

    # 4. Directory structure (top 2 levels)
    try:
        struct_lines = [f"{ws.name}/"]
        exclude = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".idea", ".vscode"}
        entries = sorted(ws.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        for e in entries:
            if e.name.startswith(".") or e.name in exclude:
                continue
            prefix = "├── " if e != entries[-1] else "└── "
            suffix = "/" if e.is_dir() else ""
            struct_lines.append(f"{prefix}{e.name}{suffix}")
            if e.is_dir() and e.name not in exclude:
                try:
                    sub = sorted(e.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))[:10]
                    for s2 in sub:
                        if s2.name.startswith(".") or s2.name in exclude:
                            continue
                        p2 = "│   ├── " if s2 != sub[-1] else "│   └── "
                        s2_suffix = "/" if s2.is_dir() else ""
                        struct_lines.append(f"{p2}{s2.name}{s2_suffix}")
                except Exception:
                    pass
        parts.append("## 目录结构\n" + "\n".join(struct_lines))
    except Exception:
        pass

    return "\n\n".join(parts)


# ═════════════════════════════════════════════════════════════════
#  Project Map Builder — scans workspace for all .py files,
#  extracts class/function names from file headers.
# ═════════════════════════════════════════════════════════════════
def build_project_map(workspace: str, max_entries: int = 80) -> str:
    """Generate a project file index: path + top-level classes/functions."""
    ws = Path(workspace)
    if not ws.is_dir():
        return ""

    lines = []
    exclude_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".idea", ".vscode", ".egg-info"}

    for py_file in sorted(ws.rglob("*.py")):
        if any(p in exclude_dirs for p in py_file.parts):
            continue
        if ".egg-info" in str(py_file):
            continue
        try:
            rel = py_file.relative_to(ws)
            # Read first 20 lines to find declarations
            head = ""
            with open(py_file, encoding="utf-8", errors="replace") as f:
                for _ in range(20):
                    line = f.readline()
                    if not line:
                        break
                    s = line.strip()
                    if s.startswith(("class ", "def ", "async def ")):
                        sig = s.split("(")[0].strip().rstrip(":")
                        head += sig + "; "
            if head:
                lines.append(f"- `{rel}`: {head[:150]}")
            else:
                lines.append(f"- `{rel}`")
        except Exception:
            pass

    if not lines:
        return ""

    truncated = lines[:max_entries]
    result = "\n".join(truncated)
    if len(lines) > max_entries:
        result += f"\n... 共 {len(lines)} 个文件，仅显示前 {max_entries} 个"

    return result


# ═════════════════════════════════════════════════════════════════
#  File Registry Builder — initializes registry from existing files
# ═════════════════════════════════════════════════════════════════
def build_initial_file_registry(workspace: str) -> dict[str, dict]:
    """Scan existing files to build initial file registry."""
    registry: dict[str, dict] = {}
    ws = Path(workspace)
    if not ws.is_dir():
        return registry

    exclude_dirs = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".idea", ".vscode"}
    for py_file in sorted(ws.rglob("*.py")):
        if any(p in exclude_dirs for p in py_file.parts):
            continue
        try:
            rel = str(py_file.relative_to(ws))
            text = py_file.read_text(encoding="utf-8", errors="replace")
            classes = []
            functions = []
            for line in text.splitlines():
                s = line.strip()
                if s.startswith("class ") and ":" in s:
                    name = s.split("(")[0].replace("class ", "").replace(":", "").strip()
                    classes.append(name)
                elif s.startswith(("def ", "async def ")):
                    name = s.replace("async def ", "").replace("def ", "").split("(")[0].strip()
                    functions.append(name)
            registry[rel] = {
                "classes": classes[:10],
                "functions": functions[:15],
                "last_action": "existing",
                "round": 0,
            }
        except Exception:
            pass

    return registry


# ═════════════════════════════════════════════════════════════════
#  Memory Bank — project-level progress tracking via .md files
# ═════════════════════════════════════════════════════════════════
MEMORY_BANK_DIR = ".gangge"

def read_memory_bank(workspace: str) -> tuple[str, str]:
    """Read .gangge/progress.md and .gangge/changelog.md content."""
    ws = Path(workspace)
    mb_dir = ws / MEMORY_BANK_DIR
    progress = ""
    changelog = ""
    if mb_dir.exists():
        p = mb_dir / "progress.md"
        if p.exists():
            try:
                progress = p.read_text(encoding="utf-8", errors="replace")[:3000]
            except Exception:
                pass
        c = mb_dir / "changelog.md"
        if c.exists():
            try:
                changelog = c.read_text(encoding="utf-8", errors="replace")[:3000]
            except Exception:
                pass
    return progress, changelog


# ═════════════════════════════════════════════════════════════════
#  Git Status Detector — branch, uncommitted changes, recent commits
# ═════════════════════════════════════════════════════════════════
def detect_git_state(workspace: str) -> str:
    """Detect current Git state: branch, uncommitted files, recent commits."""
    ws = Path(workspace)
    git_dir = ws / ".git"
    if not git_dir.exists():
        return ""

    import subprocess
    parts = []

    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=workspace, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if branch and branch != "HEAD":
            parts.append(f"分支: {branch}")
    except Exception:
        pass

    try:
        status = subprocess.run(
            ["git", "status", "--short"],
            cwd=workspace, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if status:
            lines = status.splitlines()[:10]
            parts.append(
                f"未提交变更 ({len(lines)} 文件):\n"
                + "\n".join(f"  {l}" for l in lines)
            )
    except Exception:
        pass

    try:
        log = subprocess.run(
            ["git", "log", "--oneline", "-5"],
            cwd=workspace, capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        if log:
            log_lines = log.splitlines()
            parts.append("最近提交:\n" + "\n".join(f"  {l}" for l in log_lines))
    except Exception:
        pass

    return "\n".join(parts) if parts else ""


def auto_git_commit(workspace: str, message: str) -> str:
    """Auto git add + commit. Returns commit hash or error."""
    import subprocess
    try:
        subprocess.run(
            ["git", "add", "-A"],
            cwd=workspace, capture_output=True, text=True, timeout=10,
        )
        result = subprocess.run(
            ["git", "commit", "-m", message[:80]],
            cwd=workspace, capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            # Extract short hash
            hash_match = ""
            for line in result.stdout.splitlines():
                if "commit" in line:
                    hash_match = line.strip()
                    break
            return hash_match or "committed"
        elif "nothing to commit" in result.stdout or "nothing to commit" in result.stderr:
            return "(无变更)"
        else:
            return f"commit failed: {result.stderr[:200]}"
    except Exception as e:
        return f"git error: {e}"



def update_memory_bank(workspace: str, progress_update: str, changelog_update: str):
    """Write update to .gangge/progress.md and .gangge/changelog.md."""
    ws = Path(workspace)
    mb_dir = ws / MEMORY_BANK_DIR
    mb_dir.mkdir(parents=True, exist_ok=True)

    if progress_update:
        p = mb_dir / "progress.md"
        try:
            # Append to existing
            existing = ""
            if p.exists():
                existing = p.read_text(encoding="utf-8", errors="replace")
            p.write_text(existing + "\n" + progress_update, encoding="utf-8")
        except Exception:
            pass

    if changelog_update:
        c = mb_dir / "changelog.md"
        try:
            # Prepend to changelog (newest first)
            existing = ""
            if c.exists():
                existing = c.read_text(encoding="utf-8", errors="replace")
            c.write_text(changelog_update + "\n---\n" + existing, encoding="utf-8")
        except Exception:
            pass


# ═════════════════════════════════════════════════════════════════
#  Main Window
# ═════════════════════════════════════════════════════════════════
class GanggeDesktop(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Gangge Code — AI 编程助手")
        self.setMinimumSize(1200, 800)
        self.resize(1500, 920)

        self._settings = QSettings("Gangge", "GanggeCode")
        self._llm: BaseLLM | None = None
        self._worker: GanggeWorker | None = None
        self._running = False
        self._current_session_id: str = ""
        self._batch_tasks: list[str] = []
        self._batch_queue: list[str] = []

        # Session DB
        self._db = SessionDB()
        self._db.connect()

        self._setup_menu()
        self._setup_ui()
        self._load_settings()
        self._refresh_session_list()
        self._update_provider_fields()

        # Status bar
        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_label = QLabel("就绪")
        sb.addWidget(self._status_label, 1)
        self._status_progress = QProgressBar()
        self._status_progress.setMaximumWidth(200)
        self._status_progress.setVisible(False)
        sb.addPermanentWidget(self._status_progress)

    # ── Menu ──────────────────────────────────────────────────
    def _setup_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu("文件(&F)")
        a = QAction("新建会话", self)
        a.setShortcut(QKeySequence("Ctrl+N"))
        a.triggered.connect(self._new_session)
        fm.addAction(a)
        fm.addSeparator()
        a = QAction("清空输出", self)
        a.setShortcut(QKeySequence("Ctrl+L"))
        a.triggered.connect(self._clear_output)
        fm.addAction(a)
        fm.addSeparator()
        a = QAction("退出(&Q)", self)
        a.setShortcut(QKeySequence("Ctrl+Q"))
        a.triggered.connect(self.close)
        fm.addAction(a)

        tm = mb.addMenu("工具(&T)")
        a = QAction("打开工作目录...", self)
        a.setShortcut(QKeySequence("Ctrl+O"))
        a.triggered.connect(self._browse_workspace)
        tm.addAction(a)

        hm = mb.addMenu("帮助(&H)")
        a = QAction("关于 Gangge Code", self)
        a.triggered.connect(lambda: QMessageBox.about(
            self, "关于", "<h2>Gangge Code v0.1.0</h2><p>AI 编程助手 — 5 层架构 Agentic Loop</p>"
            "<p>支持: DeepSeek · OpenAI · Anthropic · Ollama</p>"
            "<hr><p>会话持久化 · 文件 Diff · 测试验证 · 批量任务 · 计划确认</p>"))
        hm.addAction(a)

    # ── Config widgets (created early, displayed in settings dialog) ──
    def _init_config_widgets(self):
        """Create config widgets that need to exist before _load_settings."""
        # These are parented to self but not in any layout until _open_settings
        self._api_key_input = QLineEdit(self)
        self._api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key_input.setPlaceholderText("API Key...")
        self._api_key_input.hide()

        self._model_combo = QComboBox(self)
        self._model_combo.setEditable(True)
        self._model_combo.hide()

        self._base_url_input = QLineEdit(self)
        self._base_url_input.setPlaceholderText("API Base URL (如需要)")
        self._base_url_input.hide()

        self._max_rounds_spin = QSpinBox(self)
        self._max_rounds_spin.setRange(5, 100)
        self._max_rounds_spin.setValue(30)
        self._max_rounds_spin.hide()

        self._auto_allow_cb = QCheckBox("自动允许安全操作", self)
        self._auto_allow_cb.setChecked(True)
        self._auto_allow_cb.hide()

        self._auto_inject_cb = QCheckBox("自动注入项目上下文", self)
        self._auto_inject_cb.setChecked(True)
        self._auto_inject_cb.hide()

        self._test_verify_cb = QCheckBox("自动触发测试验证", self)
        self._test_verify_cb.setChecked(True)
        self._test_verify_cb.hide()

        self._git_commit_cb = QCheckBox("任务完成后自动 Git 提交", self)
        self._git_commit_cb.setChecked(True)
        self._git_commit_cb.hide()

        self._plan_mode_cb = QCheckBox("规划模式 (先出计划后执行)", self)
        self._plan_mode_cb.hide()

        self._extra_prompt = QPlainTextEdit(self)
        self._extra_prompt.setPlaceholderText("额外的指令...")
        self._extra_prompt.setMaximumHeight(100)
        self._extra_prompt.hide()

    # ── UI ────────────────────────────────────────────────────
    def _setup_ui(self):
        # ── Init config widgets (needed before _load_settings) ──
        self._init_config_widgets()

        c = QWidget()
        self.setCentralWidget(c)
        ml = QVBoxLayout(c)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)

        # ── Toolbar (compact, VS Code-style) ──
        tb = QToolBar()
        tb.setMovable(False)
        tb.setIconSize(QSize(14, 14))
        tb.setStyleSheet(
            "QToolBar{background:#161b22;border-bottom:1px solid #21262d;padding:2px 6px;spacing:4px;}"
        )
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        def _tb_btn(text, tip, callback):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.clicked.connect(lambda: callback())
            b.setStyleSheet(
                "QToolButton{color:#c9d1d9;padding:4px 10px;border-radius:4px;font-size:12px;}"
                "QToolButton:hover{background:#30363d;}"
            )
            return b

        tb.addWidget(_tb_btn("🔄 新建", "新建会话 (Ctrl+N)", self._new_session))
        self._btn_cancel = _tb_btn("⏹ 停止", "停止执行", self._cancel_task)
        self._btn_cancel.setEnabled(False)
        tb.addWidget(self._btn_cancel)
        tb.addWidget(_tb_btn("🗑 清空", "清空输出 (Ctrl+L)", self._clear_output))
        tb.addSeparator()
        tb.addWidget(_tb_btn("📂 目录", "选择工作目录 (Ctrl+O)", self._browse_workspace))
        tb.addWidget(_tb_btn("💾 导出", "保存输出到文件", self._save_output))
        tb.addSeparator()

        sp = QWidget()
        sp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        tb.addWidget(sp)

        lbl = QLabel("Provider:")
        lbl.setStyleSheet("color:#8b949e;font-size:12px;padding:0 4px;")
        tb.addWidget(lbl)
        self._provider_combo = QComboBox()
        self._provider_combo.setFixedWidth(130)
        for k, cfg in PROVIDER_CONFIGS.items():
            self._provider_combo.addItem(cfg["label"], k)
        self._provider_combo.currentIndexChanged.connect(self._update_provider_fields)
        tb.addWidget(self._provider_combo)

        tb.addSeparator()
        tb.addWidget(_tb_btn("⚙ 设置", "打开设置", self._open_settings))

        # ── Main splitter: Sidebar | Center ──
        main_sp = QSplitter(Qt.Orientation.Horizontal)
        main_sp.setHandleWidth(2)

        # ════════════════════════════════════════
        #  LEFT SIDEBAR — Sessions + Files
        # ════════════════════════════════════════
        sidebar = QWidget()
        sl = QVBoxLayout(sidebar)
        sl.setContentsMargins(4, 4, 0, 4)
        sl.setSpacing(4)

        sidebar_tabs = QTabWidget()
        sidebar_tabs.setDocumentMode(True)
        sidebar_tabs.setStyleSheet(
            "QTabWidget::pane{border:1px solid #21262d;border-radius:4px;background:#0d1117;}"
            "QTabBar::tab{background:#161b22;color:#8b949e;border:1px solid #21262d;"
            "border-bottom:none;padding:6px 16px;font-size:11px;}"
            "QTabBar::tab:selected{background:#0d1117;color:#f0f6fc;border-bottom:2px solid #f78166;}"
        )

        # ── Sessions tab ──
        sess_tab = QWidget()
        sess_lay = QVBoxLayout(sess_tab)
        sess_lay.setContentsMargins(4, 4, 4, 4)
        sess_lay.setSpacing(4)
        self._session_list = QListWidget()
        self._session_list.setStyleSheet(
            "QListWidget{background:#0d1117;border:1px solid #21262d;border-radius:4px;color:#c9d1d9;}"
            "QListWidget::item{padding:6px 8px;border-bottom:1px solid #161b22;font-size:12px;}"
            "QListWidget::item:selected{background:#1f6feb;color:#fff;}"
        )
        self._session_list.itemClicked.connect(self._on_session_clicked)
        sess_lay.addWidget(self._session_list)
        sess_btn_row = QHBoxLayout()
        for text, tip, cb in [
            ("➕", "新建会话", lambda: self._new_session()),
            ("✏️", "重命名", lambda: self._rename_session()),
            ("🗑️", "删除", lambda: self._delete_session()),
        ]:
            b = QPushButton(text)
            b.setFixedSize(28, 24)
            b.setToolTip(tip)
            b.setStyleSheet(
                "QPushButton{background:#21262d;border:1px solid #30363d;border-radius:4px;"
                "color:#c9d1d9;font-size:11px;padding:0;}"
                "QPushButton:hover{background:#30363d;}"
            )
            b.clicked.connect(cb)
            sess_btn_row.addWidget(b)
        sess_btn_row.addStretch()
        sess_lay.addLayout(sess_btn_row)
        sidebar_tabs.addTab(sess_tab, "📋 会话")

        # ── Files tab ──
        files_tab = QWidget()
        fl = QVBoxLayout(files_tab)
        fl.setContentsMargins(4, 4, 4, 4)
        fl.setSpacing(4)
        ws_row = QHBoxLayout()
        self._ws_input = QLineEdit()
        self._ws_input.setPlaceholderText("工作目录...")
        self._ws_input.setStyleSheet("font-size:11px;padding:4px 8px;")
        ws_row.addWidget(self._ws_input)
        ws_btn = QPushButton("📂")
        ws_btn.setFixedSize(28, 24)
        ws_btn.setToolTip("选择目录")
        ws_btn.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;border-radius:4px;"
            "color:#c9d1d9;font-size:11px;padding:0;}"
            "QPushButton:hover{background:#30363d;}"
        )
        ws_btn.clicked.connect(self._browse_workspace)
        ws_row.addWidget(ws_btn)
        fl.addLayout(ws_row)
        self._file_browser = FileBrowserWidget()
        self._file_browser.setStyleSheet(
            "FileBrowserWidget{background:#0d1117;border:1px solid #21262d;border-radius:4px;color:#c9d1d9;}"
        )
        fl.addWidget(self._file_browser)
        sidebar_tabs.addTab(files_tab, "📂 文件")

        sl.addWidget(sidebar_tabs)

        # ════════════════════════════════════════
        #  CENTER AREA — Chat + Bottom Panel
        # ════════════════════════════════════════
        center = QWidget()
        center_lay = QVBoxLayout(center)
        center_lay.setContentsMargins(8, 4, 8, 4)
        center_lay.setSpacing(4)

        # Vertical splitter: Chat output (top) | Tool/Diff panel (bottom)
        v_sp = QSplitter(Qt.Orientation.Vertical)
        v_sp.setHandleWidth(2)

        # ── Chat output ──
        self._output = QTextBrowser()
        self._output.setReadOnly(True)
        self._output.setOpenExternalLinks(True)
        self._output.setMinimumHeight(200)
        self._output.setStyleSheet(
            "QTextBrowser{background:#0d1117;border:1px solid #21262d;border-radius:6px;"
            "padding:12px;color:#c9d1d9;font-size:13px;}"
        )
        self._highlighter = OutputHighlighter(self._output.document())
        v_sp.addWidget(self._output)

        # ── Bottom panel: Tool/Diff tabs ──
        bottom_panel = QTabWidget()
        bottom_panel.setDocumentMode(True)
        bottom_panel.setMinimumHeight(150)
        bottom_panel.setMaximumHeight(350)
        bottom_panel.setStyleSheet(
            "QTabWidget::pane{border:1px solid #21262d;border-radius:4px;background:#0d1117;}"
            "QTabBar::tab{background:#161b22;color:#8b949e;border:1px solid #21262d;"
            "border-bottom:none;padding:4px 14px;font-size:11px;}"
            "QTabBar::tab:selected{background:#0d1117;color:#f0f6fc;}"
        )

        # Tools tab
        self._tool_table = DiffTabWidget()
        self._tool_table.setStyleSheet("background:#0d1117;")
        bottom_panel.addTab(self._tool_table, "🔧 工具调用")

        # Diff tab (reuses the same DiffTabWidget's diff viewer)
        self._diff_tab = DiffTabWidget()
        bottom_panel.addTab(self._diff_tab, "📝 文件变更")

        v_sp.addWidget(bottom_panel)
        v_sp.setSizes([400, 200])
        v_sp.setStretchFactor(0, 3)
        v_sp.setStretchFactor(1, 1)

        center_lay.addWidget(v_sp)

        # ── Input area ──
        input_frame = QFrame()
        input_frame.setStyleSheet(
            "QFrame{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:6px;}"
        )
        input_lay = QVBoxLayout(input_frame)
        input_lay.setContentsMargins(8, 6, 8, 6)
        input_lay.setSpacing(6)

        self._task_input = QPlainTextEdit()
        self._task_input.setPlaceholderText(
            "输入编程任务... (Ctrl+Enter 执行)\n"
            "多行 = 批量任务，每行一个，依次执行"
        )
        self._task_input.setMaximumHeight(80)
        self._task_input.setMinimumHeight(48)
        self._task_input.setStyleSheet(
            "QPlainTextEdit{background:#0d1117;border:1px solid #30363d;border-radius:6px;"
            "padding:8px;color:#c9d1d9;font-size:13px;}"
            "QPlainTextEdit:focus{border-color:#58a6ff;}"
        )
        input_lay.addWidget(self._task_input)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)
        self._batch_btn = QPushButton("📋 批量")
        self._batch_btn.setToolTip("多行任务依次执行")
        self._batch_btn.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;border-radius:6px;"
            "padding:6px 14px;color:#c9d1d9;font-size:12px;}"
            "QPushButton:hover{background:#30363d;}"
        )
        self._batch_btn.clicked.connect(self._run_batch)
        btn_row.addWidget(self._batch_btn)

        btn_row.addStretch()

        self._btn_run = QPushButton("▶  执行")
        self._btn_run.setProperty("primary", True)
        self._btn_run.setMinimumWidth(120)
        self._btn_run.setStyleSheet(
            "QPushButton{background:#238636;color:#fff;border:1px solid rgba(240,246,252,0.1);"
            "border-radius:6px;padding:8px 24px;font-size:13px;font-weight:600;}"
            "QPushButton:hover{background:#2ea043;}"
            "QPushButton:disabled{background:#21262d;color:#484f58;}"
        )
        self._btn_run.clicked.connect(self._run_task)
        btn_row.addWidget(self._btn_run)

        input_lay.addLayout(btn_row)
        QShortcut(QKeySequence("Ctrl+Return"), self._task_input, self._run_task)

        center_lay.addWidget(input_frame)

        # ── Assemble splitter ──
        main_sp.addWidget(sidebar)
        main_sp.addWidget(center)
        main_sp.setSizes([250, 800])
        main_sp.setStretchFactor(0, 0)
        main_sp.setStretchFactor(1, 1)

        ml.addWidget(main_sp)

        # Sync: workspace change → 刷新文件浏览器 + 会话列表
        self._ws_input.textChanged.connect(
            lambda: self._file_browser.set_root(self._ws_input.text())
        )
        self._ws_input.editingFinished.connect(
            lambda: self._refresh_session_list()
        )

    # ── Settings Dialog ───────────────────────────────────────
    def _open_settings(self):
        """Open a settings dialog (like VS Code's settings panel)."""
        dlg = QDialog(self)
        dlg.setWindowTitle("⚙ 设置 - Gangge Code")
        dlg.setMinimumSize(520, 520)
        dlg.setStyleSheet("QDialog{background:#0d1117;}")

        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)

        title = QLabel("设置")
        title.setStyleSheet("color:#f0f6fc;font-size:16px;font-weight:bold;padding:4px 0;")
        layout.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")

        sw = QWidget()
        sw.setStyleSheet("background:transparent;")
        form = QVBoxLayout(sw)
        form.setSpacing(16)

        # ── LLM ──
        llm_g = QGroupBox("LLM 配置")
        llm_g.setStyleSheet(
            "QGroupBox{font-size:13px;font-weight:600;color:#58a6ff;border:1px solid #30363d;"
            "border-radius:8px;margin-top:16px;padding:16px 12px 12px;}"
            "QGroupBox::title{subcontrol-origin:margin;left:14px;padding:0 6px;}"
        )
        lf = QFormLayout(llm_g)
        lf.setSpacing(8)
        # Use local widgets, sync with member widgets on accept
        _api_key = QLineEdit()
        _api_key.setEchoMode(QLineEdit.EchoMode.Password)
        _api_key.setPlaceholderText("API Key...")
        _api_key.setText(self._api_key_input.text())
        lf.addRow("API Key:", _api_key)

        _model = QComboBox()
        _model.setEditable(True)
        for i in range(self._model_combo.count()):
            _model.addItem(self._model_combo.itemText(i), self._model_combo.itemData(i))
        _model.setCurrentText(self._model_combo.currentText())
        lf.addRow("Model:", _model)

        _base_url = QLineEdit()
        _base_url.setPlaceholderText("API Base URL (如需要)")
        _base_url.setText(self._base_url_input.text())
        lf.addRow("Base URL:", _base_url)

        _show_key = QCheckBox("显示 API Key")
        _show_key.toggled.connect(
            lambda chk: _api_key.setEchoMode(
                QLineEdit.EchoMode.Normal if chk else QLineEdit.EchoMode.Password
            )
        )
        lf.addRow("", _show_key)
        form.addWidget(llm_g)

        # ── Advanced ──
        ad_g = QGroupBox("高级设置")
        ad_g.setStyleSheet(llm_g.styleSheet())
        af = QFormLayout(ad_g)
        af.setSpacing(6)

        _rounds = QSpinBox()
        _rounds.setRange(5, 100)
        _rounds.setValue(self._max_rounds_spin.value())
        af.addRow("最大轮数:", _rounds)

        _auto_allow = QCheckBox("自动允许安全操作")
        _auto_allow.setChecked(self._auto_allow_cb.isChecked())
        af.addRow("", _auto_allow)

        _auto_inject = QCheckBox("自动注入项目上下文")
        _auto_inject.setChecked(self._auto_inject_cb.isChecked())
        af.addRow("", _auto_inject)

        _test_verify = QCheckBox("自动触发测试验证")
        _test_verify.setChecked(self._test_verify_cb.isChecked())
        af.addRow("", _test_verify)

        _git_commit = QCheckBox("任务完成后自动 Git 提交")
        _git_commit.setChecked(self._git_commit_cb.isChecked())
        af.addRow("", _git_commit)

        _plan_mode = QCheckBox("规划模式 (先出计划后执行)")
        _plan_mode.setChecked(self._plan_mode_cb.isChecked())
        af.addRow("", _plan_mode)
        form.addWidget(ad_g)

        # ── Extra Prompt ──
        ex_g = QGroupBox("额外 System Prompt")
        ex_g.setStyleSheet(llm_g.styleSheet())
        ex_lay = QVBoxLayout(ex_g)
        _extra = QPlainTextEdit()
        _extra.setPlaceholderText("额外的指令，如编码规范、测试要求...")
        _extra.setMaximumHeight(100)
        _extra.setPlainText(self._extra_prompt.toPlainText())
        ex_lay.addWidget(_extra)
        form.addWidget(ex_g)

        form.addStretch()
        scroll.setWidget(sw)
        layout.addWidget(scroll, 1)

        # Buttons
        btn_bar = QHBoxLayout()
        btn_bar.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(
            "QPushButton{background:#21262d;color:#c9d1d9;border:1px solid #30363d;"
            "border-radius:6px;padding:8px 20px;font-size:13px;}"
            "QPushButton:hover{background:#30363d;}"
        )
        cancel_btn.clicked.connect(dlg.reject)
        btn_bar.addWidget(cancel_btn)

        ok_btn = QPushButton("✅ 保存设置")
        ok_btn.setStyleSheet(
            "QPushButton{background:#238636;color:#fff;border-radius:6px;padding:8px 24px;"
            "font-size:13px;font-weight:600;}"
            "QPushButton:hover{background:#2ea043;}"
        )
        ok_btn.clicked.connect(dlg.accept)
        btn_bar.addWidget(ok_btn)
        layout.addLayout(btn_bar)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            # Sync back to member widgets
            self._api_key_input.setText(_api_key.text())
            self._model_combo.clear()
            for i in range(_model.count()):
                self._model_combo.addItem(_model.itemText(i), _model.itemData(i))
            self._model_combo.setCurrentText(_model.currentText())
            self._base_url_input.setText(_base_url.text())
            self._max_rounds_spin.setValue(_rounds.value())
            self._auto_allow_cb.setChecked(_auto_allow.isChecked())
            self._auto_inject_cb.setChecked(_auto_inject.isChecked())
            self._test_verify_cb.setChecked(_test_verify.isChecked())
            self._git_commit_cb.setChecked(_git_commit.isChecked())
            self._plan_mode_cb.setChecked(_plan_mode.isChecked())
            self._extra_prompt.setPlainText(_extra.toPlainText())
            self._update_provider_fields()
            self._save_settings()
            self._sync_env_file()

    def _sync_env_file(self):
        """Sync desktop settings back to .env file so CLI also picks them up."""
        env_path = Path(__file__).resolve().parent.parent / ".env"
        provider = self._provider_combo.currentData()

        # Map provider to env keys
        api_key_map = {
            "deepseek": "DEEPSEEK_API_KEY",
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "ollama": "OLLAMA_API_KEY",
        }
        model_map = {
            "deepseek": "DEEPSEEK_MODEL",
            "openai": "OPENAI_MODEL",
            "anthropic": "ANTHROPIC_MODEL",
            "ollama": "OLLAMA_MODEL",
        }
        base_url_map = {
            "deepseek": "DEEPSEEK_BASE_URL",
            "ollama": "OLLAMA_BASE_URL",
        }

        updates = {
            "LLM_PROVIDER": provider,
            api_key_map.get(provider, ""): self._api_key_input.text(),
            model_map.get(provider, ""): self._model_combo.currentText(),
        }
        if provider in base_url_map and self._base_url_input.text().strip():
            updates[base_url_map[provider]] = self._base_url_input.text().strip()

        try:
            # Read existing .env
            lines = []
            if env_path.exists():
                lines = env_path.read_text(encoding="utf-8").splitlines()

            # Update or append
            updated_keys = set()
            new_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    new_lines.append(line)
                    continue
                if "=" in stripped:
                    key = stripped.split("=", 1)[0].strip()
                    if key in updates:
                        new_lines.append(f"{key}={updates[key]}")
                        updated_keys.add(key)
                    else:
                        new_lines.append(line)
                else:
                    new_lines.append(line)

            # Add missing keys
            for key, val in updates.items():
                if key and key not in updated_keys:
                    new_lines.append(f"{key}={val}")

            env_path.write_text("\n".join(new_lines), encoding="utf-8")
        except Exception:
            pass  # .env is optional, don't crash if it fails

    # ── Events ────────────────────────────────────────────────
    def closeEvent(self, event):
        self._cancel_task()
        self._save_settings()
        self._db.close()
        event.accept()

    # ── Session ───────────────────────────────────────────────
    def _new_session(self):
        self._clear_output()
        self._diff_tab.clear_entries()
        ws = self._ws_input.text().strip()
        sid = self._db.create_session("新会话", ws)
        self._current_session_id = sid
        self._refresh_session_list()
        # Select the new session in the list
        for i in range(self._session_list.count()):
            item = self._session_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == sid:
                self._session_list.setCurrentItem(item)
                break
        self._status_label.setText(f"新会话: {sid}")

    def _refresh_session_list(self):
        self._session_list.clear()
        # 按当前工作目录过滤，只显示属于该目录的会话
        current_ws = self._ws_input.text().strip()
        sessions = self._db.list_sessions(50, workspace=current_ws)
        for s in sessions:
            ws_tag = " 📁" if s["workspace"] else ""
            label = f"{s['title'][:30]}  ({s['updated_at'][:16]}){ws_tag}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, s["id"])
            item.setData(Qt.ItemDataRole.UserRole + 1, s["title"])
            self._session_list.addItem(item)

        # 如果当前工作目录有会话，在列表底部加分隔提示
        if current_ws and sessions:
            sep = QListWidgetItem(f"─ {len(sessions)} 个会话 ─")
            sep.setFlags(sep.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            sep.setForeground(QColor("#666666"))
            self._session_list.addItem(sep)

    def _on_session_clicked(self, item):
        sid = item.data(Qt.ItemDataRole.UserRole)
        if not sid or sid == self._current_session_id:
            return

        # Save current session messages
        self._save_current_session_messages()

        # Load new session
        self._current_session_id = sid
        self._clear_output()

        # ── CHANGE: 方案C — load_turns 重建对话历史 ──────────
        turn_msgs = self._db.load_turns(sid, limit=self._db.MAX_LOAD_MESSAGES)
        total = self._db.count_messages(sid)

        if total > self._db.MAX_LOAD_MESSAGES:
            hint = (
                f"📦 该会话共 {total} 条消息（聚合后），"
                f"仅显示最近 {self._db.MAX_LOAD_MESSAGES} 条。"
            )
            self._append_output(f"📂 加载会话: {item.text()}\n{hint}\n", "system")
        else:
            self._append_output(f"📂 加载会话: {item.text()} ({total} 条消息)\n", "system")
        self._append_output("─" * 60 + "\n", "system")

        # 渲染消息 — tool 角色只显示 80 字符摘要
        for msg in turn_msgs:
            role = msg["role"]
            content = msg["content"]
            if role == "user":
                self._append_output(f"👤 {content}", "user")
            elif role == "assistant" and isinstance(content, list):
                for block in content:
                    if block.get("type") == "text" and block.get("text"):
                        self._append_output(block["text"], "assistant")
                    elif block.get("type") == "tool_use":
                        name = block.get("name", "?")
                        self._append_output(f"  ▶ {name}(...)", "tool")
            elif role == "assistant":
                self._append_output(str(content), "assistant")
            elif role == "tool":
                summary = str(content)[:80].replace("\n", " ")
                is_error = msg.get("is_error", False)
                icon = "✗" if is_error else "✓"
                tid = (msg.get("tool_use_id", "") or "")[:8]
                self._append_output(f"    {icon} [{tid}] {summary}...", "tool")

        # Load tool calls
        self._diff_tab.clear_entries()
        calls = self._db.load_tool_calls(sid)
        for c in calls:
            self._diff_tab.add_entry(c["tool_name"], c["output"][:200], c["is_error"], c["diff"])

        # Restore session workspace if set
        sess = self._db.get_session(sid)
        if sess and sess["workspace"]:
            old_ws = self._ws_input.text().strip()
            if sess["workspace"] != old_ws:
                self._ws_input.setText(sess["workspace"])
                self._file_browser.set_root(sess["workspace"])
                self._refresh_session_list()  # 工作目录变了 → 刷新会话列表

        self._status_label.setText(f"会话: {sess['title'] if sess else sid}")

    def _delete_session(self):
        item = self._session_list.currentItem()
        if not item:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, "确认删除", f"删除会话 {item.text()}?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self._db.delete_session(sid)
            if self._current_session_id == sid:
                self._current_session_id = ""
                self._clear_output()
                self._diff_tab.clear_entries()
            self._refresh_session_list()

    def _rename_session(self):
        item = self._session_list.currentItem()
        if not item:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        title = item.data(Qt.ItemDataRole.UserRole + 1)
        new_title, ok = QInputDialog.getText(self, "重命名会话", "会话名称:", text=title)
        if ok and new_title:
            self._db.update_session(sid, title=new_title)
            self._refresh_session_list()

    def _save_current_session_messages(self):
        """Save current output to session DB."""
        if not self._current_session_id:
            return
        # We already save incrementally in _append_output, so this is a no-op
        # But we update the session timestamp
        self._db.update_session(self._current_session_id, updated_at=datetime.now().isoformat())

    # ── Actions ───────────────────────────────────────────────
    def _clear_output(self):
        self._output.clear()

    def _save_output(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存输出", "gangge_output.txt", "文本文件 (*.txt);;所有文件 (*)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._output.toPlainText())
            self._status_label.setText(f"已保存: {path}")

    def _browse_workspace(self):
        path = QFileDialog.getExistingDirectory(self, "选择工作目录", self._ws_input.text())
        if path:
            self._ws_input.setText(path)
            self._file_browser.set_root(path)
            self._status_label.setText(f"工作目录: {path}")

    def _update_provider_fields(self):
        key = self._provider_combo.currentData()
        cfg = PROVIDER_CONFIGS.get(key, PROVIDER_CONFIGS["deepseek"])
        self._model_combo.clear()
        self._model_combo.addItems(cfg["models"])
        sv = self._settings.value(f"model_{key}", cfg["model_default"])
        self._model_combo.setCurrentText(sv)
        if cfg.get("base_url_editable", False):
            self._base_url_input.setReadOnly(False)
            sv_url = self._settings.value(f"base_url_{key}", cfg["base_url_default"])
            self._base_url_input.setText(sv_url)
            self._base_url_input.setPlaceholderText(cfg["base_url_default"])
        else:
            self._base_url_input.setReadOnly(True)
            self._base_url_input.setText("")
            self._base_url_input.setPlaceholderText("(默认地址)")

    def _build_llm(self) -> BaseLLM | None:
        provider_key = self._provider_combo.currentData()
        api_key = self._api_key_input.text().strip()
        model = self._model_combo.currentText().strip()
        cfg = PROVIDER_CONFIGS.get(provider_key, {})

        if provider_key in ("deepseek", "openai"):
            if not api_key:
                api_key = os.environ.get(cfg.get("api_key_env", ""), "")
            if not api_key:
                self._status_label.setText("⚠️ 请输入 API Key")
                return None
            return create_llm(provider=provider_key)
        elif provider_key == "anthropic":
            if not api_key:
                api_key = os.environ.get("ANTHROPIC_API_KEY", "")
            if not api_key:
                self._status_label.setText("⚠️ 请输入 Anthropic API Key")
                return None
            from gangge.layer5_llm.anthropic import AnthropicLLM
            return AnthropicLLM(api_key=api_key, model=model, max_tokens=8192, temperature=0.0)
        elif provider_key == "ollama":
            url = self._base_url_input.text().strip() or "http://localhost:11434/v1"
            from gangge.layer5_llm.openai_compat import OpenAICompatLLM
            return OpenAICompatLLM(base_url=url, api_key="ollama", model=model, max_tokens=8192, temperature=0.0)
        return None

    # ── Run / Batch / Cancel ──────────────────────────────────
    def _run_task(self):
        if self._running:
            self._status_label.setText("⏳ 任务执行中...")
            return

        task = self._task_input.toPlainText().strip()
        if not task:
            self._status_label.setText("⚠️ 请输入任务")
            return

        llm = self._build_llm()
        if not llm:
            return
        self._execute_single(llm, task)

    def _run_batch(self):
        if self._running:
            return
        text = self._task_input.toPlainText().strip()
        tasks = [t.strip() for t in text.split("\n") if t.strip()]
        if len(tasks) < 2:
            self._run_task()
            return

        llm = self._build_llm()
        if not llm:
            return

        self._batch_queue = tasks
        self._status_label.setText(f"📋 批量任务: {len(tasks)} 个")
        self._execute_batch_next(llm)

    def _execute_batch_next(self, llm: BaseLLM):
        if not self._batch_queue:
            self._status_label.setText("✅ 批量任务全部完成")
            return

        task = self._batch_queue[0]
        remaining = len(self._batch_queue)
        total = len(self._batch_queue) + (1 if self._running else 0)

        # Create a new session for batch if none exists
        if not self._current_session_id:
            ws = self._ws_input.text().strip()
            self._current_session_id = self._db.create_session("批量任务", ws)
            self._refresh_session_list()

        self._execute_single(llm, task, batch_index=total - remaining, batch_total=total)

    def _execute_single(self, llm: BaseLLM, task: str, batch_index: int = 0, batch_total: int = 1):
        workspace = self._ws_input.text().strip()
        if not workspace:
            # Auto-create project folder
            from datetime import datetime
            ws_dir = Path.cwd() / "gangge_projects" / f"project_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            ws_dir.mkdir(parents=True, exist_ok=True)
            workspace = str(ws_dir)
            self._ws_input.setText(workspace)
            self._file_browser.set_root(workspace)
            self._status_label.setText(f"📁 自动创建项目: {workspace}")
        auto_allow = self._auto_allow_cb.isChecked()
        plan_mode = self._plan_mode_cb.isChecked()
        extra_prompt = self._extra_prompt.toPlainText().strip()

        # ── Auto-inject project context ──
        project_context = ""
        project_map = ""
        file_registry: dict = {}
        ganggerules = ""
        memory_bank_progress = ""
        memory_bank_changelog = ""
        if self._auto_inject_cb.isChecked():
            project_context = scan_project_context(workspace)
            if project_context:
                self._append_output("📁 已自动注入项目上下文\n", "system")

            # ── Build project map ──
            project_map = build_project_map(workspace)
            if project_map:
                self._append_output("🗺️ 已生成项目文件索引\n", "system")

            # ── Build initial file registry ──
            file_registry = build_initial_file_registry(workspace)
            if file_registry:
                self._append_output(f"📋 已注册 {len(file_registry)} 个现有文件\n", "system")

            # ── Read .ganggerules ──
            rules_path = Path(workspace) / ".ganggerules"
            if rules_path.exists():
                try:
                    ganggerules = rules_path.read_text(encoding="utf-8", errors="replace")[:3000]
                    self._append_output("📜 已加载 .ganggerules 项目规则\n", "system")
                except Exception:
                    pass

            # ── Read Memory Bank ──
            memory_bank_progress, memory_bank_changelog = read_memory_bank(workspace)
            if memory_bank_progress or memory_bank_changelog:
                self._append_output("📚 已加载 Memory Bank (进度+变更日志)\n", "system")

            # ── Git state injection ──
            git_state = detect_git_state(workspace)
            if git_state:
                project_context += "\n\n## Git 状态\n" + git_state
                self._append_output("🔀 已注入 Git 状态\n", "system")

        # Create session if none
        if not self._current_session_id:
            self._current_session_id = self._db.create_session(task[:40], workspace)
            self._refresh_session_list()

        self._llm = llm
        self._running = True
        self._btn_run.setEnabled(False)
        self._batch_btn.setEnabled(False)
        self._btn_cancel.setEnabled(True)
        self._status_progress.setVisible(True)
        self._status_progress.setRange(0, 0)

        batch_text = f" [{batch_index + 1}/{batch_total}]" if batch_total > 1 else ""
        self._status_label.setText(f"🚀 执行{batch_text}...")

        self._worker = GanggeWorker(
            llm=llm, task=task, workspace=workspace,
            max_rounds=self._max_rounds_spin.value(),
            plan_mode=plan_mode, project_context=project_context,
            system_prompt_extra=extra_prompt, auto_allow=auto_allow,
            batch_index=batch_index, batch_total=batch_total,
            project_map=project_map,
            file_registry=file_registry,
            ganggerules=ganggerules,
            memory_bank_progress=memory_bank_progress,
            memory_bank_changelog=memory_bank_changelog,
            provider=self._provider_combo.currentData(),
            model_name=self._model_combo.currentText(),
        )
        self._worker.text_block.connect(self._append_output)
        self._worker.tool_call_sig.connect(self._on_tool_call)
        self._worker.finished.connect(lambda s: self._on_finished(s, llm))
        # ── CHANGE: 方案C — turn_complete → save_turn ──────────
        if self._current_session_id:
            sid = self._current_session_id
            db = self._db
            self._worker.turn_complete.connect(
                lambda msgs: db.save_turn(sid, msgs)
            )
        # ────────────────────────────────────────────────────────
        self._worker.start()

    def _cancel_task(self):
        if self._worker and self._running:
            self._worker.cancel()
            self._append_output("\n⏹ 任务已取消\n", "system")
            self._batch_queue.clear()
            self._on_finished({}, None)

    def _on_finished(self, summary: dict, llm: BaseLLM | None):
        self._running = False
        self._btn_run.setEnabled(True)
        self._batch_btn.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._status_progress.setVisible(False)
        self._status_progress.setRange(0, 100)
        self._status_progress.setValue(0)

        # ── Plan mode: show confirmation dialog ──
        if summary.get("plan_mode") and summary.get("final_response"):
            dlg = PlanConfirmDialog(summary["final_response"], self)
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.approved:
                plan_text = dlg.get_plan_text()
                self._append_output("\n📋 计划已批准，开始执行...\n", "system")
                # Re-run with approved plan injected
                task = self._task_input.toPlainText().strip()
                task += "\n\n按照以下已批准的计划执行:\n" + plan_text
                self._task_input.setPlainText(task)
                # Trigger execution in next event loop iteration
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(100, self._run_task)
                return
            elif dlg.exec() == QDialog.DialogCode.Accepted and not dlg.approved:
                self._append_output("\n⏹ 计划被拒绝\n", "system")
                self._status_label.setText("计划被拒绝")
                return

        # ── Memory Bank update ──
        mb_update = summary.get("memory_bank_update", "")
        if mb_update and self._ws_input.text():
            workspace = self._ws_input.text().strip()
            # Split update into progress and changelog parts
            progress_part = ""
            changelog_part = mb_update
            if "progress" in mb_update.lower() or "## 进度" in mb_update:
                progress_part = mb_update
            update_memory_bank(workspace, progress_part, changelog_part)
            if progress_part or changelog_part:
                self._append_output("📚 Memory Bank 已更新\n", "system")

        # ── Git auto-commit ──
        if (
            self._git_commit_cb.isChecked()
            and summary
            and not summary.get("error")
            and self._ws_input.text()
        ):
            workspace = self._ws_input.text().strip()
            git_dir = Path(workspace) / ".git"
            if git_dir.exists():
                task_text = self._task_input.toPlainText().strip()[:60]
                commit_msg = f"gangge: {task_text or 'auto commit'}"
                result = auto_git_commit(workspace, commit_msg)
                self._append_output(f"🔀 Git: {result}\n", "system")

        if summary.get("error"):
            self._status_label.setText(f"❌ {summary['error']}")
        elif summary:
            r = summary.get("rounds", 0)
            c = summary.get("tool_calls", 0)
            self._status_label.setText(f"✅ 完成: {r} 轮, {c} 次工具调用")
        self._worker = None

        # Continue batch
        if self._batch_queue:
            self._batch_queue.pop(0)
            if self._batch_queue and llm:
                self._execute_batch_next(llm)

    def _on_tool_call(self, tool_name: str, output: str, is_error: bool, diff: str):
        self._diff_tab.add_entry(tool_name, output, is_error, diff)
        # Persist to DB
        if self._current_session_id:
            self._db.save_tool_call(
                self._current_session_id,
                round_num=self._diff_tab._table.rowCount(),
                tool_name=tool_name,
                tool_input="",
                tool_output=output,
                is_error=is_error,
                diff=diff,
            )

    def _append_output(self, text: str, role: str = ""):
        css = {"user": "color:#58a6ff;font-weight:bold", "assistant": "color:#3fb950",
               "tool": "color:#d29922", "system": "color:#8b949e;font-style:italic",
               "error": "color:#f85149;font-weight:bold"}.get(role, "")
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        # Simple code block handling
        lines = escaped.split("\n")
        parts = []
        in_code = False
        for line in lines:
            if line.strip().startswith("```"):
                if in_code:
                    parts.append("</code></pre>")
                    in_code = False
                else:
                    parts.append("<pre><code>")
                    in_code = True
                continue
            if in_code:
                parts.append(line + "\n")
            elif line == "":
                parts.append("<br>")
            else:
                parts.append(line + "<br>")
        if in_code:
            parts.append("</code></pre>")

        html = "".join(parts)
        if css:
            html = f'<span style="{css}">{html}</span>'

        cursor.insertHtml(html)
        self._output.setTextCursor(cursor)
        self._output.ensureCursorVisible()

        # ── CHANGE: 方案C — _append_output 只做 UI 渲染，DB 由 turn_complete 信号写入

    # ── Settings ──────────────────────────────────────────────
    def _save_settings(self):
        key = self._provider_combo.currentData()
        self._settings.setValue("provider", key)
        self._settings.setValue(f"api_key_{key}", self._api_key_input.text())
        self._settings.setValue(f"model_{key}", self._model_combo.currentText())
        self._settings.setValue(f"base_url_{key}", self._base_url_input.text())
        self._settings.setValue("workspace", self._ws_input.text())
        self._settings.setValue("max_rounds", self._max_rounds_spin.value())
        self._settings.setValue("plan_mode", self._plan_mode_cb.isChecked())
        self._settings.setValue("auto_allow", self._auto_allow_cb.isChecked())
        self._settings.setValue("auto_inject", self._auto_inject_cb.isChecked())
        self._settings.setValue("test_verify", self._test_verify_cb.isChecked())
        self._settings.setValue("git_commit", self._git_commit_cb.isChecked())
        self._settings.setValue("extra_prompt", self._extra_prompt.toPlainText())
        self._settings.setValue("window_geometry", self.saveGeometry())
        self._settings.setValue("window_state", self.saveState())

    def _load_settings(self):
        p = self._settings.value("provider", "deepseek")
        idx = self._provider_combo.findData(p)
        if idx >= 0:
            self._provider_combo.setCurrentIndex(idx)
        # Restore per-provider settings
        api_key = self._settings.value(f"api_key_{p}", "")
        if api_key:
            self._api_key_input.setText(api_key)
        model_val = self._settings.value(f"model_{p}", "")
        if model_val:
            self._model_combo.setCurrentText(model_val)
        base_url = self._settings.value(f"base_url_{p}", "")
        if base_url:
            self._base_url_input.setText(base_url)
        ws = self._settings.value("workspace", "")
        if ws:
            self._ws_input.setText(ws)
            self._file_browser.set_root(ws)
        else:
            # No saved workspace → auto-create a project folder
            from datetime import datetime
            projects_root = Path.cwd() / "gangge_projects"
            project_name = f"project_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            auto_ws = projects_root / project_name
            auto_ws.mkdir(parents=True, exist_ok=True)
            self._ws_input.setText(str(auto_ws))
            self._file_browser.set_root(str(auto_ws))
        self._max_rounds_spin.setValue(int(self._settings.value("max_rounds", 30)))
        self._plan_mode_cb.setChecked(self._settings.value("plan_mode", "false") == "true")
        self._auto_allow_cb.setChecked(self._settings.value("auto_allow", "true") == "true")
        self._auto_inject_cb.setChecked(self._settings.value("auto_inject", "true") != "false")
        self._test_verify_cb.setChecked(self._settings.value("test_verify", "true") != "false")
        self._git_commit_cb.setChecked(self._settings.value("git_commit", "true") != "false")
        ep = self._settings.value("extra_prompt", "")
        if ep:
            self._extra_prompt.setPlainText(ep)
        geo = self._settings.value("window_geometry")
        if geo:
            self.restoreGeometry(geo)
        st = self._settings.value("window_state")
        if st:
            self.restoreState(st)


# ═════════════════════════════════════════════════════════════════
#  Entry Point
# ═════════════════════════════════════════════════════════════════
def main():
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("Gangge Code")
    app.setApplicationVersion("0.1.0")
    app.setOrganizationName("Gangge")
    app.setStyleSheet(DARK_STYLESHEET)
    font = QFont("Segoe UI", 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)
    w = GanggeDesktop()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
