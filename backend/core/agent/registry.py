"""
AgentRegistry — 子 Agent 动态注册表
- 监听 data/agents/ 目录变化 (watchdog)
- 自动注册/注销 Agent
- 提供 agent_id -> BaseAgent 实例的路由
"""
from pathlib import Path
from typing import Dict, Optional
import asyncio
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from config.settings import settings
from core.agent.base import BaseAgent


class AgentEventHandler(FileSystemEventHandler):
    """监听 Agent 目录变化，触发注册/注销"""

    def __init__(self, registry):
        self.registry = registry

    def on_created(self, event):
        if event.is_directory:
            dir_name = Path(event.src_path).name
            # 检查是否是有效的 Agent 目录 (含 config.yaml)
            if (Path(event.src_path) / "config.yaml").exists():
                print(f"[Watchdog] 检测到新 Agent 目录: {dir_name}")
                asyncio.run_coroutine_threadsafe(
                    self.registry.register(dir_name),
                    self.registry._loop,
                )

    def on_deleted(self, event):
        if event.is_directory:
            dir_name = Path(event.src_path).name
            print(f"[Watchdog] 检测到 Agent 目录删除: {dir_name}")
            asyncio.run_coroutine_threadsafe(
                self.registry.unregister(dir_name),
                self.registry._loop,
            )


class AgentRegistry:
    """子 Agent 注册表 — 动态管理所有 Agent 实例"""

    def __init__(self):
        self._agents: Dict[str, BaseAgent] = {}
        self._observer: Optional[Observer] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def init(self, loop: asyncio.AbstractEventLoop):
        """初始化注册表：扫描现有 Agent + 启动目录监听"""
        self._loop = loop

        # 扫描 data/agents/ 下所有有效 Agent
        agents_path = Path(settings.agents_dir)
        agents_path.mkdir(parents=True, exist_ok=True)

        for agent_dir in agents_path.iterdir():
            if agent_dir.is_dir() and (agent_dir / "config.yaml").exists():
                await self.register(agent_dir.name)

        print(f"[Registry] 初始扫描完成，已注册 {len(self._agents)} 个 Agent: {list(self._agents.keys())}")

        # 启动 watchdog 监听 (在 inotify 受限的容器环境中优雅降级)
        try:
            self._observer = Observer()
            self._observer.schedule(
                AgentEventHandler(self),
                str(agents_path),
                recursive=False,
            )
            self._observer.start()
            print(f"[Registry] watchdog 已启动，监听: {agents_path}")
        except OSError as e:
            print(f"[Registry] ⚠ watchdog 启动失败 ({e})，跳过热加载")
            print(f"[Registry]   Agent 变更需重启服务生效")
            self._observer = None

    async def register(self, agent_id: str):
        """注册一个 Agent (从目录加载配置)"""
        try:
            agent = BaseAgent(agent_id)
            agent.load()
            agent.load_memory()
            self._agents[agent_id] = agent
            print(f"[Registry] ✓ Agent 已注册: {agent_id} ({agent.name})")
        except Exception as e:
            print(f"[Registry] ✗ Agent 注册失败 {agent_id}: {e}")

    async def unregister(self, agent_id: str):
        """注销一个 Agent"""
        if agent_id in self._agents:
            agent = self._agents.pop(agent_id)
            agent.save_memory()
            print(f"[Registry] ✗ Agent 已注销: {agent_id} ({agent.name})")

    def get(self, agent_id: str) -> Optional[BaseAgent]:
        """获取 Agent 实例"""
        return self._agents.get(agent_id)

    def list_agents(self) -> list[dict]:
        """列出所有已注册 Agent 的基本信息"""
        return [
            {
                "agent_id": aid,
                "name": a.name,
                "description": a.description,
            }
            for aid, a in self._agents.items()
        ]

    def shutdown(self):
        """关闭注册表，保存所有 Agent 记忆"""
        for agent_id, agent in self._agents.items():
            try:
                agent.save_memory()
            except Exception as e:
                print(f"[Registry] 保存记忆失败 {agent_id}: {e}")
        if self._observer:
            self._observer.stop()
            self._observer.join()
        print("[Registry] 已关闭，所有 Agent 记忆已保存")


# 全局注册表单例
agent_registry = AgentRegistry()
