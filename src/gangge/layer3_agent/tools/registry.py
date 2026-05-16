"""Tool registry — manage all available tools."""

from __future__ import annotations

import logging
from typing import Any, Callable, Awaitable

from gangge.layer3_agent.tools.base import BaseTool, ToolResult
from gangge.layer5_llm.base import ToolDefinition

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry of all available tools."""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """Register a tool."""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        """Unregister a tool by name."""
        self._tools.pop(name, None)

    def get(self, name: str) -> BaseTool | None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[BaseTool]:
        """List all registered tools."""
        return list(self._tools.values())

    def get_definitions(self) -> list[ToolDefinition]:
        """Get tool definitions for LLM API."""
        return [tool.to_definition() for tool in self._tools.values()]

    async def execute(self, name: str, input_data: dict[str, Any]) -> ToolResult:
        """Execute a tool by name with given input."""
        tool = self.get(name)
        if not tool:
            return ToolResult(output=f"未知工具: {name}", is_error=True)
        return await tool.safe_execute(**input_data)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools


def create_tool_registry(
    workspace: str = "",
    ask_user_callback: Callable[[str], Awaitable[str]] | None = None,
    load_plugins: bool = True,
) -> ToolRegistry:
    """Create a ToolRegistry with all built-in tools registered.

    This is the single source of truth for which tools are available.
    Both CLI and GUI call this function — no duplicated registration logic.
    """
    from gangge.layer3_agent.tools.bash import BashTool
    from gangge.layer3_agent.tools.file_ops import ReadFileTool, WriteFileTool, EditFileTool
    from gangge.layer3_agent.tools.search import GrepTool, GlobTool, ListDirTool
    from gangge.layer3_agent.tools.web import WebFetchTool
    from gangge.layer3_agent.tools.ask_user import AskUserTool
    from gangge.layer3_agent.tools.lint_check import LintCheckTool
    from gangge.layer3_agent.tools.create_tool import CreateToolTool

    registry = ToolRegistry()

    registry.register(BashTool(workspace=workspace))
    registry.register(ReadFileTool(workspace=workspace))
    registry.register(WriteFileTool(workspace=workspace))
    registry.register(EditFileTool(workspace=workspace))
    registry.register(LintCheckTool(workspace=workspace))
    for cls in [GrepTool, GlobTool, ListDirTool, WebFetchTool]:
        registry.register(cls())

    registry.register(AskUserTool(ask_callback=ask_user_callback))

    create_tool = CreateToolTool(workspace=workspace, registry=registry)
    registry.register(create_tool)

    if load_plugins and workspace:
        from gangge.layer4_tools.plugin_loader import load_plugins as _load_plugins
        loaded = _load_plugins(workspace, registry)
        if loaded:
            logger.info("[Registry] loaded %d plugins: %s", len(loaded), loaded)

    return registry
