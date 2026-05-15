"""Agentic Loop — the core engine of the AI assistant.

Implements the Plan & Execute pattern:
1. Send messages to LLM
2. If tool_use → check permission → execute → add result → loop
3. If end_turn → return final response
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Awaitable

from gangge.layer3_agent.tools.registry import ToolRegistry
from gangge.layer3_agent.tools.base import ToolResult
from gangge.layer3_agent.prompts.system import build_system_prompt, detect_empty_workspace
from gangge.layer3_agent.progress_emitter import ProgressEmitter, EventType
from gangge.i18n import t
from gangge.layer4_tools.mcp_client import MCPClientManager
from gangge.layer4_permission.guard import (
    PermissionGuard,
    PermissionDecision,
    PermissionRequest,
)
from gangge.layer5_llm.base import (
    BaseLLM,
    ContentBlock,
    ContentType,
    LLMResponse,
    Message,
    Role,
)

logger = logging.getLogger(__name__)


class TurnBuffer:
    """
    方案C：单轮对话暂存区。
    收集 LLM 文字输出、tool_use、tool_result，
    聚合成标准 LLM 消息格式供存入 DB。
    """

    def __init__(self):
        self.text_parts: list[str] = []
        self.tool_uses: list[dict] = []
        self.tool_results: list[dict] = []

    def add_text(self, text: str):
        self.text_parts.append(text)

    def add_tool_use(self, tool_use_id: str, tool_name: str, tool_input: dict):
        self.tool_uses.append({
            "type": "tool_use",
            "id": tool_use_id,
            "name": tool_name,
            "input": tool_input,
        })

    def add_tool_result(self, tool_use_id: str, output: str, is_error: bool = False):
        self.tool_results.append({
            "role": "tool",
            "tool_use_id": tool_use_id,
            "content": output,
            "is_error": is_error,
        })

    def to_db_messages(self) -> list[dict]:
        """聚合成标准 LLM 消息格式。"""
        content = []
        full_text = "".join(self.text_parts).strip()
        if full_text:
            content.append({"type": "text", "text": full_text})
        content.extend(self.tool_uses)

        messages = []
        if content:
            messages.append({"role": "assistant", "content": content})
        messages.extend(self.tool_results)
        return messages

    def is_empty(self) -> bool:
        return not self.text_parts and not self.tool_uses and not self.tool_results


@dataclass
class LoopConfig:
    """Configuration for the agentic loop."""

    max_tool_rounds: int = 30        # Max tool-call iterations (可在 .env 中通过 MAX_ROUNDS 覆盖)
    max_tokens: int = 8192
    system_prompt: str = ""
    workspace_dir: str = "."
    project_context: str = ""
    plan_mode: bool = False

    # ── Project map: file index injected into system prompt ──
    project_map: str = ""

    # ── File registry: tracks all file modifications ──
    file_registry: dict[str, dict] = field(default_factory=dict)
    # {"src/main.py": {"classes":["App"],"functions":["main"],"last_action":"write","round":5}}

    # ── Summary compression: auto-compress old rounds ──
    enable_summary_compression: bool = True
    summary_compression_interval: int = 5  # every N rounds

    # ── Sliding window: keep only recent N rounds, discard older ──
    enable_sliding_window: bool = True
    max_history_rounds: int = 6  # only keep recent N user/assistant pairs

    # ── Tool result truncation ──
    enable_tool_result_truncation: bool = True
    tool_result_max_chars: int = 2000

    # ── Lazy project map: only inject full index on first round ──
    enable_lazy_project_map: bool = True

    # ── Memory Bank: project-level progress tracking ──
    memory_bank_progress: str = ""
    memory_bank_changelog: str = ""
    memory_bank_decisions: str = ""

    # ── .ganggerules: project-specific rules ──
    ganggerules: str = ""

    # ── ask_user callback: pause loop and wait for user input ──
    ask_user_callback: Callable[[str], Awaitable[str]] | None = None


@dataclass
class ToolExecution:
    """Record of a single tool execution."""

    tool_name: str
    input: dict[str, Any]
    output: str
    is_error: bool = False
    permission: str = ""  # "auto" | "allowed" | "denied"
    metadata: dict[str, Any] = field(default_factory=dict)  # e.g. {"diff": "...", "before_content": "..."}


@dataclass
class LoopResult:
    """Result of the agentic loop."""

    final_response: str
    tool_executions: list[ToolExecution] = field(default_factory=list)
    total_rounds: int = 0
    total_tokens: dict[str, int] = field(default_factory=dict)
    extra: dict[str, str] = field(default_factory=dict)  # e.g. {"memory_bank_update": "..."}


# Callback types
StreamCallback = Callable[[ContentBlock], Awaitable[None]]


class AgenticLoop:
    """The core agentic loop engine.

    Orchestrates LLM calls, tool executions, and permission checks.
    """

    def __init__(
        self,
        llm: BaseLLM,
        tools: ToolRegistry,
        permission_guard: PermissionGuard,
        config: LoopConfig | None = None,
    ):
        self.llm = llm
        self.tools = tools
        self.guard = permission_guard
        self.config = config or LoopConfig()
        self._stream_callback: StreamCallback | None = None
        # ── Progress Emitter ──
        self.emitter = ProgressEmitter()
        self._text_callback: Callable[[ContentBlock], None] | None = None
        # ── PATCH: MCP Client Manager ──
        self.mcp_manager: MCPClientManager | None = None
        self._init_mcp()

    def set_stream_callback(self, callback: StreamCallback) -> None:
        """Set callback for streaming content blocks."""
        self._stream_callback = callback

    def set_text_callback(self, callback: Callable[[ContentBlock], None]) -> None:
        """Set a synchronous text callback for progress messages."""
        self._text_callback = callback

    def _init_mcp(self):
        """初始化 MCP 客户端管理器（连接外部工具服务器）。"""
        ws = Path(self.config.workspace_dir) if self.config.workspace_dir else Path(".")
        config_path = ws / ".gangge" / "mcp_servers.json"
        try:
            self.mcp_manager = MCPClientManager.from_config_file(str(config_path))
            self.mcp_manager.connect_all()
            tools = self.mcp_manager.get_all_tools()
            if tools:
                names = [t.full_name for t in tools]
                logger.info(f"[MCP] 已加载 {len(tools)} 个外部工具: {', '.join(names)}")
        except Exception as e:
            logger.info(f"[MCP] 初始化跳过: {e}")
            self.mcp_manager = None

    def _ensure_memory_bank(self) -> None:
        """Auto-load memory bank files from .gangge/ directory.

        Reads progress.md, changelog.md, and decisions.md into config fields
        so they get injected into the system prompt.
        """
        gangge_dir = Path(self.config.workspace_dir) / ".gangge"
        progress_file = gangge_dir / "progress.md"
        changelog_file = gangge_dir / "changelog.md"
        decisions_file = gangge_dir / "decisions.md"

        # Create .gangge/ with defaults if missing
        if not gangge_dir.exists():
            gangge_dir.mkdir(parents=True, exist_ok=True)
        if not progress_file.exists():
            progress_file.write_text(t("memory_progress_title"), encoding="utf-8")
        if not changelog_file.exists():
            changelog_file.write_text(t("memory_changelog_title"), encoding="utf-8")
        if not decisions_file.exists():
            decisions_file.write_text(t("memory_decisions_title"), encoding="utf-8")

        # Read content
        try:
            self.config.memory_bank_progress = progress_file.read_text(encoding="utf-8").strip()
        except Exception:
            self.config.memory_bank_progress = ""
        try:
            self.config.memory_bank_changelog = changelog_file.read_text(encoding="utf-8").strip()
        except Exception:
            self.config.memory_bank_changelog = ""
        try:
            self.config.memory_bank_decisions = decisions_file.read_text(encoding="utf-8").strip()
        except Exception:
            self.config.memory_bank_decisions = ""

    def _save_memory_bank_update(self, update_text: str) -> None:
        """Save memory bank update text to .gangge/ files.

        Parses the LLM's memory-bank block and writes to progress.md, changelog.md, and decisions.md.
        """
        if not update_text.strip():
            return
        gangge_dir = Path(self.config.workspace_dir) / ".gangge"
        progress_file = gangge_dir / "progress.md"
        changelog_file = gangge_dir / "changelog.md"
        decisions_file = gangge_dir / "decisions.md"

        # Try to extract progress, changelog, and decisions sections from the update
        import re as _re
        progress_match = _re.search(r"(?:progress|进度)[：:]\s*(.+?)(?=(?:changelog|变更日志|decision|决策)[：:]|$)", update_text, _re.IGNORECASE | _re.DOTALL)
        changelog_match = _re.search(r"(?:changelog|变更日志)[：:]\s*(.+?)(?=(?:decision|决策)[：:]|$)", update_text, _re.IGNORECASE | _re.DOTALL)
        decisions_match = _re.search(r"(?:decision|决策)[：:]\s*(.+?)$", update_text, _re.IGNORECASE | _re.DOTALL)

        if progress_match:
            new_progress = progress_match.group(1).strip()
            if new_progress:
                try:
                    progress_file.write_text(f"# 项目进度\n\n{new_progress}\n", encoding="utf-8")
                    self.config.memory_bank_progress = new_progress
                    logger.info(f"[Memory Bank] progress.md 已更新")
                except Exception as e:
                    logger.warning(f"[Memory Bank] 写入 progress.md 失败: {e}")

        if changelog_match:
            new_changelog = changelog_match.group(1).strip()
            if new_changelog:
                new_entry = f"\n## {datetime.now().strftime('%Y-%m-%d')}\n{new_changelog}\n"
                try:
                    existing = changelog_file.read_text(encoding="utf-8") if changelog_file.exists() else ""
                    changelog_file.write_text(existing + new_entry, encoding="utf-8")
                    self.config.memory_bank_changelog = new_changelog
                    logger.info(f"[Memory Bank] changelog.md 已更新")
                except Exception as e:
                    logger.warning(f"[Memory Bank] 写入 changelog.md 失败: {e}")

        if decisions_match:
            new_decision = decisions_match.group(1).strip()
            if new_decision:
                new_entry = f"\n### {datetime.now().strftime('%Y-%m-%d %H:%M')}\n{new_decision}\n"
                try:
                    existing = decisions_file.read_text(encoding="utf-8") if decisions_file.exists() else ""
                    decisions_file.write_text(existing + new_entry, encoding="utf-8")
                    self.config.memory_bank_decisions = (existing + new_entry).strip()
                    logger.info(f"[Memory Bank] decisions.md 已更新")
                except Exception as e:
                    logger.warning(f"[Memory Bank] 写入 decisions.md 失败: {e}")

    def _get_all_tool_defs(self) -> list:
        """获取内置工具 + MCP 工具的完整 definitions 列表。"""
        defs = list(self.tools.get_definitions())
        if self.mcp_manager:
            mcp_defs = self.mcp_manager.build_tool_definitions()
            defs.extend(mcp_defs)
        return defs

    def _build_system_prompt(self, reads_cache: dict[str, int] | None = None, round_num: int = 0) -> str:
        prompt = build_system_prompt(
            workspace_dir=self.config.workspace_dir,
            project_context=self.config.project_context,
            plan_mode=self.config.plan_mode,
            memory_bank_progress=self.config.memory_bank_progress,
            memory_bank_changelog=self.config.memory_bank_changelog,
            memory_bank_decisions=self.config.memory_bank_decisions,
        )

        # ── Inject .ganggerules ──
        if self.config.ganggerules:
            prompt += f"\n\n## 项目规则 (.ganggerules)\n{self.config.ganggerules}"

        # ── Inject project map (lazy loading) ──
        if self.config.project_map:
            if self.config.enable_lazy_project_map and round_num > 0:
                file_count = self.config.project_map.count("\n") + 1
                prompt += f"\n\n## 项目文件索引\n[项目索引已在第1轮加载，包含约 {file_count} 个条目，如需查看请用 list_dir 工具]"
            else:
                prompt += f"\n\n## 项目文件索引 (请利用这些信息定位文件)\n{self.config.project_map}"

        # ── Inject file registry ──
        if self.config.file_registry:
            lines = ["", "## 已修改的文件记录 (实时更新)"]
            for path, info in sorted(self.config.file_registry.items()):
                action = info.get("last_action", "?")
                rnd = info.get("round", "?")
                detail = ""
                if info.get("classes"):
                    detail += f" classes:{','.join(info['classes'][:5])}"
                if info.get("functions"):
                    detail += f" funcs:{','.join(info['functions'][:8])}"
                lines.append(f"- `{path}` [{action}, 第{rnd}轮]{detail}")
            prompt += "\n".join(lines)

        # ── Inject reads cache (context de-duplication) ──
        if reads_cache:
            prompt += "\n\n## 已读取的文件 (避免重复读取)\n"
            for path, rnd in reads_cache.items():
                prompt += f"- `{path}` (第 {rnd} 轮已读取)\n"
            prompt += "\n如需再次查看，请优先用 grep 搜索特定内容，而非重新 read_file。"

        # ── Memory Bank update instruction ──
        prompt += (
            "\n\n## 任务结束时\n"
            "在最终回复中，请附带以下更新信息（包含在 ```memory-bank 标记中）：\n"
            "1. **progress.md** 更新：新增/完成的模块、当前进度百分比\n"
            "2. **changelog.md** 更新：本次变更摘要、涉及文件列表、风险事项\n"
        )

        return prompt

    def _deduplicate_reads(
        self, messages: list[Message], reads_cache: dict[str, int]
    ) -> list[Message]:
        """Replace repeated file reads with short summaries to save tokens."""
        modified = False
        for i, msg in enumerate(messages):
            if msg.role != Role.TOOL:
                continue
            new_blocks = []
            for block in msg.content:
                if block.type != ContentType.TEXT:
                    new_blocks.append(block)
                    continue
                text = block.text
                # Check if this block contains a repeated file read
                for path, read_round in reads_cache.items():
                    if path in text and len(text) > 200:
                        text = text[:80] + f"\n[文件已在第 {read_round} 轮读取，共 {len(text)} 字符，此处省略]\n"
                        modified = True
                        break
                new_blocks.append(ContentBlock(
                    type=ContentType.TEXT,
                    text=text,
                ) if block.type == ContentType.TEXT else block)
            if modified:
                # Can't easily replace blocks in existing Message,
                # so we update the message's cached text
                pass
        return messages

    async def _compress_history(
        self, messages: list[Message], round_num: int
    ) -> list[Message]:
        """Compress old conversation rounds into a summary.

        CRITICAL: must not split tool_calls/tool message pairs.
        Scans backwards to find a safe split point.
        """
        if len(messages) <= 4:
            return messages

        # Find safe split point: walk backwards, don't split between
        # an assistant(tool_calls) and its following tool messages
        safe_idx = len(messages) - 1
        while safe_idx > 0:
            msg = messages[safe_idx]
            if msg.role == Role.USER:
                break  # USER is always a safe boundary
            if msg.role == Role.ASSISTANT:
                # Check if this assistant has tool_calls
                has_tc = any(b.type == ContentType.TOOL_USE for b in msg.content)
                if not has_tc:
                    break  # Pure text assistant is safe
            # If TOOL role or assistant with tool_calls, keep walking back
            safe_idx -= 1

        # Need at least 2 messages before safe point to make compression worthwhile
        if safe_idx < 2:
            return messages

        history_text = ""
        for msg in messages[:safe_idx]:
            t = msg.get_text()[:500]
            if t.strip():
                history_text += f"[{msg.role.value}]: {t}\n"

        try:
            summary_response = await self.llm.chat(
                messages=[
                    Message(
                        role=Role.USER,
                        content=(
                            "压缩以下对话为一段 150 字以内的摘要，"
                            "保留: 已创建/修改的文件、关键决策、当前进度\n\n"
                            + history_text
                        ),
                    )
                ],
                tools=None,
                system="你是一个对话摘要助手，只输出摘要，不要多余内容。",
            )
            summary = summary_response.text.strip()
            logger.info(f"History compressed at round {round_num}: {len(summary)} chars")
        except Exception as e:
            logger.warning(f"History compression failed: {e}")
            return messages

        # Replace compressed portion with summary, keeping tool pairs intact
        compressed = [
            Message(
                role=Role.SYSTEM,
                content=f"[历史摘要 — 第 {round_num} 轮压缩]\n{summary}",
            )
        ] + messages[safe_idx:]
        return compressed

    def _trim_history(self, messages: list[Message]) -> list[Message]:
        """Sliding window: keep only recent N rounds, discard older messages.

        A "round" is a user/assistant pair (possibly followed by tool messages).
        We count user messages as round boundaries and keep the last N rounds.
        This is simpler and more reliable than summary compression.
        """
        max_rounds = self.config.max_history_rounds

        # Find all USER message indices (these are round boundaries)
        user_indices = []
        for i, msg in enumerate(messages):
            if msg.role == Role.USER:
                user_indices.append(i)

        # If we have fewer rounds than max, no trimming needed
        if len(user_indices) <= max_rounds:
            return messages

        # Find the start index of the (len - max_rounds)-th user message
        # This is where we start keeping messages
        cutoff_idx = user_indices[-max_rounds]

        # But we must not split an assistant(tool_calls) + tool messages pair
        # Walk backwards from cutoff to find a safe boundary
        safe_idx = cutoff_idx
        while safe_idx > 0:
            msg = messages[safe_idx]
            if msg.role == Role.USER:
                break
            if msg.role == Role.ASSISTANT:
                has_tc = any(b.type == ContentType.TOOL_USE for b in msg.content)
                if not has_tc:
                    break
            safe_idx -= 1

        trimmed = messages[safe_idx:]
        dropped = len(messages) - len(trimmed)
        if dropped > 0:
            logger.info(f"Sliding window: dropped {dropped} old messages, keeping {len(trimmed)}")
        return trimmed

    async def _emit(self, block: ContentBlock) -> None:
        """Emit a content block to the stream callback."""
        if self._stream_callback:
            await self._stream_callback(block)

    def _get_permission_action(self, tool_name: str, tool_input: dict) -> str:
        """Extract the action string for permission checking."""
        if tool_name == "bash":
            return tool_input.get("command", "")
        elif tool_name in ("read_file", "write_file", "edit_file"):
            return tool_input.get("path", "")
        return tool_name

    async def _auto_lint_check(self, file_path: str) -> str:
        """Run a quick lint check on a modified file. Returns summary or empty string."""
        try:
            from gangge.layer3_agent.tools.lint_check import LintCheckTool
            checker = LintCheckTool(workspace=self.config.workspace_dir)
            result = await checker.execute(path=file_path)
            if result.is_error:
                return f"[lint] {result.output}"
            return ""
        except Exception:
            return ""

    async def run(self, messages: list[Message]) -> LoopResult:
        """Run the agentic loop until LLM returns end_turn.

        Args:
            messages: Conversation history (will be modified in place).

        Returns:
            LoopResult with final response and execution records.
        """
        # ── PATCH: include MCP tool definitions ──
        # ── Load Memory Bank from .gangge/ files ──
        self._ensure_memory_bank()

        # ── Shadow Git: auto-checkpoint before AI starts ──
        shadow_checkpoint = None
        if self.config.workspace_dir:
            from gangge.layer4_tools.shadow_git import ShadowGit
            sg = ShadowGit(self.config.workspace_dir)
            if sg.is_available() or sg.ensure_init():
                shadow_checkpoint = sg.checkpoint("before AI task")
                if shadow_checkpoint:
                    logger.info(f"Shadow Git checkpoint: {shadow_checkpoint}")

        tool_defs = self._get_all_tool_defs()
        is_empty_dir = detect_empty_workspace(self.config.workspace_dir)
        executions: list[ToolExecution] = []
        total_tokens: dict[str, int] = {"input": 0, "output": 0}
        has_modified_files = False
        file_registry = dict(self.config.file_registry)  # mutable copy
        reads_cache: dict[str, int] = {}  # path -> round_number for de-dup
        memory_bank_update = ""  # extracted from LLM's final response

        for round_num in range(self.config.max_tool_rounds):
            logger.info(f"Agentic loop round {round_num + 1}")

            # ── Emit round indicator ──
            self.emitter.emit(EventType.ROUND, f"第 {round_num + 1} 轮")
            await self._emit(ContentBlock(
                type=ContentType.TEXT,
                text=f"\n[dim]── 第 {round_num + 1} 轮 ──[/dim]\n",
            ))

            # ── Rebuild system prompt with fresh project context ──
            self.config.file_registry = file_registry
            system = self._build_system_prompt(reads_cache=reads_cache, round_num=round_num)
            self.emitter.emit(EventType.THINKING, f"正在思考...")

            # ── Sliding window: trim old messages ──
            if self.config.enable_sliding_window and round_num > 0:
                messages = self._trim_history(messages)

            # ── Summary compression every N rounds (fallback, disabled when sliding window is on) ──
            if (
                not self.config.enable_sliding_window
                and self.config.enable_summary_compression
                and round_num > 0
                and round_num % self.config.summary_compression_interval == 0
            ):
                messages = await self._compress_history(messages, round_num)
                await self._emit(ContentBlock(
                    type=ContentType.TEXT,
                    text=f"\n📦 历史压缩: 第 {round_num} 轮，压缩旧对话以节省上下文\n",
                ))

            # 1. Call LLM (with 120s timeout to prevent hanging)
            await self._emit(ContentBlock(
                type=ContentType.TEXT,
                text="⏳ 等待 AI 回复...\n",
            ))
            try:
                response = await asyncio.wait_for(
                    self.llm.chat(
                        messages=messages,
                        tools=tool_defs,
                        system=system,
                    ),
                    timeout=120.0,
                )
            except asyncio.TimeoutError:
                error_text = "LLM 调用超时（120s），请检查网络或 API 状态"
                logger.error(error_text)
                self.emitter.emit(EventType.ERROR, error_text)
                return LoopResult(
                    final_response=error_text,
                    tool_executions=executions,
                    total_rounds=round_num,
                    total_tokens=total_tokens,
                )
            except Exception as e:
                error_text = f"LLM 调用失败: {e}"
                logger.error(error_text)
                self.emitter.emit(EventType.ERROR, error_text)
                return LoopResult(
                    final_response=error_text,
                    tool_executions=executions,
                    total_rounds=round_num,
                    total_tokens=total_tokens,
                )

            # Track token usage
            total_tokens["input"] += response.usage.get("input_tokens", 0)
            total_tokens["output"] += response.usage.get("output_tokens", 0)

            # 2. Add assistant message to history
            assistant_msg = Message(role=Role.ASSISTANT, content=response.content)
            messages.append(assistant_msg)

            # 3. Stream text content to UI
            for block in response.content:
                if block.type in (ContentType.TEXT, ContentType.THINKING):
                    await self._emit(block)

            # 4. If no tool calls → force retry (rounds 0-2) or exit
            has_tool_call = response.stop_reason == "tool_use" and response.tool_calls
            if not has_tool_call:
                # ── Force tool use on early rounds (0-2) ──
                if round_num <= 2 and not has_modified_files:
                    text = response.text
                    self.emitter.emit(EventType.WARNING,
                                      f"第 {round_num+1} 轮未调用工具，正在强制重试")
                    await self._emit(ContentBlock(
                        type=ContentType.TEXT,
                        text="⚠️ AI 未使用工具，正在强制重试...\n",
                    ))
                    if is_empty_dir:
                        force_msg = (
                            "你刚才只输出了文字，没有调用任何工具。\n\n"
                            "当前工作目录是空的，不需要探索，直接开始构建。\n\n"
                            "请立刻：\n"
                            "1. 输出规划（技术栈 + 模块 + 任务清单）\n"
                            "2. 调用 write_file 或 bash 开始创建第一个文件\n\n"
                            "现在开始，不要再回复纯文字。"
                        )
                    else:
                        force_msg = (
                            "你刚才只输出了文字，没有调用任何工具。\n\n"
                            "这是不允许的。Gangge Code 要求每轮必须调用工具。\n\n"
                            "请立刻重新回复，这次必须：\n"
                            "1. 输出任务规划（模块清单 + 任务清单）\n"
                            "2. 同时调用第一个工具开始执行\n\n"
                            "不要再说 '我来了解一下'，直接行动。"
                        )
                    messages.append(Message(
                        role=Role.USER,
                        content=[ContentBlock(type=ContentType.TEXT, text=force_msg)],
                    ))
                    continue
                # ── Test verification ──
                if has_modified_files:
                    messages.append(Message(
                        role=Role.USER,
                        content=[ContentBlock(
                            type=ContentType.TEXT,
                            text="[系统提示] 检测到文件已被修改。请运行相关测试或检查来验证修改是否正确。如果没有测试，至少运行 lint 或编译检查。",
                        )],
                    ))
                    has_modified_files = False
                    continue
                # ── Extract Memory Bank update from final response ──
                final_text = response.text
                mb_extracted = ""
                if "```memory-bank" in final_text:
                    import re as _re
                    m = _re.search(r"```memory-bank\n(.*?)```", final_text, _re.DOTALL)
                    if m:
                        mb_extracted = m.group(1).strip()
                # ── Save Memory Bank update to files ──
                if mb_extracted:
                    self._save_memory_bank_update(mb_extracted)

                # ── Shadow Git: post-task checkpoint ──
                after_checkpoint = None
                if self.config.workspace_dir and has_modified_files:
                    from gangge.layer4_tools.shadow_git import ShadowGit
                    sg = ShadowGit(self.config.workspace_dir)
                    after_checkpoint = sg.checkpoint("after AI task completed")

                self.emitter.emit_done(total_steps=round_num + 1)
                return LoopResult(
                    final_response=final_text,
                    tool_executions=executions,
                    total_rounds=round_num + 1,
                    total_tokens=total_tokens,
                    extra={
                        "memory_bank_update": mb_extracted,
                        "shadow_checkpoint_before": shadow_checkpoint or "",
                        "shadow_checkpoint_after": after_checkpoint or "",
                    },
                )

            # 5. Process tool calls
            tool_results_msg = Message(role=Role.TOOL)
            await self._emit(ContentBlock(
                type=ContentType.TEXT,
                text=f"🔧 AI 调用了 {len(response.tool_calls)} 个工具:\n",
            ))

            for tool_call in response.tool_calls:
                tool_name = tool_call.name
                tool_input = tool_call.input
                action = self._get_permission_action(tool_name, tool_input)
                self.emitter.emit_tool_start(tool_name, tool_input)

                # Check permission
                perm_result = await self.guard.check(
                    tool_name=tool_name,
                    action=action,
                    context={"input": tool_input},
                )

                if perm_result.decision == PermissionDecision.DENY:
                    tool_results_msg.add_tool_result(
                        call_id=tool_call.id,
                        result=f"权限被拒绝: {perm_result.reason}",
                        is_error=True,
                    )
                    executions.append(ToolExecution(
                        tool_name=tool_name,
                        input=tool_input,
                        output=f"DENIED: {perm_result.reason}",
                        is_error=True,
                        permission="denied",
                    ))
                    self.emitter.emit_tool_end(tool_name, False)
                    continue

                # Execute tool
                import time
                _t0 = time.monotonic()

                # ── Special handling: ask_user ──
                if tool_name == "ask_user":
                    question = tool_input.get("question", "")
                    await self._emit(ContentBlock(
                        type=ContentType.TEXT,
                        text=f"\n[yellow]❓ {question}[/yellow]\n",
                    ))
                    if self.config.ask_user_callback:
                        user_answer = await self.config.ask_user_callback(question)
                    else:
                        user_answer = ""
                    result = ToolResult(
                        output=user_answer if user_answer else "(用户未提供输入)",
                    )
                # ── PATCH: MCP tool dispatch ──
                elif "__" in tool_name and self.mcp_manager:
                    output = self.mcp_manager.call_tool(tool_name, tool_input)
                    result = ToolResult(output=output, is_error=output.startswith("[错误]"))
                else:
                    result = await self.tools.execute(tool_name, tool_input)

                _elapsed = int((time.monotonic() - _t0) * 1000)

                # ── Tool result truncation ──
                result_output = result.output
                if (
                    self.config.enable_tool_result_truncation
                    and len(result_output) > self.config.tool_result_max_chars
                ):
                    result_output = (
                        result_output[:self.config.tool_result_max_chars]
                        + f"\n...[截断，共{len(result_output)}字符]"
                    )

                tool_results_msg.add_tool_result(
                    call_id=tool_call.id,
                    result=result_output,
                    is_error=result.is_error,
                )
                executions.append(ToolExecution(
                    tool_name=tool_name,
                    input=tool_input,
                    output=result.output[:2000],
                    is_error=result.is_error,
                    permission=perm_result.decision.value,
                    metadata=result.metadata,
                ))
                self.emitter.emit_tool_end(tool_name, not result.is_error, _elapsed)

                # ── Track file reads for context de-duplication ──
                if tool_name == "read_file" and not result.is_error:
                    path = tool_input.get("path", "")
                    if path and path not in reads_cache:
                        reads_cache[path] = round_num + 1

                # ── Track file modifications in file registry ──
                if tool_name in ("write_file", "edit_file") and not result.is_error:
                    path = tool_input.get("path", "")
                    has_modified_files = True

                    # ── Auto lint check after file modification ──
                    lint_result = await self._auto_lint_check(path)
                    if lint_result:
                        result_output += f"\n\n{lint_result}"

                    if path:
                        # Scan file for classes/functions
                        try:
                            p = Path(path)
                            if p.exists():
                                text = p.read_text(encoding="utf-8", errors="replace")
                                classes: list[str] = []
                                functions: list[str] = []
                                for line in text.splitlines():
                                    s = line.strip()
                                    if s.startswith("class ") and ":" in s:
                                        name = s.split("(")[0].replace("class ", "").replace(":", "").strip()
                                        classes.append(name)
                                    elif s.startswith(("def ", "async def ")):
                                        name = s.replace("async def ", "").replace("def ", "").split("(")[0].strip()
                                        functions.append(name)
                                file_registry[path] = {
                                    "classes": classes[:10],
                                    "functions": functions[:15],
                                    "last_action": tool_name,
                                    "round": round_num + 1,
                                }
                        except Exception:
                            file_registry[path] = {
                                "last_action": tool_name,
                                "round": round_num + 1,
                            }

                # Emit tool result info
                status = "✓" if not result.is_error else "✗"
                # ── PATCH: MCP tool display ──
                display_name = tool_name
                if "__" in tool_name:
                    server, name = tool_name.split("__", 1)
                    display_name = f"[MCP:{server}] {name}"
                # ──────────────────────────────
                await self._emit(ContentBlock(
                    type=ContentType.TEXT,
                    text=f"  {status} {display_name}: {result.output[:100]}...\n",
                ))

            messages.append(tool_results_msg)

        self.emitter.emit(EventType.WARNING, "达到最大工具调用轮数限制")
        return LoopResult(
            final_response="[达到最大工具调用轮数限制]",
            tool_executions=executions,
            total_rounds=self.config.max_tool_rounds,
            total_tokens=total_tokens,
        )
