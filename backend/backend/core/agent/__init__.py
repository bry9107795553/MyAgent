"""
Agent 系统 — 配置外壳 + 注册表 + 生命周期 + 生成器

模块:
    base.py             — BaseAgent: 配置外壳，加载 config.yaml + prompt.txt
    registry.py         — AgentRegistry: watchdog 热加载 + 注册/注销
    lifecycle.py        — AgentLifecycle: 创建/删除/导出/导入 Agent
    agent_schemas.py    — Pydantic 模型: Agent 配置校验
    agent_generator.py  — AgentGenerator: LLM 驱动 Agent 自动生成
"""
from core.agent.base import BaseAgent
from core.agent.registry import agent_registry, AgentRegistry
from core.agent.lifecycle import agent_lifecycle, AgentLifecycle
from core.agent.agent_schemas import (
    AgentConfig,
    AgentPersonality,
    AgentTools,
    AgentMemory,
    AgentPrivacy,
    AgentGenerateRequest,
    AgentGenerateResponse,
)
from core.agent.agent_generator import agent_generator, AgentGenerator