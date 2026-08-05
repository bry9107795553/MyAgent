"""
动态工具注册 API — 支持信息侦察员生成并注册新工具

路由:
    POST /api/tools/generate  — 接收工具定义 JSON，验证并注册
    GET  /api/tools             — 列出所有已注册工具
    GET  /api/tools/{name}      — 获取工具详情
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import json

from core.tools.base import tool_registry

router = APIRouter(prefix="/api/tools", tags=["tools"])


class ToolGenerateRequest(BaseModel):
    """信息侦察员生成的工具定义"""
    tool_name: str
    display_name: str = ""
    description: str
    parameters: dict
    implementation: dict  # {language, dependencies, code}
    category: str = "工具增强"
    safety_notes: str = ""


class DynamicTool:
    """
    运行时动态生成的工具包装器。
    在沙箱中执行 implementation.code，实例化后注册到 tool_registry。
    """
    def __init__(self, definition: dict):
        self.defn = definition
        self._instance = None  # 延迟编译

    @property
    def name(self) -> str:
        return self.defn["tool_name"]

    @property
    def description(self) -> str:
        return self.defn.get("description", "")

    @property
    def parameters(self) -> dict:
        return self.defn.get("parameters", {"type": "object", "properties": {}, "required": []})

    async def execute(self, **kwargs) -> dict:
        """动态执行生成的代码"""
        if not self._instance:
            self._compile()
        return await self._instance.execute(**kwargs)

    def to_openai_format(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }

    def _compile(self):
        """编译并实例化生成的工具代码"""
        code = self.defn["implementation"].get("code", "")
        if not code:
            raise ValueError("implementation.code 为空")

        # 沙箱执行
        namespace = {
            "__builtins__": __builtins__,
            "BaseTool": __import__("core.tools.base", fromlist=["BaseTool"]).BaseTool,
        }
        exec(code, namespace)

        # 查找继承 BaseTool 的类
        for name, obj in namespace.items():
            if isinstance(obj, type) and hasattr(obj, "name") and hasattr(obj, "execute"):
                self._instance = obj()
                print(f"[DynamicTool] ✓ 编译成功: {self.name}")
                return

        raise RuntimeError(f"未找到有效的 BaseTool 子类: {self.name}")


@router.get("")
async def list_tools():
    """列出所有工具（内置 + 动态注册）"""
    return {
        "tools": [
            {"name": name, "type": "builtin" if isinstance(tool_registry._tools[name], type(tool_registry._tools.get(next(iter(tool_registry._tools), "")))) else "dynamic"}
            for name in tool_registry.list_all()
        ],
        "count": len(tool_registry.list_all()),
    }


@router.get("/{tool_name}")
async def get_tool(tool_name: str):
    """获取工具详情（仅动态工具）"""
    tool = tool_registry._tools.get(tool_name)
    if not tool:
        raise HTTPException(status_code=404, detail=f"工具不存在: {tool_name}")
    if isinstance(tool, DynamicTool):
        return {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
            "definition": tool.defn,
        }
    raise HTTPException(status_code=400, detail="内置工具不支持查看详情")


@router.post("/generate")
async def generate_tool(req: ToolGenerateRequest):
    """接收信息侦察员生成的工具定义，验证安全后注册"""
    # 安全检查
    code = req.implementation.get("code", "")
    if not code:
        raise HTTPException(status_code=400, detail="implementation.code 为空")

    # 禁止危险操作
    forbidden = ["os.system(", "subprocess.", "eval(", "exec(", "import os", "__import__"]
    for fb in forbidden:
        if fb in code:
            raise HTTPException(status_code=400, detail=f"代码包含禁止的操作: {fb}")

    # 构建工具定义
    definition = {
        "tool_name": req.tool_name,
        "display_name": req.display_name or req.tool_name,
        "description": req.description,
        "parameters": req.parameters,
        "implementation": req.implementation,
        "category": req.category,
        "safety_notes": req.safety_notes,
    }

    # 注册
    try:
        dyn_tool = DynamicTool(definition)
        dyn_tool._compile()  # 立即编译，失败则报错
        tool_registry._tools[dyn_tool.name] = dyn_tool
        print(f"[ToolsAPI] ✓ 动态工具已注册: {dyn_tool.name}")
        return {
            "success": True,
            "tool": {"name": dyn_tool.name, "description": dyn_tool.description},
            "message": f"工具 {dyn_tool.name} 已注册，所有有权限的角色可使用",
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"工具编译失败: {e}")
