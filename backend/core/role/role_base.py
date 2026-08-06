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
import json

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
from core.tools.base import tool_registry  # 导入即触发 builtin 工具注册（core/tools/__init__ 副作用）


# ===== 7 段式提示词框架模板 =====

# 工具调用最大轮次上限（防止模型死循环反复调工具占死 GPU / 上机演示卡死）
MAX_TOOL_ITERATIONS = 5

# 单轮工具调用数上限 + LLM 重复调用去重（14B 模型偶尔返回 20-30 个相同调用）
MAX_TOOL_CALLS_PER_TURN = 10


def _dedup_tool_calls(tool_calls: list[dict]) -> list[dict]:
    """去重：同一函数+同一参数只执行一次，防止 LLM 幻觉重复调用。"""
    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for tc in tool_calls:
        fn = tc.get("function", {})
        name = fn.get("name", "")
        args = fn.get("arguments", "{}") or "{}"
        # 标准化参数: 排序 key，忽略对象内的顺序差异
        try:
            args_norm = json.dumps(json.loads(args) if isinstance(args, str) else (args or {}), sort_keys=True)
        except Exception:
            args_norm = json.dumps(args, sort_keys=True)
        key = (name, args_norm)
        if key not in seen:
            seen.add(key)
            unique.append(tc)
    # file_write 同路径去重: 多条写入同一个文件 → 只保留最后一条
    path_seen: dict[str, int] = {}
    for i, tc in enumerate(unique):
        fn = tc.get("function", {})
        if fn.get("name") == "file_write":
            try:
                a = json.loads(fn.get("arguments", "{}")) if isinstance(fn.get("arguments", ""), str) else fn.get("arguments", {})
                p = a.get("path", "")
                if p:
                    path_seen[p] = i  # 记录最后一次出现位置
            except Exception:
                pass
    if path_seen:
        keep = set(path_seen.values())
        filtered = [tc for i, tc in enumerate(unique) if tc.get("function", {}).get("name") != "file_write" or i in keep]
        if len(filtered) < len(unique):
            print(f"[Role:*] ⚠ 同路径 file_write 去重: {len(unique)} → {len(filtered)}")
        unique = filtered
    if len(tool_calls) > len(unique):
        print(f"[Role:*] ⚠ 工具去重: {len(tool_calls)} → {len(unique)} (有 {len(tool_calls) - len(unique)} 个重复)")
    return unique

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
        调用 LLM (非流式)，并闭环处理工具调用 (function calling)。

        断点 A：把「角色被授权的工具 schema」通过 gateway 传给模型
                (来自角色 role_pool.json 的 tools 白名单 → 注册表过滤)
        断点 B：模型若返回 tool_calls，则逐个执行、把结果回填 messages、
                再请求模型，直到模型不再要求调工具或达到最大轮次。

        :param ctx: 角色上下文
        :return: LLM 最终文本响应
        """
        from core.llm.gateway import llm_gateway

        messages = self.context_to_messages(ctx)
        # 使用角色对应的 GPU 端口
        base_url = self._get_gpu_url()

        # 兜底：确保内置工具已注册（core/tools/__init__ 导入副作用）
        if not tool_registry.list_all():
            import core.tools.builtin  # noqa: F401

        # 断点 A：按角色授权白名单取出该角色可用的工具 schema
        #   role_pool.json 的 tools 字段是授权白名单（权限控制举证材料），
        #   注册表 get_available_tools() 已实现按白名单过滤，这里不绕过它。
        agent_config = {"tools": {name: True for name in self.tool_names}}
        tool_defs = tool_registry.get_tool_definitions(agent_config)
        # 无工具授权时传 None，与历史行为完全一致（gateway 不会收到空 tools 数组）
        tools_arg = tool_defs if tool_defs else None

        return await self._run_tool_loop(
            llm_gateway, messages, base_url, tools_arg, agent_config,
        )

    async def _run_tool_loop(
        self,
        gateway,
        messages: list[dict],
        base_url: str,
        tools_arg,
        agent_config: dict,
    ) -> str:
        """
        工具调用闭环：循环执行模型要求的工具，直到模型不再要求或达到轮次上限。

        容错要点：
        - 模型返回格式不标准的 tool_calls（参数非合法 JSON、缺字段、未知工具名）
          不能让整个对话崩掉 —— 解析失败降级为空参、未知工具返回「不存在」、
          执行异常由注册表捕获，一律作为 tool 消息回填，让模型自行恢复。
        - 达到 MAX_TOOL_ITERATIONS 上限后强制返回，避免模型死循环占死 GPU。
        """
        last_content = ""

        for _ in range(MAX_TOOL_ITERATIONS):
            try:
                result = await gateway.chat(
                    messages,
                    temperature=0.7,
                    max_tokens=4096,
                    tools=tools_arg,
                    base_url=base_url,
                )
            except Exception as e:
                # LLM 工具调用异常（常见于 llama.cpp JSON 解析失败 500）
                print(f"[Role:{self.id}] ⚠ 工具循环异常: {e} → 降级为纯文本调用")
                try:
                    result = await gateway.chat(
                        messages, temperature=0.7, max_tokens=4096,
                        base_url=base_url,  # 不带 tools 参数
                    )
                    return result.get("content") or ""
                except Exception as e2:
                    print(f"[Role:{self.id}] 💀 纯文本降级也失败: {e2}")
                    return last_content

            content = result.get("content") or ""
            # 30B MoE 思考模式：若 content 为空，回退到 reasoning
            if not content:
                reasoning = result.get("reasoning") or ""
                if reasoning:
                    content = reasoning
                    print(f"[Role:{self.id}] ℹ 30B 思考模式: content 为空，回退 reasoning ({len(reasoning)} chars)")
            last_content = content or last_content
            tool_calls = result.get("tool_calls") or []

            # 去重 & 上限：防止 14B 模型一次返回 20+ 个重复调用
            if tool_calls:
                tool_calls = _dedup_tool_calls(tool_calls)
                if len(tool_calls) > MAX_TOOL_CALLS_PER_TURN:
                    print(f"[Role:{self.id}] ⚠ 单轮工具调用超限: {len(tool_calls)} → 截断为 {MAX_TOOL_CALLS_PER_TURN}")
                    tool_calls = tool_calls[:MAX_TOOL_CALLS_PER_TURN]

            # 模型不再要求调工具 → 本轮就是最终答案
            if not tool_calls:
                return content

            # 把 assistant 的 tool_calls 回写进 messages，作为下一轮上下文
            messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": [
                    {
                        "id": tc.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": tc.get("function", {}).get("name", ""),
                            "arguments": tc.get("function", {}).get("arguments", "{}"),
                        },
                    }
                    for tc in tool_calls
                ],
            })

            # 逐个执行工具，结果以 role=tool 消息回填
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}") or "{}"

                # 容错：llama.cpp 可能返回格式不标准的 arguments
                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except (json.JSONDecodeError, TypeError, ValueError):
                    args = {}
                    print(f"[Role:{self.id}] ⚠ 工具参数 JSON 解析失败: {name} | 原值={raw_args!r}")

                try:
                    tool_result = await tool_registry.execute_tool(name, args, agent_config)
                except Exception as e:
                    tool_result = {"success": False, "error": f"工具执行未捕获异常: {e}"}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(tool_result, ensure_ascii=False, default=str),
                })

        # 达到最大轮次仍未结束 —— 取最后一轮文本，避免无限循环占死 GPU
        print(f"[Role:{self.id}] ⚠ 工具调用达到上限 {MAX_TOOL_ITERATIONS} 轮，强制结束")
        return last_content

    async def _call_llm_stream(self, ctx: RoleContext) -> AsyncGenerator[str, None]:
        """
        调用 LLM (流式)，支持工具调用。

        工具调用策略 (混合模式):
            llama.cpp 的流式端点不支持 function calling —— 工具调用只在
            非流式 /chat/completions 中生效。因此本方法采用「先探工具、再流式」策略:
                1. 先用非流式调用 (带 tools schema) 检测模型是否要调工具
                2. 如果有 tool_calls，执行工具 → 回填 → 循环，进度以文本帧 yield
                3. 模型不再要求调工具后，用流式端点产出最终回复

        如果角色没有工具授权 (tool_names 为空)，直接走纯流式（与旧行为一致，
        零开销）。
        """
        from core.llm.gateway import llm_gateway

        messages = self.context_to_messages(ctx)
        base_url = self._get_gpu_url()

        # 兜底：确保内置工具已注册
        if not tool_registry.list_all():
            import core.tools.builtin  # noqa: F401

        # 该角色是否有工具授权 —— 无授权则纯流式，零开销
        agent_config = {"tools": {name: True for name in self.tool_names}}
        tool_defs = tool_registry.get_tool_definitions(agent_config)
        tools_arg = tool_defs if tool_defs else None

        if not tools_arg:
            # 无工具 → 纯流式 (与旧行为完全一致)
            async for token in llm_gateway.chat_stream(
                messages,
                temperature=0.7,
                max_tokens=4096,
                base_url=base_url,
            ):
                yield token
            return

        # 工具循环: 先用非流式调用来检测/执行工具调用
        last_content = ""
        for iteration in range(MAX_TOOL_ITERATIONS):
            try:
                result = await llm_gateway.chat(
                    messages,
                    temperature=0.7,
                    max_tokens=4096,
                    tools=tools_arg,
                    base_url=base_url,
                )
            except Exception as e:
                print(f"[Role:{self.id}] ⚠ 流式工具循环内 LLM 异常: {e}")
                yield last_content or f"[推理失败: {e}]"
                return

            content = result.get("content") or ""
            # 30B MoE 思考模式：提取 reasoning，作为折叠的思维链展示
            reasoning = result.get("reasoning") or ""
            if reasoning and content:
                yield f'\n<thinking>{reasoning}</thinking>\n'
            elif not content:
                reasoning = reasoning or ""
                if reasoning:
                    content = reasoning
                    print(f"[Role:{self.id}] ℹ 流式模式回退 reasoning ({len(reasoning)} chars)")
            last_content = content or last_content
            tool_calls = result.get("tool_calls") or []

            # 去重 & 上限（同非流式路径）
            if tool_calls:
                tool_calls = _dedup_tool_calls(tool_calls)
                if len(tool_calls) > MAX_TOOL_CALLS_PER_TURN:
                    print(f"[Role:{self.id}] ⚠ 单轮工具调用超限: {len(tool_calls)} → 截断为 {MAX_TOOL_CALLS_PER_TURN}")
                    tool_calls = tool_calls[:MAX_TOOL_CALLS_PER_TURN]

            if not tool_calls:
                # 模型不再要求调工具 → 用流式产出最终回复
                break

            # 通知前端正在执行工具
            tool_names = [tc.get("function", {}).get("name", "?") for tc in tool_calls]
            yield f"\n[🔧 调用工具: {', '.join(tool_names)}] "

            # 回写 assistant 消息 (含 tool_calls)
            messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": [
                    {
                        "id": tc.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": tc.get("function", {}).get("name", ""),
                            "arguments": tc.get("function", {}).get("arguments", "{}"),
                        },
                    }
                    for tc in tool_calls
                ],
            })

            # 逐个执行工具
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                raw_args = fn.get("arguments", "{}") or "{}"

                try:
                    args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                except (json.JSONDecodeError, TypeError, ValueError):
                    args = {}
                    print(f"[Role:{self.id}] ⚠ 流式工具参数解析失败: {name}")

                try:
                    tool_result = await tool_registry.execute_tool(name, args, agent_config)
                except Exception as e:
                    tool_result = {"success": False, "error": f"工具执行异常: {e}"}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id", ""),
                    "content": json.dumps(tool_result, ensure_ascii=False, default=str),
                })

                # 工具执行状态反馈
                ok = "✓" if tool_result.get("success") else "✗"
                yield f"\n[{ok} {name}] "

        # 流式产出最终回复
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