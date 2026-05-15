"""Tool registry — manage all available tools."""

from __future__ import annotations

from typing import Any

from gangge.layer3_agent.tools.base import BaseTool, ToolResult
from gangge.layer5_llm.base import ToolDefinition


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
