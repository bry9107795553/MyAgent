"""
搜索工具 — 网页搜索 (未启用的占位实现)

⚠ 合规说明：
本工具**没有接入任何外部服务**，execute() 恒定返回 "未启用"，不发起任何
网络请求。它在所有 Agent 配置中默认关闭 (AgentTools.web_search = False)。

保留它是为了让工具注册表的能力面完整可见；它与模型推理无关，
本项目的核心推理 100% 运行在本机 llama.cpp (ROCm / AMD Radeon GPU)。
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
        """占位实现 — 不发起任何网络请求，恒定返回"未启用"。"""
        return {
            "success": False,
            "error": "网页搜索未启用",
            "hint": (
                "本项目为纯离线私有 Agent，未接入任何外部搜索服务。"
                "信息检索请使用本地知识库 (core/memory/knowledge_base.py)。"
            ),
            "query": query,
            "max_results": max_results,
            "results": [],
        }
