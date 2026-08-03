"""
搜索工具 — 网页搜索
- WebSearchTool: 网页搜索 (占位实现，返回提示需要配置搜索 API)

接入真实搜索服务时，只需在 execute 方法中替换占位逻辑即可。
"""
from typing import Optional

from core.tools.base import BaseTool


class WebSearchTool(BaseTool):
    """网页搜索工具 (占位实现)"""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "在互联网上搜索指定关键词，返回相关网页摘要和链接。"
            "适用于需要获取最新信息、事实查证或知识检索的场景。"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "搜索关键词",
                },
                "max_results": {
                    "type": "integer",
                    "description": "最大返回结果数量，默认 5",
                    "default": 5,
                },
            },
            "required": ["query"],
        }

    async def execute(
        self,
        query: str,
        max_results: Optional[int] = 5,
    ) -> dict:
        """执行网页搜索 (占位实现)

        TODO: 接入真实搜索 API (如 SerpAPI / Bing Search API / Google Custom Search)
        """
        # 当前为占位实现 — 提示需要配置搜索 API
        return {
            "success": False,
            "error": "网页搜索功能尚未配置搜索 API",
            "hint": (
                "请在环境变量或配置文件中设置搜索 API 密钥 "
                "(如 SERPAPI_KEY / BING_API_KEY / GOOGLE_API_KEY)，"
                "并在 WebSearchTool.execute 中接入对应服务。"
            ),
            "query": query,
            "max_results": max_results,
            "results": [],
        }
