"""
模块生成引擎 — 自然语言 → JSON 配置 → 前端通用渲染器

核心流程:
    用户描述 → LLM 生成 JSON → Pydantic 校验 → 保存到模块库 → 前端渲染
"""
from core.module_engine.schemas import ModuleConfig, FieldDef
from core.module_engine.templates import TEMPLATE_REGISTRY
from core.module_engine.generator import ModuleGenerator

# 全局生成器单例
module_generator = ModuleGenerator()

__all__ = [
    "ModuleConfig",
    "FieldDef",
    "TEMPLATE_REGISTRY",
    "module_generator",
]
