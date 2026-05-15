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
from gangge.i18n import get_language, set_language, t as _t

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
        "label": _t("ollama_label"),
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
                title TEXT NOT NULL DEFAULT 'New Session',
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

    def create_session(self, title: str = "", workspace: str = "") -> str:
        if not title:
            title = _t("session_new")
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
        self.setWindowTitle(_t("plan_title"))
        self.setMinimumSize(600, 400)
        self.approved = False
        self._setup_ui(plan_text)

    def _setup_ui(self, plan_text: str):
        layout = QVBoxLayout(self)

        title = QLabel(_t("plan_heading"))
        title.setProperty("heading", True)
        layout.addWidget(title)

        self._plan_view = QTextBrowser()
        self._plan_view.setPlainText(plan_text)
        self._plan_view.setStyleSheet("background: #161b22; padding: 12px; font-family: Consolas, monospace;")
        layout.addWidget(self._plan_view, 1)

        info = QLabel(_t("plan_info"))
        info.setWordWrap(True)
        info.setStyleSheet("color: #8b949e; padding: 4px 0;")
        layout.addWidget(info)

        btn_row = QHBoxLayout()
        self._edit_btn = QPushButton("✏️")
        self._edit_btn.clicked.connect(self._toggle_edit)
        btn_row.addWidget(self._edit_btn)

        btn_row.addStretch()

        reject_btn = QPushButton("❌")
        reject_btn.setProperty("danger", True)
        reject_btn.clicked.connect(self.reject)
        btn_row.addWidget(reject_btn)

        approve_btn = QPushButton(_t("btn_approve"))
        approve_btn.setProperty("primary", True)
        approve_btn.clicked.connect(self.approve)
        btn_row.addWidget(approve_btn)

        layout.addLayout(btn_row)

    def _toggle_edit(self):
        if self._plan_view.isReadOnly():
            self._plan_view.setReadOnly(False)
            self._edit_btn.setText(_t("btn_save_edit"))
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
class DiffViewer(QWidget):
    """Displays unified diffs with green/red highlighting and rollback action."""

    rollback_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._text = QTextBrowser()
        self._text.setReadOnly(True)
        self._text.setStyleSheet(
            "QTextBrowser{font-family:'Consolas','Courier New',monospace;font-size:12px;"
            "background:#0d1117;border:1px solid #21262d;border-radius:4px;color:#c9d1d9;}"
        )
        layout.addWidget(self._text)

        self._action_bar = QHBoxLayout()
        self._action_bar.setContentsMargins(4, 0, 4, 0)

        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet("color:#8b949e;font-size:11px;")
        self._action_bar.addWidget(self._stats_label)
        self._action_bar.addStretch()

        self._rollback_btn = QPushButton("↩️ 回滚此变更")
        self._rollback_btn.setStyleSheet(
            "QPushButton{background:#da3633;border:1px solid #f85149;border-radius:4px;"
            "color:#fff;font-size:11px;padding:3px 10px;font-weight:bold;}"
            "QPushButton:hover{background:#f85149;}"
        )
        self._rollback_btn.clicked.connect(self.rollback_requested.emit)
        self._rollback_btn.setVisible(False)
        self._action_bar.addWidget(self._rollback_btn)

        self._copy_btn = QPushButton("📋 复制")
        self._copy_btn.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;border-radius:4px;"
            "color:#8b949e;font-size:11px;padding:3px 8px;}"
            "QPushButton:hover{background:#30363d;color:#c9d1d9;}"
        )
        self._copy_btn.clicked.connect(self._copy_diff)
        self._copy_btn.setVisible(False)
        self._action_bar.addWidget(self._copy_btn)

        layout.addLayout(self._action_bar)

        self._current_diff = ""

    def show_diff(self, diff_text: str):
        self._current_diff = diff_text
        self._text.clear()
        if not diff_text.strip():
            self._text.setPlainText("(无变更)")
            self._stats_label.setText("")
            self._rollback_btn.setVisible(False)
            self._copy_btn.setVisible(False)
            return

        added = sum(1 for l in diff_text.splitlines() if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in diff_text.splitlines() if l.startswith("-") and not l.startswith("---"))
        self._stats_label.setText(f"+{added} / -{removed} 行变更")
        self._rollback_btn.setVisible(True)
        self._copy_btn.setVisible(True)

        html = []
        for line in diff_text.splitlines():
            escaped = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            if line.startswith("+") and not line.startswith("+++"):
                html.append(f'<span style="background:#1b3a1b;color:#3fb950">{escaped}</span>')
            elif line.startswith("-") and not line.startswith("---"):
                html.append(f'<span style="background:#3a1b1b;color:#f85149">{escaped}</span>')
            elif line.startswith("@@"):
                html.append(f'<span style="color:#58a6ff;font-weight:bold">{escaped}</span>')
            elif line.startswith("---") or line.startswith("+++"):
                html.append(f'<span style="color:#d29922;font-weight:bold">{escaped}</span>')
            else:
                html.append(f'<span style="color:#8b949e">{escaped}</span>')
        self._text.setHtml("<pre style='margin:4px;line-height:1.4;'>" + "<br>".join(html) + "</pre>")

    def set_plain_text(self, text: str):
        self._current_diff = ""
        self._text.setPlainText(text)
        self._stats_label.setText("")
        self._rollback_btn.setVisible(False)
        self._copy_btn.setVisible(False)

    def _copy_diff(self):
        if self._current_diff:
            from PyQt6.QtWidgets import QApplication
            QApplication.clipboard().setText(self._current_diff)


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
    ask_user_sig = pyqtSignal(str)          # question to ask user

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
        self._ask_user_answer = ""
        self._ask_user_event = asyncio.Event()

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
            self.text_block.emit(_t("execution_error", error=f"{e}\n{traceback.format_exc()}"), "error")
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
        from gangge.layer3_agent.tools.ask_user import AskUserTool
        from gangge.layer3_agent.tools.lint_check import LintCheckTool

        registry = ToolRegistry()
        registry.register(BashTool(workspace=self.workspace))
        registry.register(ReadFileTool(workspace=self.workspace))
        registry.register(WriteFileTool(workspace=self.workspace))
        registry.register(EditFileTool(workspace=self.workspace))
        registry.register(LintCheckTool(workspace=self.workspace))
        for cls in [GrepTool, GlobTool, ListDirTool, WebFetchTool]:
            registry.register(cls())

        async def _ask_user_callback(question: str) -> str:
            self._ask_user_answer = ""
            self._ask_user_event.clear()
            self.ask_user_sig.emit(question)
            await self._ask_user_event.wait()
            return self._ask_user_answer

        registry.register(AskUserTool(ask_callback=_ask_user_callback))

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
            system_text += _t("plan_mode_prompt")

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
            ask_user_callback=_ask_user_callback,
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
                self.text_block.emit(_t("execution_tool_call", name=block.tool_name, input=inp), "tool")

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
        self.text_block.emit(_t("execution_workspace", path=self.workspace), "system")
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
            "shadow_checkpoint_before": result.extra.get("shadow_checkpoint_before", ""),
            "shadow_checkpoint_after": result.extra.get("shadow_checkpoint_after", ""),
        }

        for exc in result.tool_executions:
            diff = exc.metadata.get("diff", "")
            self.tool_call_sig.emit(exc.tool_name, exc.output[:300], exc.is_error, diff)

        inp = result.total_tokens.get("input", 0)
        out = result.total_tokens.get("output", 0)
        cost_part = f" | 费用: {cost_display}" if cost_display else ""
        self.text_block.emit(
            _t("execution_done", rounds=result.total_rounds, tools=len(result.tool_executions), input=inp, output=out, cost=cost_part),
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

    FILE_ICONS = {
        ".py": "🐍", ".js": "📜", ".ts": "📘", ".jsx": "⚛️", ".tsx": "⚛️",
        ".html": "🌐", ".css": "🎨", ".scss": "🎨", ".sass": "🎨",
        ".json": "📋", ".yaml": "⚙️", ".yml": "⚙️", ".toml": "⚙️",
        ".md": "📝", ".rst": "📝", ".txt": "📄",
        ".sql": "🗄️", ".db": "🗄️", ".sqlite": "🗄️",
        ".sh": "💻", ".bat": "💻", ".ps1": "💻",
        ".dockerfile": "🐳", ".env": "🔐", ".gitignore": "🔀",
        ".cpp": "🔧", ".c": "🔧", ".h": "🔧", ".hpp": "🔧",
        ".rs": "🦀", ".go": "🐹", ".java": "☕", ".kt": "📱",
        ".rb": "💎", ".php": "🐘", ".swift": "🦅",
        ".png": "🖼️", ".jpg": "🖼️", ".jpeg": "🖼️", ".gif": "🖼️", ".svg": "🖼️",
        ".mp4": "🎬", ".mp3": "🎵", ".wav": "🎵",
        ".zip": "📦", ".tar": "📦", ".gz": "📦", ".rar": "📦",
        ".pdf": "📑", ".doc": "📑", ".docx": "📑",
        ".xml": "📰", ".csv": "📊", ".xlsx": "📊",
    }
    FOLDER_ICON = "📁"
    FOLDER_OPEN_ICON = "📂"
    DEFAULT_FILE_ICON = "📄"

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setAnimated(True)
        self._tree.setIndentation(16)
        self._tree.itemExpanded.connect(self._on_expand)
        self._tree.itemCollapsed.connect(self._on_collapse)
        self._tree.itemClicked.connect(self._on_click)
        self._tree.setStyleSheet(
            "QTreeWidget{background:#0d1117;border:1px solid #21262d;border-radius:6px;"
            "color:#c9d1d9;outline:none;}"
            "QTreeWidget::item{padding:3px 4px;border-radius:3px;}"
            "QTreeWidget::item:selected{background:#1f6feb;color:#fff;}"
            "QTreeWidget::item:hover{background:#161b22;}"
        )
        layout.addWidget(self._tree)
        self._root_path = ""

    def _get_icon(self, entry: Path) -> str:
        if entry.is_dir():
            return self.FOLDER_ICON
        ext = entry.suffix.lower()
        return self.FILE_ICONS.get(ext, self.DEFAULT_FILE_ICON)

    def set_root(self, path: str):
        self._root_path = path
        self._tree.clear()
        if not path or not os.path.isdir(path):
            return
        root_item = QTreeWidgetItem([f"{self.FOLDER_OPEN_ICON} {os.path.basename(path) or path}"])
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
            icon = self._get_icon(entry)
            child = QTreeWidgetItem([f"{icon} {entry.name}"])
            child.setData(0, Qt.ItemDataRole.UserRole, str(entry))
            if entry.is_dir():
                child.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
                child.addChild(QTreeWidgetItem(["(loading)"]))
            parent_item.addChild(child)

    def _on_expand(self, item):
        text = item.text(0)
        if self.FOLDER_ICON in text and self.FOLDER_OPEN_ICON not in text:
            item.setText(0, text.replace(self.FOLDER_ICON, self.FOLDER_OPEN_ICON, 1))
        path = item.data(0, Qt.ItemDataRole.UserRole) or ""
        if not path or not os.path.isdir(path):
            return
        if item.childCount() == 1 and item.child(0).text(0) == "(loading)":
            item.removeChild(item.child(0))
        if item.childCount() == 0:
            self._populate(item, path, self._depth(item))

    def _on_collapse(self, item):
        text = item.text(0)
        if self.FOLDER_OPEN_ICON in text:
            item.setText(0, text.replace(self.FOLDER_OPEN_ICON, self.FOLDER_ICON, 1))

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
#  Tool Call Table + Inline Diff Viewer
# ═════════════════════════════════════════════════════════════════
class ToolCallPanel(QWidget):
    """Tool call table with inline diff viewer — saves vertical space."""

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # Header with count
        header = QHBoxLayout()
        self._count_label = QLabel(_t("tool_calls", n=0))
        self._count_label.setProperty("heading", True)
        header.addWidget(self._count_label)
        header.addStretch()
        clear_btn = QPushButton(_t("btn_clear"))
        clear_btn.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;border-radius:4px;"
            "color:#8b949e;font-size:11px;padding:2px 8px;}"
            "QPushButton:hover{background:#30363d;color:#c9d1d9;}"
        )
        clear_btn.clicked.connect(self.clear_entries)
        header.addWidget(clear_btn)
        layout.addLayout(header)

        # Table
        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels([_t("tool_header_num"), _t("tool_header_name"), _t("tool_header_status"), _t("tool_header_output"), ""])
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.setColumnWidth(0, 36)
        self._table.setColumnWidth(1, 90)
        self._table.setColumnWidth(2, 50)
        self._table.setColumnWidth(4, 40)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setStyleSheet(
            "QTableWidget{background-color:#0d1117;border:1px solid #21262d;border-radius:6px;"
            "gridline-color:#161b22;color:#c9d1d9;}"
            "QTableWidget::item{padding:4px 6px;font-size:12px;}"
            "QTableWidget::item:selected{background:#1f6feb;}"
        )
        self._table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self._table)

        # Inline diff viewer (hidden by default)
        self._diff_frame = QFrame()
        self._diff_frame.setStyleSheet(
            "QFrame{background:#0d1117;border:1px solid #30363d;border-radius:6px;}"
        )
        diff_layout = QVBoxLayout(self._diff_frame)
        diff_layout.setContentsMargins(8, 6, 8, 6)
        diff_layout.setSpacing(4)

        diff_header = QHBoxLayout()
        diff_title = QLabel("📝 文件变更")
        diff_title.setStyleSheet("color:#58a6ff;font-size:12px;font-weight:bold;")
        diff_header.addWidget(diff_title)
        diff_header.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(22, 22)
        close_btn.setStyleSheet(
            "QPushButton{background:transparent;color:#8b949e;font-size:12px;border:none;}"
            "QPushButton:hover{color:#f85149;}"
        )
        close_btn.clicked.connect(lambda: self._diff_frame.setVisible(False))
        diff_header.addWidget(close_btn)
        diff_layout.addLayout(diff_header)

        self._diff_viewer = DiffViewer()
        self._diff_viewer.setMinimumHeight(120)
        self._diff_viewer.setMaximumHeight(300)
        self._diff_viewer.rollback_requested.connect(self._on_rollback_diff)
        diff_layout.addWidget(self._diff_viewer)
        self._diff_frame.setVisible(False)
        layout.addWidget(self._diff_frame)

        self._entries: list[dict] = []
        self._expanded_row: int = -1

    def add_entry(self, tool_name: str, output: str, is_error: bool, diff: str = ""):
        row = self._table.rowCount()
        self._table.insertRow(row)

        # Row height
        self._table.setRowHeight(row, 28)

        # #
        num = QTableWidgetItem(str(row + 1))
        num.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        num.setForeground(QColor("#484f58"))
        self._table.setItem(row, 0, num)

        # Tool name with icon
        icon_map = {
            "write_file": "📝", "edit_file": "✏️", "read_file": "📄",
            "bash": "💻", "grep": "🔍", "glob": "📂", "list_dir": "📁",
            "web_fetch": "🌐", "ask_user": "❓", "lint_check": "🔍",
        }
        icon = icon_map.get(tool_name, "🔧")
        tool_item = QTableWidgetItem(f"{icon} {tool_name}")
        tool_item.setForeground(QColor("#d29922"))
        self._table.setItem(row, 1, tool_item)

        # Status
        status_text = "❌" if is_error else "✅"
        status_item = QTableWidgetItem(status_text)
        status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        status_item.setForeground(QColor("#f85149" if is_error else "#3fb950"))
        self._table.setItem(row, 2, status_item)

        # Output (truncated)
        out_text = output[:120].replace("\n", " ")
        out_item = QTableWidgetItem(out_text)
        out_item.setToolTip(output[:500])
        out_item.setForeground(QColor("#8b949e"))
        self._table.setItem(row, 3, out_item)

        # Diff indicator
        has_diff = bool(diff and diff.strip())
        diff_btn = QTableWidgetItem("📋" if has_diff else "")
        diff_btn.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        diff_btn.setToolTip(_t("tip_diff") if has_diff else _t("tip_no_diff"))
        diff_btn.setForeground(QColor("#58a6ff" if has_diff else "#30363d"))
        self._table.setItem(row, 4, diff_btn)

        self._entries.append({
            "tool_name": tool_name,
            "output": output,
            "is_error": is_error,
            "diff": diff,
            "has_diff": has_diff,
        })
        self._count_label.setText(_t("tool_calls", n=len(self._entries)))
        self._table.scrollToBottom()

    def _on_cell_clicked(self, row: int, col: int):
        if row < 0 or row >= len(self._entries):
            return
        entry = self._entries[row]

        # Click diff column or any row to toggle diff
        if col == 4 or entry.get("has_diff"):
            if self._expanded_row == row and self._diff_frame.isVisible():
                self._diff_frame.setVisible(False)
                self._expanded_row = -1
            else:
                self._diff_viewer.show_diff(entry.get("diff", ""))
                self._diff_frame.setVisible(True)
                self._expanded_row = row
        else:
            # Show output in diff viewer for non-diff entries
            self._diff_viewer.set_plain_text(entry.get("output", "") or "(无输出)")
            self._diff_frame.setVisible(True)
            self._expanded_row = row

    def clear_entries(self):
        self._table.setRowCount(0)
        self._entries.clear()
        self._diff_frame.setVisible(False)
        self._expanded_row = -1
        self._count_label.setText(_t("tool_calls", n=0))

    def _on_rollback_diff(self):
        from PyQt6.QtWidgets import QMessageBox
        window = self.window()
        workspace = ""
        if hasattr(window, "_ws_input"):
            workspace = window._ws_input.text().strip()
        if not workspace:
            return
        from gangge.layer4_tools.shadow_git import ShadowGit
        sg = ShadowGit(workspace)
        if not sg.is_available():
            return
        reply = QMessageBox.warning(
            window, _t("rollback_confirm"),
            _t("rollback_done_simple"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if sg.rollback("HEAD~1"):
            if hasattr(window, "_append_output"):
                window._append_output(_t("rollback_done_simple"), "system")
            if hasattr(window, "_file_browser"):
                window._file_browser.set_root(workspace)
            if hasattr(window, "_status_label"):
                window._status_label.setText(_t("status_rollback_ok"))
            self._diff_frame.setVisible(False)
        else:
            if hasattr(window, "_status_label"):
                window._status_label.setText(_t("status_rollback_fail"))


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
        self.setWindowTitle(f"{_t('app_title')} — {_t('app_subtitle')}")
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

        # Status bar — multi-section with real-time stats
        sb = QStatusBar()
        self.setStatusBar(sb)
        sb.setStyleSheet("QStatusBar{background:#161b22;border-top:1px solid #21262d;padding:2px 8px;}")

        # Left: main status message
        self._status_label = QLabel(_t("status_ready"))
        self._status_label.setStyleSheet("color:#c9d1d9;font-size:12px;padding:2px 8px;")
        sb.addWidget(self._status_label, 1)

        # Center: live stats (rounds, tokens)
        self._stats_label = QLabel("")
        self._stats_label.setStyleSheet("color:#8b949e;font-size:11px;padding:2px 8px;")
        sb.addPermanentWidget(self._stats_label)

        # Right: progress bar
        self._status_progress = QProgressBar()
        self._status_progress.setMaximumWidth(120)
        self._status_progress.setMaximumHeight(14)
        self._status_progress.setStyleSheet(
            "QProgressBar{background:#21262d;border:1px solid #30363d;border-radius:6px;"
            "text-align:center;color:#8b949e;font-size:10px;height:14px;}"
            "QProgressBar::chunk{background:#1f6feb;border-radius:5px;}"
        )
        self._status_progress.setVisible(False)
        sb.addPermanentWidget(self._status_progress)

        # Far right: timer
        self._timer_label = QLabel("")
        self._timer_label.setStyleSheet("color:#484f58;font-size:11px;padding:2px 4px;")
        sb.addPermanentWidget(self._timer_label)

    # ── Menu ──────────────────────────────────────────────────
    def _setup_menu(self):
        mb = self.menuBar()
        fm = mb.addMenu(_t("menu_file"))
        a = QAction(_t("menu_new_session"), self)
        a.setShortcut(QKeySequence("Ctrl+N"))
        a.triggered.connect(self._new_session)
        fm.addAction(a)
        fm.addSeparator()
        a = QAction(_t("menu_clear_output"), self)
        a.setShortcut(QKeySequence("Ctrl+L"))
        a.triggered.connect(self._clear_output)
        fm.addAction(a)
        fm.addSeparator()
        a = QAction(_t("menu_quit"), self)
        a.setShortcut(QKeySequence("Ctrl+Q"))
        a.triggered.connect(self.close)
        fm.addAction(a)

        tm = mb.addMenu(_t("menu_tools"))
        a = QAction(_t("menu_open_workspace"), self)
        a.setShortcut(QKeySequence("Ctrl+O"))
        a.triggered.connect(self._browse_workspace)
        tm.addAction(a)

        hm = mb.addMenu(_t("menu_help"))
        a = QAction(_t("menu_about"), self)
        a.triggered.connect(lambda: QMessageBox.about(
            self, _t("menu_about"), _t("about_text")))
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

        self._auto_allow_cb = QCheckBox(_t("cb_auto_allow"), self)
        self._auto_allow_cb.setChecked(True)
        self._auto_allow_cb.hide()

        self._auto_inject_cb = QCheckBox(_t("cb_auto_inject"), self)
        self._auto_inject_cb.setChecked(True)
        self._auto_inject_cb.hide()

        self._test_verify_cb = QCheckBox(_t("cb_test_verify"), self)
        self._test_verify_cb.setChecked(True)
        self._test_verify_cb.hide()

        self._git_commit_cb = QCheckBox(_t("cb_git_commit"), self)
        self._git_commit_cb.setChecked(True)
        self._git_commit_cb.hide()

        self._lang_combo = QComboBox(self)
        self._lang_combo.addItem("中文", "zh")
        self._lang_combo.addItem("English", "en")
        self._lang_combo.hide()

        self._plan_mode_cb = QCheckBox(_t("cb_plan_mode"), self)
        self._plan_mode_cb.hide()

        self._extra_prompt = QPlainTextEdit(self)
        self._extra_prompt.setPlaceholderText(_t("extra_prompt_placeholder"))
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

        tb.addWidget(_tb_btn(_t("btn_new"), _t("tip_new"), self._new_session))
        self._btn_cancel = _tb_btn(_t("btn_stop"), _t("tip_stop"), self._cancel_task)
        self._btn_cancel.setEnabled(False)
        tb.addWidget(self._btn_cancel)
        tb.addWidget(_tb_btn(_t("btn_clear"), _t("tip_clear"), self._clear_output))
        tb.addSeparator()
        tb.addWidget(_tb_btn(_t("btn_dir"), _t("tip_dir"), self._browse_workspace))
        tb.addWidget(_tb_btn(_t("btn_export"), _t("tip_export"), self._save_output))
        self._btn_rollback = _tb_btn(_t("btn_rollback"), _t("tip_rollback"), self._rollback_checkpoint)
        self._btn_rollback.setEnabled(False)
        tb.addWidget(self._btn_rollback)
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
        tb.addWidget(_tb_btn(_t("btn_settings"), _t("tip_settings"), self._open_settings))

        # ── Main splitter: Sidebar | Center | Preview ──
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
            ("➕", _t("sidebar_new"), lambda: self._new_session()),
            ("✏️", _t("sidebar_rename"), lambda: self._rename_session()),
            ("🗑️", _t("sidebar_delete"), lambda: self._delete_session()),
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
        sidebar_tabs.addTab(sess_tab, _t("tab_sessions"))

        # ── Files tab ──
        files_tab = QWidget()
        fl = QVBoxLayout(files_tab)
        fl.setContentsMargins(4, 4, 4, 4)
        fl.setSpacing(4)
        ws_row = QHBoxLayout()
        self._ws_input = QLineEdit()
        self._ws_input.setPlaceholderText(_t("workspace_placeholder"))
        self._ws_input.setStyleSheet("font-size:11px;padding:4px 8px;")
        ws_row.addWidget(self._ws_input)
        ws_btn = QPushButton("📂")
        ws_btn.setFixedSize(28, 24)
        ws_btn.setToolTip(_t("tip_select_dir"))
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
        self._file_browser.file_selected.connect(self._on_file_selected)
        fl.addWidget(self._file_browser)
        sidebar_tabs.addTab(files_tab, "📂 文件")

        sl.addWidget(sidebar_tabs)

        # ════════════════════════════════════════
        #  CENTER AREA — Chat + Input (VSCode-style)
        # ════════════════════════════════════════
        center = QWidget()
        center_lay = QVBoxLayout(center)
        center_lay.setContentsMargins(0, 0, 0, 0)
        center_lay.setSpacing(0)

        # ── Chat output ──
        self._output = QTextBrowser()
        self._output.setReadOnly(True)
        self._output.setOpenExternalLinks(True)
        self._output.setStyleSheet(
            "QTextBrowser{background:#0d1117;border:none;"
            "padding:16px 20px;color:#c9d1d9;font-size:13px;}"
        )
        self._highlighter = OutputHighlighter(self._output.document())
        center_lay.addWidget(self._output, 1)

        # ── Input area (compact, VSCode-style bottom bar) ──
        input_frame = QFrame()
        input_frame.setStyleSheet(
            "QFrame{background:#161b22;border-top:1px solid #21262d;}"
        )
        input_lay = QHBoxLayout(input_frame)
        input_lay.setContentsMargins(12, 8, 12, 8)
        input_lay.setSpacing(8)

        self._task_input = QPlainTextEdit()
        self._task_input.setPlaceholderText(
            _t("input_placeholder")
        )
        self._task_input.setMaximumHeight(100)
        self._task_input.setMinimumHeight(36)
        self._task_input.setStyleSheet(
            "QPlainTextEdit{background:#0d1117;border:1px solid #30363d;"
            "border-radius:6px;padding:6px 10px;color:#c9d1d9;font-size:13px;}"
            "QPlainTextEdit:focus{border:1px solid #58a6ff;outline:none;}"
        )
        self._task_input.textChanged.connect(self._auto_resize_input)
        input_lay.addWidget(self._task_input, 1)

        # Button column: Stop/Run toggle + Batch
        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)
        btn_col.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self._batch_btn = QPushButton(_t("btn_batch"))
        self._batch_btn.setToolTip(_t("tip_batch"))
        self._batch_btn.setFixedHeight(28)
        self._batch_btn.setStyleSheet(
            "QPushButton{background:#21262d;border:1px solid #30363d;border-radius:4px;"
            "color:#8b949e;font-size:11px;padding:2px 8px;}"
            "QPushButton:hover{background:#30363d;color:#c9d1d9;}"
        )
        self._batch_btn.clicked.connect(self._run_batch)
        btn_col.addWidget(self._batch_btn)

        self._btn_run = QPushButton(_t("btn_send"))
        self._btn_run.setToolTip(_t("tip_send"))
        self._btn_run.setFixedHeight(34)
        self._btn_run.setStyleSheet(
            "QPushButton{background:#238636;color:#fff;border:none;"
            "border-radius:6px;font-size:13px;font-weight:bold;padding:4px 14px;}"
            "QPushButton:hover{background:#2ea043;}"
            "QPushButton:disabled{background:#21262d;color:#484f58;}"
        )
        self._btn_run.clicked.connect(self._run_task)
        btn_col.addWidget(self._btn_run)

        # Stop button (hidden by default, shown during execution)
        self._btn_stop = QPushButton(_t("btn_stop"))
        self._btn_stop.setToolTip(_t("tip_stop"))
        self._btn_stop.setFixedHeight(34)
        self._btn_stop.setStyleSheet(
            "QPushButton{background:#da3633;color:#fff;border:none;"
            "border-radius:6px;font-size:13px;font-weight:bold;padding:4px 14px;}"
            "QPushButton:hover{background:#f85149;}"
        )
        self._btn_stop.clicked.connect(self._cancel_task)
        self._btn_stop.setVisible(False)
        btn_col.addWidget(self._btn_stop)

        input_lay.addLayout(btn_col)

        self._task_input.installEventFilter(self)

        center_lay.addWidget(input_frame)

        # ════════════════════════════════════════
        #  RIGHT PANEL — Preview + Tool Calls (VSCode-style side panel)
        # ════════════════════════════════════════
        right_panel = QWidget()
        right_panel.setMinimumWidth(280)
        right_panel.setMaximumWidth(600)
        right_lay = QVBoxLayout(right_panel)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        right_tabs = QTabWidget()
        right_tabs.setDocumentMode(True)
        right_tabs.setStyleSheet(
            "QTabWidget::pane{border:none;background:#0d1117;}"
            "QTabBar::tab{background:#161b22;color:#8b949e;border:none;"
            "border-bottom:2px solid transparent;padding:8px 14px;font-size:11px;}"
            "QTabBar::tab:selected{color:#f0f6fc;border-bottom:2px solid #f78166;}"
        )

        # ── Preview tab (file content viewer) ──
        preview_tab = QWidget()
        preview_lay = QVBoxLayout(preview_tab)
        preview_lay.setContentsMargins(4, 4, 4, 4)
        preview_lay.setSpacing(4)

        self._preview_path = QLabel(_t("preview_click"))
        self._preview_path.setStyleSheet(
            "color:#8b949e;font-size:11px;padding:4px 8px;"
            "background:#161b22;border-radius:4px;"
        )
        preview_lay.addWidget(self._preview_path)

        self._preview_output = QTextBrowser()
        self._preview_output.setReadOnly(True)
        self._preview_output.setStyleSheet(
            "QTextBrowser{background:#0d1117;border:1px solid #21262d;border-radius:4px;"
            "font-family:'Consolas','Courier New',monospace;font-size:12px;"
            "color:#c9d1d9;padding:8px;}"
        )
        preview_lay.addWidget(self._preview_output)

        right_tabs.addTab(preview_tab, _t("tab_preview"))

        # ── Tool Calls tab ──
        tool_tab = QWidget()
        tool_lay = QVBoxLayout(tool_tab)
        tool_lay.setContentsMargins(0, 0, 0, 0)
        self._tool_panel = ToolCallPanel()
        tool_lay.addWidget(self._tool_panel)
        right_tabs.addTab(tool_tab, _t("tab_tools"))

        right_lay.addWidget(right_tabs)

        # ── Assemble splitter ──
        main_sp.addWidget(sidebar)
        main_sp.addWidget(center)
        main_sp.addWidget(right_panel)
        main_sp.setSizes([220, 600, 320])
        main_sp.setStretchFactor(0, 0)
        main_sp.setStretchFactor(1, 1)
        main_sp.setStretchFactor(2, 0)

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
        dlg.setWindowTitle(_t("settings_title"))
        dlg.setMinimumSize(520, 520)
        dlg.setStyleSheet("QDialog{background:#0d1117;}")

        layout = QVBoxLayout(dlg)
        layout.setSpacing(12)

        title = QLabel(_t("settings_heading"))
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
        lf.addRow(_t("settings_api_key"), _api_key)

        _model = QComboBox()
        _model.setEditable(True)
        for i in range(self._model_combo.count()):
            _model.addItem(self._model_combo.itemText(i), self._model_combo.itemData(i))
        _model.setCurrentText(self._model_combo.currentText())
        lf.addRow(_t("settings_model"), _model)

        _base_url = QLineEdit()
        _base_url.setPlaceholderText("API Base URL (如需要)")
        _base_url.setText(self._base_url_input.text())
        lf.addRow(_t("settings_base_url"), _base_url)

        _show_key = QCheckBox(_t("settings_show_key"))
        _show_key.toggled.connect(
            lambda chk: _api_key.setEchoMode(
                QLineEdit.EchoMode.Normal if chk else QLineEdit.EchoMode.Password
            )
        )
        lf.addRow("", _show_key)
        form.addWidget(llm_g)

        # ── Advanced ──
        ad_g = QGroupBox(_t("settings_advanced"))
        ad_g.setStyleSheet(llm_g.styleSheet())
        af = QFormLayout(ad_g)
        af.setSpacing(6)

        _rounds = QSpinBox()
        _rounds.setRange(5, 100)
        _rounds.setValue(self._max_rounds_spin.value())
        af.addRow(_t("settings_max_rounds"), _rounds)

        _auto_allow = QCheckBox(_t("settings_auto_allow"))
        _auto_allow.setChecked(self._auto_allow_cb.isChecked())
        af.addRow("", _auto_allow)

        _auto_inject = QCheckBox(_t("settings_auto_inject"))
        _auto_inject.setChecked(self._auto_inject_cb.isChecked())
        af.addRow("", _auto_inject)

        _test_verify = QCheckBox(_t("settings_test_verify"))
        _test_verify.setChecked(self._test_verify_cb.isChecked())
        af.addRow("", _test_verify)

        _git_commit = QCheckBox(_t("settings_git_commit"))
        _git_commit.setChecked(self._git_commit_cb.isChecked())
        af.addRow("", _git_commit)

        _plan_mode = QCheckBox(_t("settings_plan_mode"))
        _plan_mode.setChecked(self._plan_mode_cb.isChecked())
        af.addRow("", _plan_mode)

        _lang = QComboBox()
        _lang.addItem("中文", "zh")
        _lang.addItem("English", "en")
        current_lang = get_language()
        idx = _lang.findData(current_lang)
        if idx >= 0:
            _lang.setCurrentIndex(idx)
        af.addRow(_t("settings_language"), _lang)
        form.addWidget(ad_g)

        # ── Extra Prompt ──
        ex_g = QGroupBox(_t("settings_extra_prompt"))
        ex_g.setStyleSheet(llm_g.styleSheet())
        ex_lay = QVBoxLayout(ex_g)
        _extra = QPlainTextEdit()
        _extra.setPlaceholderText(_t("extra_prompt_placeholder"))
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
        cancel_btn = QPushButton(_t("btn_cancel"))
        cancel_btn.setStyleSheet(
            "QPushButton{background:#21262d;color:#c9d1d9;border:1px solid #30363d;"
            "border-radius:6px;padding:8px 20px;font-size:13px;}"
            "QPushButton:hover{background:#30363d;}"
        )
        cancel_btn.clicked.connect(dlg.reject)
        btn_bar.addWidget(cancel_btn)

        ok_btn = QPushButton(_t("btn_save"))
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
            self._lang_combo.setCurrentIndex(_lang.currentIndex())
            self._update_provider_fields()
            self._save_settings()
            self._sync_env_file()
            # Apply language change
            new_lang = _lang.currentData()
            if new_lang != get_language():
                set_language(new_lang)
                QMessageBox.information(
                    dlg, _t("settings_heading"),
                    "语言已切换，重启应用后完全生效。\nLanguage changed. Restart to apply fully."
                )

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
            "GANGGE_LANG": self._lang_combo.currentData(),
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
        self._tool_panel.clear_entries()
        ws = self._ws_input.text().strip()
        sid = self._db.create_session(_t("session_new"), ws)
        self._current_session_id = sid
        self._refresh_session_list()
        # Select the new session in the list
        for i in range(self._session_list.count()):
            item = self._session_list.item(i)
            if item and item.data(Qt.ItemDataRole.UserRole) == sid:
                self._session_list.setCurrentItem(item)
                break
        self._status_label.setText(_t("status_new_session", sid=sid))

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
            sep = QListWidgetItem(_t("session_count", n=len(sessions)))
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
            hint = _t("session_load_with_hint", total=total, max=self._db.MAX_LOAD_MESSAGES)
            self._append_output(_t("session_load", name=item.text()) + f"\n{hint}\n", "system")
        else:
            self._append_output(_t("session_load_count", name=item.text(), total=total) + "\n", "system")
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
        self._tool_panel.clear_entries()
        calls = self._db.load_tool_calls(sid)
        for c in calls:
            self._tool_panel.add_entry(c["tool_name"], c["output"][:200], c["is_error"], c["diff"])

        # Restore session workspace if set
        sess = self._db.get_session(sid)
        if sess and sess["workspace"]:
            old_ws = self._ws_input.text().strip()
            if sess["workspace"] != old_ws:
                self._ws_input.setText(sess["workspace"])
                self._file_browser.set_root(sess["workspace"])
                self._refresh_session_list()  # 工作目录变了 → 刷新会话列表

        self._status_label.setText(_t("status_session", title=sess['title'] if sess else sid))

    def _delete_session(self):
        item = self._session_list.currentItem()
        if not item:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        if QMessageBox.question(self, _t("session_confirm_delete"), _t("session_delete_msg", name=item.text()), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self._db.delete_session(sid)
            if self._current_session_id == sid:
                self._current_session_id = ""
                self._clear_output()
                self._tool_panel.clear_entries()
            self._refresh_session_list()

    def _rename_session(self):
        item = self._session_list.currentItem()
        if not item:
            return
        sid = item.data(Qt.ItemDataRole.UserRole)
        title = item.data(Qt.ItemDataRole.UserRole + 1)
        new_title, ok = QInputDialog.getText(self, _t("session_rename"), _t("session_rename_label"), text=title)
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

    # ── Input auto-resize & Enter handling ──────────────────
    def _auto_resize_input(self):
        doc = self._task_input.document()
        h = int(doc.size().height()) + 16
        h = max(36, min(h, 100))
        self._task_input.setFixedHeight(h)

    def eventFilter(self, obj, event):
        if obj == self._task_input and event.type() == event.Type.KeyPress:
            from PyQt6.QtCore import QEvent
            from PyQt6.QtGui import QKeyEvent
            ke = event
            # Shift+Enter = insert newline
            if ke.key() == Qt.Key.Key_Return and ke.modifiers() == Qt.KeyboardModifier.ShiftModifier:
                cursor = self._task_input.textCursor()
                cursor.insertText("\n")
                return True
            # Ctrl+Enter or plain Enter (single line) = run
            if ke.key() == Qt.Key.Key_Return:
                if ke.modifiers() == Qt.KeyboardModifier.ControlModifier:
                    self._run_task()
                    return True
                # If single line (no newline in text), Enter runs
                text = self._task_input.toPlainText()
                if "\n" not in text:
                    self._run_task()
                    return True
                # Multi-line: Enter inserts newline (like Shift+Enter)
                cursor = self._task_input.textCursor()
                cursor.insertText("\n")
                return True
        return super().eventFilter(obj, event)

    # ── Actions ───────────────────────────────────────────────
    def _clear_output(self):
        self._output.clear()

    def _rollback_checkpoint(self):
        from PyQt6.QtWidgets import QMessageBox
        workspace = self._ws_input.text().strip()
        if not workspace:
            self._status_label.setText(_t("status_no_workspace"))
            return
        from gangge.layer4_tools.shadow_git import ShadowGit
        sg = ShadowGit(workspace)
        if not sg.is_available():
            self._status_label.setText(_t("status_no_git"))
            return
        checkpoints = sg.list_checkpoints(limit=10)
        gangge_cps = [c for c in checkpoints if c.get("is_checkpoint")]
        if not gangge_cps:
            self._status_label.setText(_t("status_no_checkpoint"))
            return
        items = [f"{c['hash']} — {c['date'][:16]} {c['message']}" for c in gangge_cps[:8]]
        item, ok = QInputDialog.getItem(
            self, _t("rollback_title"), _t("rollback_select"),
            items, 0, False,
        )
        if not ok or not item:
            return
        selected_hash = item.split(" ")[0]
        reply = QMessageBox.warning(
            self, _t("rollback_confirm"),
            _t("rollback_confirm_msg", hash=selected_hash),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if sg.rollback(selected_hash):
            self._append_output(_t("rollback_done", hash=selected_hash), "system")
            self._file_browser.set_root(workspace)
            self._status_label.setText(_t("status_rollback_ok_hash", hash=selected_hash))
        else:
            self._status_label.setText(_t("status_rollback_fail"))

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

    def _on_file_selected(self, file_path: str):
        try:
            p = Path(file_path)
            if not p.exists() or not p.is_file():
                return
            size_kb = p.stat().st_size / 1024
            ext = p.suffix.lower()
            image_exts = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".webp"}
            binary_exts = {".exe", ".dll", ".so", ".pyc", ".pyd", ".zip", ".tar", ".gz", ".rar", ".7z", ".pdf", ".doc", ".docx", ".xlsx", ".pptx", ".db", ".sqlite"}

            self._preview_path.setText(f"📄 {p.name} ({size_kb:.1f} KB)")

            if ext in binary_exts:
                self._preview_output.setPlainText(f"[二进制文件] {file_path}\n大小: {size_kb:.1f} KB")
                return
            if ext in image_exts:
                self._preview_output.setPlainText(f"[图片文件] {file_path}\n大小: {size_kb:.1f} KB")
                return
            if size_kb > 500:
                self._preview_output.setPlainText(f"[文件过大] {file_path}\n大小: {size_kb:.1f} KB\n请使用 read_file 工具读取")
                return

            content = p.read_text(encoding="utf-8", errors="replace")
            lines = content.splitlines()
            total = len(lines)
            max_show = 500
            shown = lines[:max_show]
            truncated = total > max_show

            numbered = "\n".join(f"{i+1:>5}│ {line}" for i, line in enumerate(shown))
            if truncated:
                numbered += f"\n\n... 省略 {total - max_show} 行 (共 {total} 行)"

            self._preview_output.setPlainText(numbered)
        except Exception as e:
            self._preview_output.setPlainText(f"读取失败: {e}")

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
        self._btn_run.setVisible(False)
        self._batch_btn.setEnabled(False)
        self._btn_stop.setVisible(True)
        self._btn_cancel.setEnabled(True)
        self._task_input.setEnabled(False)
        self._status_progress.setVisible(True)
        self._status_progress.setRange(0, 0)
        self._stats_label.setText("")
        self._timer_label.setText("⏱ 00:00")

        # Start elapsed timer
        self._start_time = time.monotonic()
        from PyQt6.QtCore import QTimer
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._update_elapsed)
        self._elapsed_timer.start(1000)

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
        self._worker.ask_user_sig.connect(self._on_ask_user)
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

    def _update_elapsed(self):
        if hasattr(self, "_start_time"):
            elapsed = int(time.monotonic() - self._start_time)
            mins, secs = divmod(elapsed, 60)
            self._timer_label.setText(f"⏱ {mins:02d}:{secs:02d}")

    def _on_finished(self, summary: dict, llm: BaseLLM | None):
        self._running = False
        self._btn_run.setVisible(True)
        self._btn_stop.setVisible(False)
        self._batch_btn.setEnabled(True)
        self._btn_cancel.setEnabled(False)
        self._task_input.setEnabled(True)
        self._status_progress.setVisible(False)
        self._status_progress.setRange(0, 100)
        self._status_progress.setValue(0)

        # Stop elapsed timer
        if hasattr(self, "_elapsed_timer") and self._elapsed_timer:
            self._elapsed_timer.stop()

        # Enable rollback button if checkpoint exists
        has_checkpoint = bool(summary and summary.get("shadow_checkpoint_before"))
        self._btn_rollback.setEnabled(has_checkpoint)

        # Update final stats
        if summary and not summary.get("error"):
            r = summary.get("rounds", 0)
            c = summary.get("tool_calls", 0)
            tokens = summary.get("tokens", {})
            inp = tokens.get("input", 0)
            out = tokens.get("output", 0)
            cost = summary.get("cost", "")
            cost_str = f" | {cost}" if cost else ""
            self._stats_label.setText(f"🔄 {r} 轮 | 🔧 {c} 次 | 📥 {inp} | 📤 {out}{cost_str}")

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

    def _on_ask_user(self, question: str):
        answer, ok = QInputDialog.getText(
            self, "AI 需要你的输入", question,
        )
        if ok:
            self._worker._ask_user_answer = answer.strip()
        else:
            self._worker._ask_user_answer = ""
        self._worker._ask_user_event.set()

    def _on_tool_call(self, tool_name: str, output: str, is_error: bool, diff: str):
        self._tool_panel.add_entry(tool_name, output, is_error, diff)
        # Persist to DB
        if self._current_session_id:
            self._db.save_tool_call(
                self._current_session_id,
                round_num=self._tool_panel._table.rowCount(),
                tool_name=tool_name,
                tool_input="",
                tool_output=output,
                is_error=is_error,
                diff=diff,
            )

    def _append_output(self, text: str, role: str = ""):
        """Render message as a styled bubble card."""
        cursor = self._output.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        # ── Bubble styling by role ──
        bubble_cfg = {
            "user": {
                "icon": "👤",
                "title": "你",
                "bg": "#1f2937",
                "border": "#374151",
                "text_color": "#e5e7eb",
                "align": "left",
            },
            "assistant": {
                "icon": "🤖",
                "title": "AI",
                "bg": "#111827",
                "border": "#1f6feb",
                "text_color": "#c9d1d9",
                "align": "left",
            },
            "tool": {
                "icon": "🔧",
                "title": "工具",
                "bg": "#1a1500",
                "border": "#d29922",
                "text_color": "#d29922",
                "align": "left",
            },
            "system": {
                "icon": "ℹ️",
                "title": "系统",
                "bg": "#0d1117",
                "border": "#30363d",
                "text_color": "#8b949e",
                "align": "center",
            },
            "error": {
                "icon": "❌",
                "title": "错误",
                "bg": "#3a1b1b",
                "border": "#f85149",
                "text_color": "#f85149",
                "align": "left",
            },
        }.get(role, {
            "icon": "",
            "title": "",
            "bg": "#0d1117",
            "border": "#30363d",
            "text_color": "#c9d1d9",
            "align": "left",
        })

        cfg = bubble_cfg
        escaped = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        # Code block handling with syntax highlighting hints
        lines = escaped.split("\n")
        parts = []
        in_code = False
        code_lang = ""
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("```"):
                if in_code:
                    parts.append("</code></pre>")
                    in_code = False
                    code_lang = ""
                else:
                    code_lang = stripped[3:].strip()
                    lang_label = f'<div style="color:#8b949e;font-size:11px;padding:2px 8px;background:#161b22;border-bottom:1px solid #30363d;">{code_lang}</div>' if code_lang else ""
                    parts.append(f'{lang_label}<pre style="background:#161b22;padding:8px 12px;margin:4px 0;border-radius:4px;overflow-x:auto;"><code style="color:#c9d1d9;font-family:Consolas,monospace;font-size:12px;line-height:1.5;">')
                    in_code = True
                continue
            if in_code:
                parts.append(line + "\n")
            elif line == "":
                parts.append("<br>")
            else:
                # Inline code `...`
                import re
                line = re.sub(r'`([^`]+)`', r'<code style="background:#161b22;padding:1px 4px;border-radius:3px;color:#79c0ff;font-family:Consolas,monospace;font-size:12px;">\1</code>', line)
                # Bold **...**
                line = re.sub(r'\*\*([^*]+)\*\*', r'<strong style="color:#f0f6fc;">\1</strong>', line)
                parts.append(line + "<br>")
        if in_code:
            parts.append("</code></pre>")

        content_html = "".join(parts)

        # Build bubble HTML
        if role == "system" and not text.strip().startswith("📋"):
            # Compact system messages (dividers, separators)
            bubble_html = (
                f'<div style="text-align:center;margin:6px 0;">'
                f'<span style="color:#484f58;font-size:12px;">{content_html}</span>'
                f'</div>'
            )
        else:
            margin = "margin:8px 40px 8px 8px;" if cfg["align"] == "left" else "margin:8px;"
            bubble_html = (
                f'<div style="{margin}padding:10px 14px;background:{cfg["bg"]};'
                f'border:1px solid {cfg["border"]};border-radius:10px;'
                f'border-left:3px solid {cfg["border"]};">'
                f'<div style="font-size:11px;color:#8b949e;margin-bottom:4px;">'
                f'{cfg["icon"]} <strong style="color:{cfg["text_color"]};">{cfg["title"]}</strong>'
                f'<span style="float:right;color:#484f58;">{datetime.now().strftime("%H:%M")}</span>'
                f'</div>'
                f'<div style="color:{cfg["text_color"]};font-size:13px;line-height:1.6;">'
                f'{content_html}</div></div>'
            )

        cursor.insertHtml(bubble_html)
        self._output.setTextCursor(cursor)
        self._output.ensureCursorVisible()

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
        self._settings.setValue("language", self._lang_combo.currentData())
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
        lang = self._settings.value("language", "")
        if lang:
            idx = self._lang_combo.findData(lang)
            if idx >= 0:
                self._lang_combo.setCurrentIndex(idx)
                set_language(lang)
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
