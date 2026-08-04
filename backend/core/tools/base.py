"""
工具系统核心 — 工具基类与注册表
- BaseTool: 所有工具的抽象基类，统一接口 (name / description / parameters / execute)
- ToolRegistry: 工具注册表，管理注册/注销、按 Agent 配置过滤、执行工具调用
- tool_registry: 全局工具注册表单例

工具配置从 Agent 的 config.yaml 中读取:
    tools:
      file_read: true
      file_write: false
      web_search: false
      code_exec: false
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional
import asyncio
import traceback


class BaseTool(ABC):
    """工具抽象基类 — 所有工具继承此类，统一接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称 (唯一标识，对应 config.yaml 中 tools 段的键名)"""

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述 (传给 LLM，帮助其判断何时调用该工具)"""

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """工具参数定义 (JSON Schema 格式，描述 execute 接收的参数)"""

    @property
    def config_key(self) -> str:
        """配置键 — 对应 config.yaml 中 tools 段的键名，默认与 name 相同。
        子类可重写此属性，将多个工具绑定到同一个配置开关下。"""
        return self.name

    @abstractmethod
    async def execute(self, **kwargs) -> dict:
        """执行工具，返回结果字典。
        :return: {"success": bool, ...} 格式的结果
        """

    def to_openai_format(self) -> dict:
        """转换为 OpenAI function calling 格式的工具定义"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """工具注册表 — 管理所有工具的注册、过滤与执行"""

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}

    def register(self, tool: BaseTool):
        """注册一个工具实例"""
        if tool.name in self._tools:
            print(f"[ToolRegistry] 工具已存在，覆盖注册: {tool.name}")
        self._tools[tool.name] = tool
        print(f"[ToolRegistry] ✓ 工具已注册: {tool.name}")

    def unregister(self, name: str):
        """注销一个工具"""
        if name in self._tools:
            del self._tools[name]
            print(f"[ToolRegistry] ✗ 工具已注销: {name}")

    def get(self, name: str) -> Optional[BaseTool]:
        """获取工具实例"""
        return self._tools.get(name)

    def list_all(self) -> list[str]:
        """列出所有已注册工具名称"""
        return list(self._tools.keys())

    def get_available_tools(self, agent_config: dict) -> list[BaseTool]:
        """根据 Agent 配置过滤可用工具

        :param agent_config: Agent 配置字典 (含 tools 段)
        :return: 该 Agent 可用的工具实例列表
        """
        tools_config = agent_config.get("tools", {})
        available = []
        for tool in self._tools.values():
            # 检查 config.yaml 中该工具对应的配置键是否启用
            if tools_config.get(tool.config_key, False):
                available.append(tool)
        return available

    def get_tool_definitions(self, agent_config: dict) -> list[dict]:
        """获取 OpenAI function calling 格式的工具定义 (按 Agent 配置过滤)

        :param agent_config: Agent 配置字典
        :return: 工具定义列表，可直接传给 LLM 的 tools 参数
        """
        return [
            tool.to_openai_format()
            for tool in self.get_available_tools(agent_config)
        ]

    async def execute_tool(
        self,
        tool_name: str,
        arguments: dict,
        agent_config: dict,
    ) -> dict:
        """执行工具调用

        :param tool_name: 工具名称
        :param arguments: 工具参数 (LLM 返回的 function arguments)
        :param agent_config: Agent 配置字典 (用于权限校验)
        :return: 工具执行结果 {"success": bool, ...}
        """
        # 1. 检查工具是否已注册
        tool = self._tools.get(tool_name)
        if not tool:
            return {"success": False, "error": f"工具不存在: {tool_name}"}

        # 2. 检查 Agent 配置是否启用了该工具
        tools_config = agent_config.get("tools", {})
        if not tools_config.get(tool.config_key, False):
            return {"success": False, "error": f"工具未启用: {tool_name}"}

        # 3. 执行工具 (捕获所有异常，避免单次工具调用崩溃影响主流程)
        try:
            print(f"[ToolRegistry] 执行工具: {tool_name} | 参数: {arguments}")
            result = await tool.execute(**arguments)
            print(f"[ToolRegistry] ✓ 工具执行完成: {tool_name}")
            return result
        except asyncio.TimeoutError:
            print(f"[ToolRegistry] ✗ 工具执行超时: {tool_name}")
            return {"success": False, "error": f"工具执行超时: {tool_name}"}
        except TypeError as e:
            # 参数不匹配
            print(f"[ToolRegistry] ✗ 工具参数错误: {tool_name} - {e}")
            return {"success": False, "error": f"工具参数错误: {tool_name} - {e}"}
        except Exception as e:
            print(f"[ToolRegistry] ✗ 工具执行异常: {tool_name} - {e}")
            return {
                "success": False,
                "error": f"工具执行异常: {tool_name} - {e}",
                "traceback": traceback.format_exc(),
            }


# 全局工具注册表单例
tool_registry = ToolRegistry()
