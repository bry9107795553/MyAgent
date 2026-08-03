"""
工具系统 — 工具基类、注册表与内置工具

使用方式:
    from core.tools import tool_registry
    from core.tools import builtin  # 导入即自动注册所有内置工具

    # 获取当前 Agent 可用的工具定义 (OpenAI function calling 格式)
    definitions = tool_registry.get_tool_definitions(agent.config)

    # 执行工具调用
    result = await tool_registry.execute_tool(
        tool_name="file_read",
        arguments={"path": "README.md"},
        agent_config=agent.config,
    )
"""
from core.tools.base import BaseTool, ToolRegistry, tool_registry

# 导入 builtin 包会自动将所有内置工具注册到 tool_registry
from core.tools import builtin  # noqa: F401

__all__ = [
    "BaseTool",
    "ToolRegistry",
    "tool_registry",
]
