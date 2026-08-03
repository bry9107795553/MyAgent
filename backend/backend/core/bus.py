"""
消息总线 — WebSocket 连接管理与事件分发
- 管理客户端 WebSocket 连接
- 支持按 agent_id 隔离消息
- 流式推理结果实时推送
"""
from fastapi import WebSocket
from typing import Dict, Set
import json
import asyncio


class MessageBus:
    """全局消息总线"""

    def __init__(self):
        # agent_id -> set of WebSocket connections
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, agent_id: str = "default"):
        """接受 WebSocket 连接，绑定到指定 agent_id"""
        await websocket.accept()
        async with self._lock:
            if agent_id not in self._connections:
                self._connections[agent_id] = set()
            self._connections[agent_id].add(websocket)
        print(f"[Bus] WebSocket 已连接 → agent: {agent_id}, 总连接数: {self._total()}")

    async def disconnect(self, websocket: WebSocket, agent_id: str = "default"):
        """断开 WebSocket 连接"""
        async with self._lock:
            if agent_id in self._connections:
                self._connections[agent_id].discard(websocket)
                if not self._connections[agent_id]:
                    del self._connections[agent_id]
        print(f"[Bus] WebSocket 已断开 → agent: {agent_id}, 总连接数: {self._total()}")

    async def send_to_agent(self, agent_id: str, message: dict):
        """向指定 agent 的所有连接推送消息"""
        conns = self._connections.get(agent_id, set()).copy()
        dead = []
        for ws in conns:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        # 清理断开的连接
        if dead:
            async with self._lock:
                for ws in dead:
                    self._connections.get(agent_id, set()).discard(ws)

    async def stream_to_agent(self, agent_id: str, token_generator):
        """
        将流式推理结果逐 token 推送给指定 agent 的所有连接
        :param agent_id: 目标 agent
        :param token_generator: 异步生成器，yield str
        """
        # 发送开始标记
        await self.send_to_agent(agent_id, {"type": "stream_start"})
        # 逐 token 推送
        async for token in token_generator:
            await self.send_to_agent(agent_id, {
                "type": "stream_token",
                "content": token,
            })
        # 发送结束标记
        await self.send_to_agent(agent_id, {"type": "stream_end"})

    def _total(self) -> int:
        return sum(len(conns) for conns in self._connections.values())


# 全局消息总线单例
message_bus = MessageBus()
