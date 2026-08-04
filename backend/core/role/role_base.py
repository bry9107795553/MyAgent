"""
RoleBase — 角色抽象基类

架构定位:
    角色是"执行引擎"——每个角色有独立的人格、记忆分区、工具权限和 LLM 调用能力。
    所有角色共享同一个 7 段式提示词框架:
        identity → responsibilities → boundaries → output → standards → memory → tools

    角色不直接与其他角色通信，所有跨角色通信通过黑板 (Blackboard) 经主控路由。

与记忆系统集成:
    每个角色拥有独立的:
        - WorkingMemory (L0): 热层滑动窗口
        - SessionMemory (L1/L2): 跨会话持久化
        - Archive: 原始归档 (零损失)
    所有角色共享:
        - KnowledgeBase (L3): 知识图谱
        - Blackboard: 角色间通信

角色类型:
    - 通用角色 (general): 知识检索、写作、质检、日程、创意、翻译、视觉分析
    - 开发角色 (dev): 教练、设计、开发、巡检、测试、部署
    - 后勤角色 (logistics): 清洁员
    - 核心角色 (core): 主控 (MasterRole，特殊处理)
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Optional, AsyncGenerator

from core.memory.working_memory import (
    Message, WorkingMemory, wm_registry,
)
from core.memory.compressor import (
    score_importance,
)
from core.memory.session_memory import (
    SessionMemory, sm_registry,
)
from core.memory.archive import (
    Archive, archive_registry,
)
from core.memory.blackboard import (
    Blackboard, BlackboardEntry, blackboard,
)
from core.memory.knowledge_base import (
    KnowledgeBase, knowledge_base,
)
from core.memory.store import generate_id, now_iso


# ===== 7 段式提示词框架模板 =====

PROMPT_SECTIONS = [
    "identity",
    "responsibilities",
    "boundaries",
    "output",
    "standards",
    "memory",
    "tools",
]


@dataclass
class RoleContext:
    """角色执行任务时的上下文"""
    role_id: str
    session_id: str
    task: str                     # 当前任务描述
    task_id: str                  # 任务 ID
    l0_messages: list[dict] = field(default_factory=list)   # 热层原文
    l1_relevant: list[dict] = field(default_factory=list)   # 相关 L1 摘要
    l2_bullets: list[dict] = field(default_factory=list)    # 所有 L2 要点
    l3_triples: list[dict] = field(default_factory=list)    # 相关知识三元组
    unread_blackboard: list[dict] = field(default_factory=list)  # 未读黑板消息
    extra_context: str = ""       # 主控附加的上下文


class RoleBase(ABC):
    """
    角色抽象基类

    子类必须实现:
        - _build_system_prompt() → str

    子类可选覆盖:
        - _get_default_prompt() → str (默认 prompt，当无外部文件时使用)
    """

    def __init__(self, role_def: dict):
        """
        :param role_def: 角色定义字典 (来自 role_pool.json 的单个角色)
        """
        # 角色身份
        self.id: str = role_def["id"]
        self.name: str = role_def["name"]
        self.group: str = role_def.get("group", "general")
        self.model_type: str = role_def.get("model", "text")
        self.gpu_affinity: str = role_def.get("gpu_affinity", "gpu0")
        self.capabilities: list[str] = role_def.get("capabilities", [])
        self.tool_names: list[str] = role_def.get("tools", [])
        self.description: str = role_def.get("description", "")

        # 系统提示词 (子类在 _build_system_prompt 中构建)
        self.system_prompt: str = ""

        # 记忆系统 — 每个角色独立分区
        self._wm: WorkingMemory = wm_registry.get(self.id)
        self._sm: SessionMemory = sm_registry.get(self.id)
        self._archive: Archive = archive_registry.get(self.id)

        # 当前会话 ID
        self._session_id: str = ""

    # ------------------------------------------------------------------ #
    # 初始化
    # ------------------------------------------------------------------ #

    def init(self, session_id: str = ""):
        """
        初始化角色 (每次新会话调用)

        :param session_id: 会话 ID
        """
        self._session_id = session_id or generate_id("sess")
        self.system_prompt = self._build_system_prompt()
        print(f"[Role:{self.id}] 已初始化 | 会话: {self._session_id} | 能力: {self.capabilities}")
        return self

    # ------------------------------------------------------------------ #
    # 抽象方法 — 子类必须实现
    # ------------------------------------------------------------------ #

    @abstractmethod
    def _build_system_prompt(self) -> str:
        """
        构建 7 段式系统提示词

        返回格式:
            # 身份 (Identity)
            ...
            # 职责 (Responsibilities)
            ...
            # 边界 (Boundaries)
            ...
            # 输出 (Output)
            ...
            # 标准 (Standards)
            ...
            # 记忆 (Memory)
            ...
            # 工具 (Tools)
            ...
        """
        ...

    # ------------------------------------------------------------------ #
    # 核心执行方法
    # ------------------------------------------------------------------ #

    async def execute(self, task: str, task_id: str = "", extra_context: str = "") -> str:
        """
        执行任务 (非流式)

        完整流程:
            1. 组装上下文 (L0 + L1 + L2 + L3 + 黑板)
            2. 调用 LLM
            3. 记录到工作记忆
            4. 发布结果到黑板

        :param task: 任务描述
        :param task_id: 任务 ID
        :param extra_context: 主控附加的上下文
        :return: 执行结果
        """
        task_id = task_id or generate_id("task")

        # 1. 组装上下文
        context = self._assemble_context(task, task_id, extra_context)

        # 2. 调用 LLM
        result = await self._call_llm(context)

        # 3. 记录到工作记忆
        self._record_task(task, result, task_id)

        return result

    async def execute_stream(self, task: str, task_id: str = "", extra_context: str = "") -> AsyncGenerator[str, None]:
        """
        执行任务 (流式)

        :param task: 任务描述
        :param task_id: 任务 ID
        :param extra_context: 主控附加的上下文
        :yield: 流式 token
        """
        task_id = task_id or generate_id("task")

        # 1. 组装上下文
        context = self._assemble_context(task, task_id, extra_context)

        # 2. 流式调用 LLM
        full_response = []
        async for token in self._call_llm_stream(context):
            full_response.append(token)
            yield token

        # 3. 记录到工作记忆
        result = "".join(full_response)
        self._record_task(task, result, task_id)

    # ------------------------------------------------------------------ #
    # 上下文组装
    # ------------------------------------------------------------------ #

    def _assemble_context(self, task: str, task_id: str, extra_context: str = "") -> RoleContext:
        """
        按需组装角色上下文 (L0 + L1 + L2 + L3 + 黑板)

        原则: 不是一次性全塞，而是按需组装
        """
        context = RoleContext(
            role_id=self.id,
            session_id=self._session_id,
            task=task,
            task_id=task_id,
            extra_context=extra_context,
        )

        # 1. L0 原文: 始终包含最近 N 轮
        context.l0_messages = self._wm.get_recent(n=20)

        # 2. L1 摘要: 任务引用过去工作时，关键词匹配拉取
        if task:
            context.l1_relevant = self._sm.search_l1(task)

        # 3. L2 要点: 跨多轮任务时全量注入 (体积小)
        context.l2_bullets = self._sm.get_all_l2()

        # 4. L3 知识: 跨会话语义检索 top-K
        if task:
            context.l3_triples = knowledge_base.search(task, top_k=5)

        # 5. 黑板未读消息: 主控转发的
        context.unread_blackboard = blackboard.fetch_unread(self.id)

        return context

    def context_to_messages(self, ctx: RoleContext) -> list[dict]:
        """
        将 RoleContext 转换为 LLM 消息列表

        :param ctx: 角色上下文
        :return: messages 列表 (system + 记忆 + 任务)
        """
        messages = [{"role": "system", "content": self.system_prompt}]

        # 注入记忆层
        memory_parts = []

        # L2 要点 (体积小，全量注入)
        if ctx.l2_bullets:
            bullets_text = "\n".join(
                f"• {b}" for bl in ctx.l2_bullets for b in bl.get("bullets", [])
            )
            if bullets_text:
                memory_parts.append(f"## 历史关键要点\n{bullets_text}")

        # L1 相关摘要
        if ctx.l1_relevant:
            l1_text = "\n---\n".join(
                s.get("summary", "") for s in ctx.l1_relevant[:3]
            )
            if l1_text:
                memory_parts.append(f"## 相关历史摘要\n{l1_text}")

        # L3 知识三元组
        if ctx.l3_triples:
            triples_text = "\n".join(
                f"({t['subject']}, {t['relation']}, {t['object']})"
                for t in ctx.l3_triples
            )
            if triples_text:
                memory_parts.append(f"## 已知知识\n{triples_text}")

        # 黑板消息
        if ctx.unread_blackboard:
            bb_text = "\n".join(
                f"[{m['msg_type']}] {m['content'][:200]}"
                for m in ctx.unread_blackboard[:5]
            )
            if bb_text:
                memory_parts.append(f"## 协作消息\n{bb_text}")

        if memory_parts:
            messages.append({
                "role": "system",
                "content": "\n\n".join(memory_parts),
            })

        # 注入 L0 原文
        messages.extend(ctx.l0_messages)

        # 注入额外上下文
        if ctx.extra_context:
            messages.append({
                "role": "system",
                "content": f"## 附加上下文\n{ctx.extra_context}",
            })

        # 注入当前任务
        messages.append({
            "role": "user",
            "content": ctx.task,
        })

        return messages

    # ------------------------------------------------------------------ #
    # LLM 调用
    # ------------------------------------------------------------------ #

    async def _call_llm(self, ctx: RoleContext) -> str:
        """
        调用 LLM (非流式)

        :param ctx: 角色上下文
        :return: LLM 响应
        """
        from core.llm.gateway import llm_gateway

        messages = self.context_to_messages(ctx)
        # 使用角色对应的 GPU 端口
        base_url = self._get_gpu_url()

        result = await llm_gateway.chat(
            messages,
            temperature=0.7,
            max_tokens=4096,
            base_url=base_url,
        )
        return result["content"]

    async def _call_llm_stream(self, ctx: RoleContext) -> AsyncGenerator[str, None]:
        """调用 LLM (流式)"""
        from core.llm.gateway import llm_gateway

        messages = self.context_to_messages(ctx)
        base_url = self._get_gpu_url()

        async for token in llm_gateway.chat_stream(
            messages,
            temperature=0.7,
            max_tokens=4096,
            base_url=base_url,
        ):
            yield token

    def _get_gpu_url(self) -> str:
        """
        根据 GPU 亲和性获取对应的 LLM 服务 URL

        实际解析逻辑收敛在 `settings.resolve_inference_url()`，
        本方法只是角色侧的薄封装 —— 端口不再在这里硬编码。

        单 GPU 模式 (默认, SINGLE_GPU_MODE=true):
            无视 gpu_affinity，所有角色 → settings.llama_base_url
            (默认 http://localhost:8000/v1，随 LLAMA_BASE_URL 变动)

        多 GPU 模式 (SINGLE_GPU_MODE=false):
            gpu0 → :8000 (14B 文本)
            gpu1 → :8001 (7B 文本 + 视觉)
            gpu2 → :8002 (7B 文本)
        """
        from config.settings import settings
        return settings.resolve_inference_url(self.gpu_affinity)

    # ------------------------------------------------------------------ #
    # 记忆记录
    # ------------------------------------------------------------------ #

    def _record_task(self, task: str, result: str, task_id: str):
        """记录任务到工作记忆"""
        self._wm.add_message("user", task, score_importance("user", task))
        self._wm.add_message("assistant", result, 2)

    # ------------------------------------------------------------------ #
    # 黑板通信
    # ------------------------------------------------------------------ #

    def publish_result(self, task_id: str, result: str, msg_type: str = "task_done"):
        """
        发布结果到黑板 (由主控路由)

        :param task_id: 任务 ID
        :param result: 执行结果
        :param msg_type: 消息类型
        """
        blackboard.publish(
            from_role=self.id,
            to_role="master",
            msg_type=msg_type,
            content=f"[{task_id}] {result}",
        )

    # ------------------------------------------------------------------ #
    # 工具方法
    # ------------------------------------------------------------------ #

    def get_status(self) -> dict:
        """获取角色状态"""
        return {
            "id": self.id,
            "name": self.name,
            "group": self.group,
            "model_type": self.model_type,
            "gpu_affinity": self.gpu_affinity,
            # 实际生效的推理端点（单卡模式下所有角色都应是同一个）
            "inference_url": self._get_gpu_url(),
            "capabilities": self.capabilities,
            "session_id": self._session_id,
            "memory": {
                "l0_message_count": len(self._wm._messages),
                "l1_summary_count": len(self._wm._l1_summaries),
                "l2_bullet_count": len(self._wm._l2_summaries),
            },
        }

    def __repr__(self) -> str:
        return f"<Role:{self.id} gpu={self.gpu_affinity} caps={self.capabilities}>"