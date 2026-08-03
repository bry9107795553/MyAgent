"""
皮肤系统 — 皮肤配置的读取、应用、AI 生成与图片取色

核心流程:
    读取 data/skins/*.json → 应用皮肤 → 前端注入 CSS 变量
    AI 生成: 自然语言 → LLM 生成 CSS 变量方案 → 保存到皮肤库
    图片取色: Pillow + sklearn KMeans → 主色调方案
"""
from core.skin.manager import SkinManager, skin_manager

__all__ = [
    "SkinManager",
    "skin_manager",
]
