"""
搜索工具 — 本地知识库搜索

本项目为纯离线私有 Agent，不对接任何外部网络搜索服务。
本工具内部对接本地知识图谱 (L3) 与近期对话记忆，提供
"类搜索"体验，完全离线、零网络请求。

隐私标签: local_only
"""
from typing import Optional

from core.tools.base import BaseTool


class WebSearchTool(BaseTool):
    """本地知识库搜索工具 — 离线检索，无外部网络请求"""

    @property
    def name(self) -> str:
        return "web_search"

    @property
    def description(self) -> str:
        return (
            "搜索本地知识库获取信息。支持关键词检索，返回相关知识条目。"
            "适用于需要获取历史知识、事实查证或信息检索的场景。"
            "注意：本工具为本地离线搜索，不访问互联网。"
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
        """
        本地知识库检索 — 对接 L3 知识图谱 + L1/L2 会话记忆。

        不发起任何网络请求，完全离线。
        """
        results = []
        sources = []

        # 1. 搜索知识图谱 (L3)
        try:
            from core.memory.knowledge_base import knowledge_base
            triples = knowledge_base.search(query, top_k=max_results)
            for t in triples:
                results.append({
                    "type": "knowledge",
                    "subject": t.get("subject", ""),
                    "relation": t.get("relation", ""),
                    "object": t.get("object", ""),
                    "confidence": t.get("confidence", 0),
                    "source": f"本地知识库 · {t.get('source_role', 'system')}",
                })
                sources.append("L3 知识图谱")
        except Exception as e:
            print(f"[WebSearch] 知识图谱检索异常: {e}")

        # 2. 搜索近期会话摘要 (L1/L2)
        try:
            from core.memory.session_memory import sm_registry
            for role_id, sm in sm_registry._stores.items():
                l1_results = sm.search_l1(query)
                for r in l1_results[:2]:
                    summary = r.get("summary", "")
                    if summary:
                        results.append({
                            "type": "memory",
                            "summary": summary[:300],
                            "source": f"会话记忆 · {role_id}",
                        })
                        sources.append("会话记忆")
        except Exception as e:
            print(f"[WebSearch] 会话记忆检索异常: {e}")

        if not results:
            return {
                "success": True,
                "query": query,
                "results": [],
                "note": "本地知识库中未找到相关信息。这是离线私有 Agent，无法访问互联网。建议：1) 提供更具体的上下文 2) 之前对话中的知识会自动沉淀到知识库。",
            }

        return {
            "success": True,
            "query": query,
            "results": results[:max_results],
            "sources": list(set(sources)),
            "count": len(results[:max_results]),
            "note": "结果来自本地知识库，未联网搜索。",
        }
