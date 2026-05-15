"""Web tools — web search and fetch."""

from __future__ import annotations

import aiohttp
from typing import Any

from gangge.layer3_agent.tools.base import BaseTool, ToolResult


class WebFetchTool(BaseTool):
    """Fetch content from a URL."""

    @property
    def name(self) -> str:
        return "web_fetch"

    @property
    def description(self) -> str:
        return "获取指定 URL 的网页内容并转换为纯文本。用于查阅文档、获取 API 信息等。"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要获取的 URL",
                },
                "max_length": {
                    "type": "integer",
                    "description": "返回内容的最大字符数，默认 10000",
                    "default": 10000,
                },
            },
            "required": ["url"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        url = kwargs["url"]
        max_length = kwargs.get("max_length", 10000)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=15),
                    headers={"User-Agent": "GanggeBot/1.0"},
                    follow_redirects=True,
                ) as resp:
                    if resp.status != 200:
                        return ToolResult(
                            output=f"HTTP {resp.status}: {url}",
                            is_error=True,
                        )
                    content_type = resp.headers.get("Content-Type", "")
                    if "text/html" not in content_type and "text/plain" not in content_type:
                        return ToolResult(
                            output=f"不支持的类型: {content_type}",
                            is_error=True,
                        )

                    text = await resp.text(errors="replace")
                    # Simple HTML tag stripping
                    import re
                    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
                    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
                    text = re.sub(r"<[^>]+>", " ", text)
                    text = re.sub(r"\s+", " ", text).strip()

                    if len(text) > max_length:
                        text = text[:max_length] + f"\n\n... (内容已截断，共 {len(text)} 字符)"
                    return ToolResult(output=text)
        except asyncio.TimeoutError:
            return ToolResult(output=f"请求超时: {url}", is_error=True)
        except Exception as e:
            return ToolResult(output=f"获取失败: {e}", is_error=True)


import asyncio


class WebSearchTool(BaseTool):
    """Search the web (placeholder — needs API key for real search)."""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return "搜索互联网获取最新信息。用于查询文档、查找解决方案等。"

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索查询关键词",
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大结果数，默认 5",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs["query"]
        # Placeholder: in production, integrate with a search API
        # (e.g., DuckDuckGo, SerpAPI, Tavily)
        return ToolResult(
            output=f"web_search 功能尚未配置 API 密钥。查询: {query}\n"
            "请设置搜索 API 后使用此功能。",
            is_error=True,
        )
