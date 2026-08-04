"""
角色系统 — Agent 执行引擎

模块:
    role_base.py — RoleBase 抽象基类: 7 段式提示词框架、记忆集成、LLM 调用
    master.py    — MasterRole 主控: 调度中心、防火墙路由、进度报告、秘书集成
    loader.py    — RoleLoader 加载器: 从 role_pool.json 创建角色实例

架构关系:
    Agent (配置外壳) → MasterRole (主控) → 角色池 (执行引擎) → LLM
                                   ↑
                              Secretary (秘书)
                              · 上下文管理 · 增量摘要 · 纠错触发

使用方式:
    from core.role import role_loader, MasterRole, RoleBase, GenericRole

    loader = role_loader
    master = loader.load_all(session_id)
    result = await master.dispatch("帮我写一篇文章")
"""
from core.role.role_base import (
    RoleBase, RoleContext, PROMPT_SECTIONS,
)
from core.role.master import (
    MasterRole,
)
from core.role.loader import (
    GenericRole, HrManagerRole, RoleLoader, role_loader,
)