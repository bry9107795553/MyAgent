"""
MasterRole — 主控角色 (前台接待 + 调度中心)

架构定位:
    主控是整个系统的唯一对外接口。用户的所有请求都经过主控，由主控:
        1. 分析请求 → 匹配预设工作组或动态组装角色
        2. 分发任务 → 通过黑板向角色下发任务
        3. 收集结果 → 从黑板拉取角色产出
        4. 防火墙 → 脱敏、裁剪、路由
        5. 报告进度 → 向用户反馈当前状态

    主控是"纯粹调度者"——不自己做需求挖掘、不教学、不写代码。
    它只做一件事: 把请求路由到正确的角色，然后汇总结果。

与 dispatcher_config.json 的关系:
    主控在初始化时加载调度器配置，所有匹配逻辑由配置驱动:
        - matching.strategy: 关键词优先 → 语义匹配 → 动态组装
        - dynamic_assembly.rules: 动态组装规则
        - dynamic_assembly.capability_to_role_map: 能力→角色映射
        - firewall_rules: 防火墙规则
        - error_handling: 错误处理策略

与黑板的关系:
    主控是黑板防火墙——所有跨角色通信必须经过主控的路由方法。
    角色不直接通信，主控负责:
        1. 脱敏: 裁剪内部推理，只保留结论
        2. 去作者: 用"某角色"替代具体角色名
        3. 最小信息: 只传递该角色执行任务所需的最小信息
"""
import asyncio
import json
import re
from pathlib import Path
from typing import Optional, AsyncGenerator

from core.role.role_base import RoleBase, RoleContext, PROMPT_SECTIONS
from core.memory.blackboard import blackboard, BlackboardEntry
from core.memory.store import generate_id, now_iso
from core.project.project_status import project_status
from core.agent.orchestrator import secretary, Secretary


# ===== 调度器配置路径 =====

DATA_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "data"
)

DISPATCHER_CONFIG_PATH = DATA_DIR / "dispatcher_config.json"
ROLE_POOL_PATH = DATA_DIR / "role_pool.json"
WORKGROUPS_DIR = DATA_DIR / "workgroups"


class MasterRole(RoleBase):
    """
    主控角色 — 前台接待 + 调度中心

    职责:
        1. 接收用户请求
        2. 分析请求，匹配角色
        3. 分发任务到角色 (通过黑板)
        4. 收集角色产出
        5. 脱敏后汇总返回给用户
    """

    def __init__(self, role_def: dict):
        super().__init__(role_def)
        self._dispatcher_config: dict = {}
        self._role_pool: dict[str, dict] = {}
        self._loaded_roles: dict[str, RoleBase] = {}  # 已加载的角色实例
        self._workgroups: dict[str, dict] = {}         # 已加载的工作组配置
        self._pending_plan: dict = {}                   # 待确认的执行计划 {wg, msg}

    # ------------------------------------------------------------------ #
    # 初始化
    # ------------------------------------------------------------------ #

    def init(self, session_id: str = ""):
        """初始化主控 (加载调度器配置 + 角色池 + 工作组 + 秘书)"""
        super().init(session_id)
        self._load_dispatcher_config()
        self._load_role_pool()
        self._load_workgroups()

        # 初始化秘书 (上下文管理员)
        secretary.init(session_id, llm_call=self._call_llm_raw)
        print(f"[Master] 秘书已初始化 | 会话: {session_id}")

        return self

    def register_role(self, role: RoleBase):
        """注册角色实例 (供 RoleLoader 调用)"""
        self._loaded_roles[role.id] = role
        print(f"[Master] 注册角色: {role.id} ({role.name})")

    # ------------------------------------------------------------------ #
    # 7 段式提示词
    # ------------------------------------------------------------------ #

    def _build_system_prompt(self) -> str:
        return f"""# 身份 (Identity)
你是「主控」—— MyAgent 系统的前台接待和调度中心。
你是用户唯一的对话入口，负责理解用户意图、匹配合适角色、分发任务、汇总结果。

## 系统能力清单（诚实告知，不编造）
**你有 tools: file_read, file_write, file_list。用它们真干活，不要文字描述"调用了某个工具"。**

你可以调度的真实角色：coach(需求分析)、designer(界面设计)、developer(代码开发)、inspector(代码审查)、tester(测试)、deployer(部署)、cleaner(清理)、writer(写作)、quality_checker(质检)、translator(翻译)、knowledge_retriever(知识检索)、visual_analyzer(视觉分析)、creative(创意)、scheduler(日程)。

**你没有且绝不编造的角色**：weather(天气)、file_manager(文件管理)、poet(诗人)、programmer(程序员)、任何不在上述列表的角色。没有网络搜索，不知道实时天气/新闻。

**关于你自己的运行环境**：AMD Radeon PRO W7900 GPU，48GB VRAM，Qwen2.5-14B 模型，llama.cpp + ROCm 推理。你有 file_read/file_write/file_list 工具。

# 职责 (Responsibilities)
1. 接收用户请求，分析意图
2. 匹配预设工作组或动态组装角色
3. 向角色下发任务 (通过黑板)
4. 收集角色产出，汇总返回用户
5. 防火墙: 脱敏、裁剪、路由角色间通信
6. 向用户报告进度

# 边界 (Boundaries)
- 你只做调度，不自己做需求挖掘、不教学、不写代码
- 你不直接调用 LLM 做推理，推理由调度到的角色完成
- 简单问候/闲聊直接回复，不需要调度角色
- 开发类任务: 先派教练 (coach) 做需求发现，再执行

# 输出 (Output)
- 向用户汇报时: 简洁、结构化、标注进度
- 向角色下发任务时: 只传递最小必要信息
- 返回格式: 直接给出结果，不暴露内部调度细节

# 标准 (Standards)
- 准确率: 不编造、不猜测，不确定时向用户确认
- 效率: 能用单角色完成的任务不组装工作组
- 防火墙: 角色间通信必须脱敏，不泄露作者身份

# 记忆 (Memory)
- 你可以访问所有角色的记忆摘要 (L1/L2)
- 你可以查询知识图谱 (L3) 获取跨会话知识
- 你可以通过黑板查看角色间通信

# 工具 (Tools)
- dispatch: 向角色下发任务
- route: 角色间消息路由 (防火墙)
- workgroup_manager: 预设工作组管理
- memory_query: 跨角色记忆查询
- user_interaction: 向用户提问或确认
"""

    # ------------------------------------------------------------------ #
    # 上下文精简 (主控是路由器，不是 LLM 对话者)
    # ------------------------------------------------------------------ #

    def _assemble_context(self, task: str, task_id: str, extra_context: str = ""):
        """主控上下文: 10轮 = 20条 — 保留足够记忆用于多轮对话"""
        ctx = super()._assemble_context(task, task_id, extra_context)
        ctx.l0_messages = self._wm.get_recent(n=20)  # 10 轮 (user+assistant)
        return ctx

    # ------------------------------------------------------------------ #
    # 配置加载
    # ------------------------------------------------------------------ #

    def _load_dispatcher_config(self):
        """加载调度器配置"""
        if DISPATCHER_CONFIG_PATH.exists():
            with open(DISPATCHER_CONFIG_PATH, "r", encoding="utf-8-sig") as f:
                self._dispatcher_config = json.load(f)
            print(f"[Master] 已加载调度器配置: {DISPATCHER_CONFIG_PATH}")
        else:
            print(f"[Master] ⚠ 调度器配置不存在: {DISPATCHER_CONFIG_PATH}")
            self._dispatcher_config = {}

    def _load_role_pool(self):
        """加载角色池定义"""
        if ROLE_POOL_PATH.exists():
            with open(ROLE_POOL_PATH, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
            for role_def in data.get("roles", []):
                self._role_pool[role_def["id"]] = role_def
            print(f"[Master] 已加载角色池: {len(self._role_pool)} 个角色")
        else:
            print(f"[Master] ⚠ 角色池文件不存在: {ROLE_POOL_PATH}")

    def _load_workgroups(self):
        """加载所有预设工作组配置"""
        if not WORKGROUPS_DIR.exists():
            print(f"[Master] ⚠ 工作组目录不存在: {WORKGROUPS_DIR}")
            return

        for wg_file in WORKGROUPS_DIR.glob("*.json"):
            try:
                with open(wg_file, "r", encoding="utf-8-sig") as f:
                    wg = json.load(f)
                wg_id = wg.get("id", wg_file.stem)
                self._workgroups[wg_id] = wg
            except Exception as e:
                print(f"[Master] ⚠ 加载工作组失败 {wg_file.name}: {e}")

        print(f"[Master] 已加载 {len(self._workgroups)} 个预设工作组: "
              f"{list(self._workgroups.keys())}")

    # ------------------------------------------------------------------ #
    # 核心调度: 工作组匹配 → 关键词匹配 → 执行
    # ------------------------------------------------------------------ #

    async def dispatch(self, user_message: str) -> dict:
        """
        分析用户消息并调度

        流程:
            1. 简单问候 → 直接回复
            2. 匹配预设工作组 (trigger_keywords 精确匹配)
            3. 工作组命中 → 按 pipeline DAG 执行各步骤
            4. 工作组未命中 → 关键词匹配角色 → 并行分发
            5. 都未匹配 → 主控自己处理

        每轮调度后更新秘书的运行时状态。

        :param user_message: 用户消息
        :return: {"type": "direct"|"workgroup"|"dispatched",
                  "content": str, "roles_used": [...], "workgroup": str|None}
        """
        # 0. 注入项目上下文 (开发相关消息时自动附加上一个活跃项目状态)
        enhanced_message = self.inject_project_context(user_message)

        result: dict = {}

        # 1. 简单问候/闲聊 → 直接回复
        if self._is_simple_greeting(user_message):
            result = {
                "type": "direct",
                "content": await self._handle_greeting(user_message),
                "roles_used": [],
                "workgroup": None,
            }
        else:
            # 2. 尝试匹配预设工作组
            matched_wg = self._match_workgroup(enhanced_message)
            if matched_wg:
                result = {
                    "type": "workgroup",
                    "content": await self._execute_pipeline(matched_wg, enhanced_message),
                    "roles_used": matched_wg.get("members", []),
                    "workgroup": matched_wg.get("id"),
                }
            else:
                # 3. 工作组未命中 → 关键词匹配角色
                matched_roles = self._keyword_match_roles(enhanced_message)
                if matched_roles:
                    results = await self._dispatch_to_roles(enhanced_message, matched_roles)
                    content = self._aggregate_results(enhanced_message, results)
                    result = {
                        "type": "dispatched",
                        "content": content,
                        "roles_used": [r["id"] for r in matched_roles],
                        "workgroup": None,
                    }
                else:
                    # 4. 都未匹配 → 主控自己处理
                    result = {
                        "type": "direct",
                        "content": await self._handle_general(enhanced_message),
                        "roles_used": [],
                        "workgroup": None,
                    }

        # 5. 秘书记录本轮对话
        secretary.record_turn(
            user_message=user_message,
            role_response=result.get("content", ""),
            role_id=result.get("workgroup") or (
                (result.get("roles_used") or [None])[0] or "master"
            ),
        )

        # 6. 检查是否需要增量摘要 (异步，不阻塞)
        if secretary.should_summarize():
            asyncio.create_task(secretary.generate_summary())

        return result

    async def dispatch_stream(self, user_message: str) -> AsyncGenerator[str, None]:
        """
        流式调度 — 三级分流
        Level 1: 自己干（闲聊/问答/简单任务）
        Level 2: 派一个人干（专业任务但单步即可）
        Level 3: 组团干（多角色协作流水线）
        """
        self._last_stream_dispatch = {"type": "direct", "workgroup": None, "roles_used": []}
        yield "[前台] "

        if self._is_simple_greeting(user_message):
            async for chunk in self._stream_greeting(user_message):
                yield chunk
            return

        # Plan-First 确认检查
        if self._pending_plan and self._is_confirmation(user_message):
            pending = self._pending_plan
            self._pending_plan = {}
            yield "好的，开始执行 👇\n"
            async for token in self._execute_workgroup_stream(pending["wg"], pending["msg"], pending["pipeline"]):
                yield token
            return

        if self._pending_plan:
            self._pending_plan = {}

        # ── 多任务拆解: 按句号/连接词切分，逐条分发 ──
        tasks = self._split_tasks(user_message)
        if len(tasks) > 1:
            yield f"[检测到 {len(tasks)} 个子任务，依次处理]\n"
            for i, task in enumerate(tasks):
                yield f"\n── 子任务 {i+1}/{len(tasks)} ──\n"
                async for token in self._dispatch_single(task):
                    yield token
            return

        # 机械拆分失败 + 消息>30字 → 调用拆解员
        if len(user_message) > 30:
            yield "[拆解中…] "
            decomposed = await self._decompose_task(user_message)
            if decomposed and len(decomposed) > 1:
                yield f"识别出 {len(decomposed)} 个子任务\n"
                for i, task in enumerate(decomposed):
                    yield f"\n── 子任务 {i+1}/{len(decomposed)} ──\n"
                    async for token in self._dispatch_single(task):
                        yield token
                return

        async for token in self._dispatch_single(user_message):
            yield token
        return

    async def _dispatch_single(self, user_message: str) -> AsyncGenerator[str, None]:
        """单任务分发（被 dispatch_stream 多任务拆解后调用）"""
        # ── 三级分流 ──
        level, detail = self._classify_task(user_message)

        if level == 1:
            # Level 1: 自己干 — 问答、闲聊、简单任务
            task_id = generate_id("task")
            ctx = self._assemble_context(user_message, task_id, "")
            # 立即给用户视觉反馈，避免「卡死」错觉
            yield "[正在思考…] "
            full_response = []
            async for token in self._call_llm_stream(ctx):
                full_response.append(token)
                yield token
            self._record_task(user_message, "".join(full_response), task_id)
            secretary.record_turn(user_message=user_message, role_response="".join(full_response), role_id="master")
            return

        elif level == 2:
            # Level 2: 派一个人干 — 翻译、简单写作、知识检索
            if detail:  # detail = matched role list
                self._last_stream_dispatch = {"type": "roles", "workgroup": None, "roles_used": [r["id"] for r in detail]}
                yield f"[已匹配 {len(detail)} 个角色: "
                yield ", ".join(r["name"] for r in detail)
                yield "] "
                yield "[正在执行…] "
                results = await self._dispatch_to_roles(user_message, detail)
                if not results:
                    # 角色执行失败 → 降级走通用 LLM
                    task_id = generate_id("task")
                    ctx = self._assemble_context(user_message, task_id, "")
                    full_response = []
                    async for token in self._call_llm_stream(ctx):
                        full_response.append(token)
                        yield token
                    self._record_task(user_message, "".join(full_response), task_id)
                    return
                content = self._aggregate_results(user_message, results)
                yield content
                self._record_task(user_message, content, generate_id("task"))
                secretary.record_turn(user_message=user_message, role_response=content, role_id=detail[0]["id"] if detail else "master")
                return
            else:
                # 没有匹配到具体角色 → 降级 Level 1
                task_id = generate_id("task")
                ctx = self._assemble_context(user_message, task_id, "")
                full_response = []
                async for token in self._call_llm_stream(ctx):
                    full_response.append(token)
                    yield token
                self._record_task(user_message, "".join(full_response), task_id)
                return

        else:  # level == 3
            # Level 3: 组团干 — 开发流水线或复杂工作组
            matched_wg = detail  # detail = matched workgroup
            wg_id = matched_wg.get("id", "")
            pipeline = matched_wg.get("pipeline", [])

            # Plan-First: 开发类 → 模糊需求展示计划，明确需求直接执行
            if matched_wg.get("conditions", {}).get("auto_approve") and wg_id.startswith("dev_"):
                # 开发类只看有没有"开发/做/建 + 实体"动词
                is_specific = bool(re.search(r'(开发|做|建|搭|创建|实现|写)', user_message)) and len(user_message.strip()) >= 8 and not re.search(r'[？?吗呃吧呢]$', user_message)

                if not is_specific:
                    plan = self._build_execution_plan(matched_wg, user_message)
                    self._pending_plan = {"wg": matched_wg, "msg": user_message, "pipeline": pipeline}
                    self._last_stream_dispatch = {
                        "type": "workgroup",
                        "workgroup": matched_wg.get("name", wg_id),
                        "roles_used": matched_wg.get("members", []),
                    }
                    yield plan
                    return
                # 需求明确，直接执行
                yield "好的，开始执行 👇\n"

            # 模糊度守卫
            text, options = self._check_vague_request(user_message, matched_wg)
            if text:
                async for chunk in self._stream_text(text, chunk_size=3, delay=0.02):
                    yield chunk
                if options:
                    yield ("[[OPTIONS]]" + json.dumps(options, ensure_ascii=False) + "[[/OPTIONS]]")
                return

            # 复杂工作组 → 直接执行
            async for token in self._execute_workgroup_stream(matched_wg, user_message, pipeline):
                yield token
            secretary.record_turn(
                user_message=user_message,
                role_response="(pipeline)",
                role_id=matched_wg.get("id", "master"),
            )
            return

    # ── 多任务拆解 ──

    def _split_tasks(self, message: str) -> list[str]:
        """按句号、分号、换行和连接词拆分多意图消息为子任务列表"""
        import re
        msg = message.strip()
        # 1. 先按连接词+标点拆分
        connectors = r'(。|；|;|\n|然后|顺便|另外|此外|接着|还有|同时|以及|之后|熟后)'
        parts = re.split(connectors, msg)
        # 2. 合并短片段
        tasks: list[str] = []
        buf = ""
        for p in parts:
            p = p.strip()
            if not p:
                continue
            if p in ["。", "；", ";", "然后", "顺便", "另外", "此外", "接着", "还有", "同时", "以及", "之后", "熟后"]:
                if buf:
                    tasks.append(buf)
                    buf = ""
                continue
            buf += ("；" if buf else "") + p
        if buf:
            tasks.append(buf)
        # 3. 合并过短的片段到相邻任务
        merged: list[str] = []
        for t in tasks:
            if len(t) <= 5 and merged:
                merged[-1] += "；" + t
            else:
                merged.append(t)
        return merged if len(merged) > 1 else [message]

    async def _decompose_task(self, message: str) -> list[str] | None:
        """LLM拆解: 复杂消息拆为独立子任务列表，失败返回 None"""
        try:
            role = self._loaded_roles.get("decomposer")
            if not role:
                return None  # 拆解员未加载（首次启动后可用）
            prompt = role.system_prompt or ""
            ctx = role._assemble_context(
                f"请拆解以下消息为独立子任务:\n{message}", "", ""
            )
            result = await role._call_llm(ctx)
            # 提取 JSON 数组
            m = re.search(r'\[[\s\S]*\]', result, re.DOTALL)
            if m:
                data = json.loads(m.group())
                tasks = [item.get("task", "") for item in data if isinstance(item, dict)]
                return tasks if len(tasks) > 1 else None
            return None
        except Exception as e:
            print(f"[Master] 拆解员调用失败: {e}")
            return None

    def _classify_task(self, message: str) -> tuple[int, object]:
        """
        Level 1: 自己干 | Level 2: 派一个人 | Level 3: 组团干
        :return: (level, detail) — detail 在 L2=角色列表, L3=工作组, L1=None
        """
        msg = message.strip()

        # ── Level 3: 多步骤开发/创建/修改任务 ──
        has_project_verb = any(v in msg for v in ["开发", "做项目", "做一个", "实现一个", "开发个",
                                                    "做个网页", "做个网站", "搭一个项目", "创建项目",
                                                    "前端页面开发", "静态页面制作", "开发一个", "建一个网站"])
        if has_project_verb and len(msg) >= 6:
            wg = self._match_workgroup(message)
            if wg: return (3, wg)

        # 修改/修复 → dev_modification 工作组（存量项目入口）
        if any(k in msg for k in ["修改", "改一下", "修复", "重构", "加功能", "调整一下", "优化一下"]):
            wg = self._match_workgroup(message)
            if wg and wg.get("id", "").startswith("dev_"): return (3, wg)

        # 含"报告/详细分析/长文" + 足够长 → 工作组
        if any(k in msg for k in ["报告", "分析报告", "详细分析", "长文"]) and len(msg) > 20:
            wg = self._match_workgroup(message)
            if wg: return (3, wg)

        # ── Level 2: 单角色专业任务 ──
        # 翻译
        if any(k in msg for k in ["翻译"]):
            r = self._role_pool.get("translator")
            if r and len(msg) < 200: return (2, [r])

        # 知识检索
        if any(k in msg for k in ["搜索", "查资料", "检索", "找文档"]):
            r = self._role_pool.get("knowledge_retriever")
            if r: return (2, [r])

        # 文件阅读/分析 → knowledge_retriever（比 master 自己读快，prompt 专精文件解析）
        has_file_read = any(k in msg for k in ["读", "读取", "查看", "看看", "看", "告诉我", "解释"])
        has_file_name = bool(re.search(r'[\w./-]+\.[\w]{2,5}', msg))
        if has_file_read and has_file_name:
            r = self._role_pool.get("knowledge_retriever")
            if r: return (2, [r])

        # 写作：≤30字简单写作 → writer；>30字复杂写作 → writer 兜底（报告走 L3 工作组）
        if any(k in msg for k in ["写", "写作", "文章", "邮件", "文案"]):
            if len(msg) <= 30 and not any(k in msg for k in ["报告", "详细", "多篇"]):
                r = self._role_pool.get("writer")
                if r: return (2, [r])
            # >30字写作，优先匹配工作组
            wg = self._match_workgroup(message)
            if wg and wg.get("id", "").startswith(("report_", "dev_")): return (3, wg)
            r = self._role_pool.get("writer")
            if r: return (2, [r])  # 没有匹配工作组，兜底派 writer

        # 总结/概括/摘要 → knowledge_retriever
        if any(k in msg for k in ["总结", "概括", "摘要", "汇总", "归纳"]):
            r = self._role_pool.get("knowledge_retriever")
            if r: return (2, [r])

        # 日程/规划/提醒 → scheduler
        if any(k in msg for k in ["规划", "安排", "日程", "提醒", "排期"]):
            r = self._role_pool.get("scheduler")
            if r: return (2, [r])

        # 分析/对比/评估 → knowledge_retriever
        if any(k in msg for k in ["分析", "对比", "评估", "比较"]):
            r = self._role_pool.get("knowledge_retriever")
            if r: return (2, [r])

        # 创意/方案/头脑风暴 → creative
        if any(k in msg for k in ["创意", "方案", "头脑风暴", "点子", "想出"]):
            r = self._role_pool.get("creative")
            if r: return (2, [r])

        # 文学创作/诗歌/故事 → writer（creative 是头脑风暴角色，不适合文学创作）
        if any(k in msg for k in ["诗", "诗歌", "故事", "小说", "一首", "一篇"]):
            r = self._role_pool.get("writer")
            if r: return (2, [r])

        # 文件操作：保存/写文件 → writer 或 creative（根据是否含创作关键词）
        if any(k in msg for k in ["保存到", "存储到", "存到", "写入文件"]):
            r = self._role_pool.get("writer") or self._role_pool.get("creative")
            if r: return (2, [r])

        # 审查/检查 → quality_checker
        if any(k in msg for k in ["审查", "检查", "验证"]):
            match = self._keyword_match_roles(message)
            if match: return (2, match)

        # ── Level 1 兜底: 自己干 ──
        return (1, None)

    @property
    def last_stream_dispatch(self) -> dict:
        return getattr(self, "_last_stream_dispatch", None) or {
            "type": "direct", "workgroup": None, "roles_used": [],
        }

    # ------------------------------------------------------------------ #
    # 意图分析
    # ------------------------------------------------------------------ #

    def _check_vague_request(self, message: str, matched_wg: dict) -> tuple[str, list[dict]]:
        """
        模糊度守卫：开发类需求太宽泛时，先反问用户确认。
        返回 (反问文本, 选项列表)，文本为空表示需求足够清晰。
        """
        wg_id = matched_wg.get("id", "")
        dev_wgs = {"dev_full", "dev_code_review", "dev_design_only", "dev_modification", "dev_tech_debt"}
        if wg_id not in dev_wgs:
            return ("", [])

        msg = message.strip()

        # 追问（不是新需求）：带问号/以"呢/吗"结尾/以"我的"开头 → 不拦截，走通用对话
        import re
        if re.search(r'[？?]$', msg) or re.search(r'(呢|吗|啊|吧)$', msg) or msg.startswith("我的") or msg.startswith("那个"):
            return ("", [])

        # 太短 → 反问用途/风格/功能
        if len(msg) <= 6:
            return (
                f"好的，你想「{msg}」——不过在开始之前，我需要了解几个关键点：\n\n",
                [
                    {"id": "purpose", "label": "用途：作品集/博客/商店/工具？", "multi": False,
                     "options": [
                         {"label": "📁 作品集", "value": "做一个作品集展示页"},
                         {"label": "📝 个人博客", "value": "做一个个人博客"},
                         {"label": "🛒 在线商店", "value": "做一个在线商店"},
                         {"label": "🔧 在线工具", "value": "做一个在线工具/计算器"},
                     ]},
                    {"id": "style", "label": "风格：简约/花哨/暗色？", "multi": False,
                     "options": [
                         {"label": "⚪ 极简白底", "value": "极简白底黑字风格"},
                         {"label": "⚫ 暗色系", "value": "暗色系风格"},
                         {"label": "🎨 彩色活泼", "value": "带色彩和动效的活泼风格"},
                     ]},
                    {"id": "features", "label": "功能：需要哪些？", "multi": True,
                     "options": [
                         {"label": "📞 联系表单", "value": "联系表单"},
                         {"label": "🖼️ 图片画廊", "value": "图片画廊"},
                         {"label": "📱 响应式", "value": "响应式适配手机"},
                         {"label": "🌙 暗色切换", "value": "明暗切换"},
                     ]},
                ]
            )

        # "写/做/开发 + 网页/网站/app" 但无具体需求
        vague_patterns = [
            r'^(写|做|开发|帮我|给我)\s*(一个?|个)\s*(网页|网站|页面|app|应用|程序)\s*[。！!！?？]*$',
            r'^(写|做|开发)\s*(个人|公司|企业)\s*(网页|网站|页面)\s*[。！!！?？]*$',
        ]
        import re
        for pat in vague_patterns:
            if re.match(pat, msg):
                return (
                    f"收到，你想做一个「{msg}」——在动手之前，先聊两句：\n\n",
                    [
                        {"id": "purpose", "label": "做什么用的？", "multi": False,
                         "options": [
                             {"label": "📁 作品集", "value": f"做一个作品集展示用的{msg}"},
                             {"label": "📝 个人博客", "value": f"做一个个人博客{msg}"},
                             {"label": "🛒 卖东西", "value": f"做一个卖东西的{msg}"},
                             {"label": "🔧 在线工具", "value": f"做一个在线工具{msg}"},
                         ]},
                        {"id": "pages", "label": "几个页面？", "multi": False,
                         "options": [
                             {"label": "1️⃣ 单页", "value": "单页就够"},
                             {"label": "3️⃣ 3-5 页", "value": "3-5 个页面"},
                             {"label": "📚 详细多页", "value": "首页+关于+联系+项目页等多个"},
                         ]},
                        {"id": "style", "label": "风格偏好？", "multi": False,
                         "options": [
                             {"label": "⚪ 简约白底", "value": "简约白底黑字风格"},
                             {"label": "⚫ 暗色专业", "value": "暗色系专业风格"},
                             {"label": "🎨 彩色活泼", "value": "彩色活泼有动画的风格"},
                         ]},
                    ]
                )

        return ("", [])

    def _is_confirmation(self, message: str) -> bool:
        """判断用户是否在确认执行计划"""
        msg = message.strip().lower()
        confirms = {"好的", "好", "开始", "确认", "继续", "行", "可以", "ok", "yes", "go", "是", "对", "嗯", "搞", "做"}
        return msg in confirms or len(msg) <= 3 and any(c in msg for c in confirms)

    def _build_execution_plan(self, wg: dict, user_message: str) -> str:
        """生成执行计划展示给用户确认"""
        wg_name = wg.get("name", wg.get("id", "工作组"))
        pipeline = wg.get("pipeline", [])
        lines = [f"📋 **执行计划 — {wg_name}**\n"]
        lines.append("根据你的需求，我计划按以下步骤执行：\n")
        for step in sorted(pipeline, key=lambda s: s.get("step", 0)):
            role = step.get("role", "?")
            action = step.get("action", "")
            # 取 action 的第一句话作为简述
            brief = action.split("。")[0].split(".")[0][:80]
            lines.append(f"> **{step.get('step', '?')}. {role}** — {brief}")
        lines.append(f"\n共 {len(pipeline)} 个角色参与。确认开始？输入「好的」继续，或提出修改意见。")
        return "\n".join(lines)

    async def _execute_workgroup_stream(self, wg: dict, user_message: str, pipeline: list):
        """执行工作组流水线，流式返回进度"""
        import asyncio
        import re
        wg_name = wg.get("name", wg.get("id"))
        self._last_stream_dispatch = {
            "type": "workgroup",
            "workgroup": wg_name,
            "roles_used": wg.get("members", []),
        }
        pq = asyncio.Queue()

        async def _on_step(step_num, role_id, status, total, output):
            summary = ""
            if output:
                lines = [l.strip() for l in output.split('\n') if l.strip() and not l.strip().startswith('#')]
                if lines:
                    summary = re.sub(r'^[-*>`|]+\s*', '', lines[0])[:120]
            await pq.put((
                f"\n\n__PIPE__{step_num}/{total} {role_id} {status}",
                role_id, summary, output or "",
            ))

        pipe_task = asyncio.ensure_future(
            self._execute_pipeline(wg, user_message, step_callback=_on_step)
        )
        buf = ""
        while not pipe_task.done():
            try:
                evt, rid, summary, output = await asyncio.wait_for(pq.get(), timeout=0.3)
                buf += evt
                status_icon = "✅" if "done" in evt else "❌"
                if summary:
                    buf += f"\n\n{status_icon} **{rid}** — {summary}\n"
                if output and len(output) > 200:
                    buf += f"<details class=\"output-fold\"><summary>📄 查看完整产出</summary><div class=\"output-content\">\n\n{output}\n\n</div></details>\n"
                elif output:
                    buf += f"\n{output}\n"
            except asyncio.TimeoutError:
                if buf: yield buf; buf = ""
                continue
        while not pq.empty():
            evt, rid, summary, output = pq.get_nowait()
            buf += evt
            status_icon = "✅" if "done" in evt else "❌"
            if summary:
                buf += f"\n\n{status_icon} **{rid}** — {summary}\n"
            if output and len(output) > 200:
                buf += f"<details class=\"output-fold\"><summary>📄 查看完整产出</summary><div class=\"output-content\">\n\n{output}\n\n</div></details>\n"
            elif output:
                buf += f"\n{output}\n"
        if buf: yield buf
        await pipe_task

    def _is_simple_greeting(self, message: str) -> bool:
        """判断是否为简单问候/闲聊 (不调度)。严格匹配，防止误判短消息"""
        msg = message.strip().lower()
        greetings = {
            "你好", "hi", "hello", "hey", "嗨", "早", "早安", "晚安", "晚上好", "早上好",
            "谢谢", "再见", "bye", "拜拜", "感谢",
            "在吗", "在么", "在?", "在？",
        }
        return msg in greetings

    async def _handle_greeting(self, message: str) -> str:
        """处理简单问候"""
        reply = f"你好！我是 MyAgent 助手，有什么可以帮你的？"
        self._record_task(message, reply, generate_id("task"))
        return reply

    async def _stream_greeting(self, message: str):
        """流式问候（逐字 yield）"""
        reply = f"你好！我是 MyAgent 助手，有什么可以帮你的？"
        async for chunk in self._stream_text(reply, chunk_size=3, delay=0.02):
            yield chunk
        self._record_task(message, reply, generate_id("task"))

    async def _stream_text(self, text: str, chunk_size: int = 3, delay: float = 0.015):
        """将文本切成小段逐块 yield，模拟真实流式输出"""
        import asyncio
        for i in range(0, len(text), chunk_size):
            yield text[i:i + chunk_size]
            await asyncio.sleep(delay)

    async def _handle_general(self, message: str) -> str:
        """处理通用对话 (未匹配到角色，主控自己 LLM 处理)"""
        task_id = generate_id("task")
        ctx = self._assemble_context(message, task_id, "")
        result = await self._call_llm(ctx)
        self._record_task(message, result, task_id)
        return result

    async def _call_llm_raw(self, messages: list[dict], **kwargs) -> dict:
        """
        原始 LLM 调用 (供秘书使用)

        :param messages: LLM 消息列表
        :param kwargs: 额外参数 (max_tokens, temperature 等)
        :return: {"content": str, ...}
        """
        from core.llm.gateway import llm_gateway

        result = await llm_gateway.chat(
            messages,
            temperature=kwargs.get("temperature", 0.7),
            max_tokens=kwargs.get("max_tokens", 4096),
            base_url=self._get_gpu_url(),
        )
        return result

    # ------------------------------------------------------------------ #
    # 角色匹配 (三步策略)
    # ------------------------------------------------------------------ #

    # ── 工作组匹配 (Step 1) ──

    def _match_workgroup(self, message: str) -> Optional[dict]:
        """
        遍历所有预设工作组，按 trigger_keywords 精确匹配

        匹配规则:
            1. 用户消息中包含任一关键词 → 命中
            2. 多个工作组命中时，取关键词匹配数最多的
            3. 都未命中返回 None

        :param message: 用户消息
        :return: 匹配的工作组配置，或 None
        """
        msg_lower = message.lower()
        best_match: Optional[dict] = None
        best_score = 0

        for wg_id, wg in self._workgroups.items():
            keywords = wg.get("trigger_keywords", [])
            score = sum(1 for kw in keywords if kw.lower() in msg_lower)
            if score > best_score:
                best_score = score
                best_match = wg

        if best_match:
            print(f"[Master] 工作组匹配: {best_match['id']} "
                  f"(命中 {best_score} 个关键词)")

        return best_match

    # ── 关键词匹配 (Step 2) ──

    def _keyword_match_roles(self, message: str) -> list[dict]:
        """
        基于能力关键词匹配角色 (工作组未命中时的回退策略)

        :param message: 用户消息
        :return: 匹配的角色定义列表
        """
        capability_map = self._dispatcher_config.get(
            "dynamic_assembly", {}
        ).get("capability_to_role_map", {})

        msg_lower = message.lower()
        matched_role_ids: set[str] = set()

        # 关键词→能力 映射
        keyword_to_capability = {
            # 知识检索
            "搜索": "web_search", "查": "web_search", "搜": "web_search",
            "找资料": "rag_search", "检索": "rag_search",
            "文档": "document_parsing",
            # 写作（去掉"写"——太宽泛，普通写作由 master 直接 LLM 回答）
            "写作": "report_writing", "撰稿": "report_writing",
            "报告": "report_writing", "总结": "report_writing",
            "文章": "report_writing", "论文": "report_writing",
            "邮件": "email_drafting", "文案": "copywriting",
            # 翻译
            "翻译": "translation", "translate": "translation",
            # 设计
            "设计": "design_system", "UI": "design_system",
            "页面": "page_inventory", "界面": "design_system",
            # 开发
            "代码": "module_implementation", "开发": "module_implementation",
            "实现": "module_implementation", "bug": "module_implementation",
            "修复": "module_implementation", "重构": "module_implementation",
            "需求": "requirement_discovery",
            # 质检
            "检查": "fact_checking", "审查": "fact_checking",
            "逻辑": "logic_verification", "事实": "fact_checking",
            # 巡检
            "架构": "architecture_review", "巡检": "architecture_review",
            "代码审查": "architecture_review", "code review": "architecture_review",
            # 测试
            "测试": "unit_test", "编译": "compilation_check",
            "lint": "lint_check",
            # 部署
            "部署": "deploy", "上线": "deploy", "发布": "deploy",
            "构建": "build",
            # 创意
            "创意": "brainstorming", "头脑风暴": "brainstorming",
            "灵感": "brainstorming", "方案": "brainstorming",
            # 日程
            "日程": "schedule_scanning", "提醒": "schedule_scanning",
            "时间": "time_management",
            # 图片
            "图片": "image_analysis", "图像": "image_analysis",
            "截图": "image_analysis",
            # 清理
            "清理": "garbage_scan", "临时文件": "unused_file_detection",
            # 人资管理
            "角色管理": "role_audit", "提示词": "prompt_optimization",
            "导出对话": "conversation_export",
        }

        for keyword, capability in keyword_to_capability.items():
            if keyword in msg_lower:
                role_ids = capability_map.get(capability, "")
                if isinstance(role_ids, str):
                    matched_role_ids.add(role_ids)
                elif isinstance(role_ids, list):
                    matched_role_ids.update(role_ids)

        # 质量门禁规则：复杂任务加质检，简单任务不加
        # 规则：任务消息 > 50 字符 或 明确写了"报告/文章/长文" → 加 quality_checker
        content_production = {"report_writing", "email_drafting", "copywriting"}
        is_complex = len(message.strip()) > 50 or any(kw in message for kw in ["报告", "文章", "论文", "长文", "详细"])
        for cap in content_production:
            if capability_map.get(cap) in matched_role_ids:
                if is_complex:
                    matched_role_ids.add("quality_checker")
                # 简单写作不追加质检

        # 开发类任务: 先加 coach
        dev_capabilities = {"module_implementation", "design_system", "architecture_review"}
        if any(
            capability_map.get(c) in matched_role_ids
            for c in dev_capabilities
        ):
            matched_role_ids.add("coach")

        # 转换为角色定义
        result = []
        for rid in matched_role_ids:
            if rid in self._role_pool:
                result.append(self._role_pool[rid])

        return result

    # ── 流水线执行 (Step 3) ──

    async def _execute_pipeline(self, workgroup: dict, user_message: str,
                                step_callback=None) -> str:
        """
        按工作组 pipeline DAG 顺序执行各步骤

        执行逻辑:
            1. 应用动态规则: coach_first (开发类先跑 coach), cleanup_hook (开发类后清理)
            2. 按 step 编号排序，逐步骤执行
            3. 每步骤: 构建任务包 → 带超时/重试执行 → 收集结果
            4. 支持 parallel_with: 同一步骤可并行执行多个角色
            5. 支持 revision_loop: 条件不满足时跳回前面的步骤

        :param workgroup: 工作组配置
        :param user_message: 用户原始消息
        :param step_callback: 可选异步回调，每步完成时调用 async cb(step_num, role_id, status, total, output)
        :return: 汇总后的执行结果
        """
        wg_name = workgroup.get("name", workgroup.get("id"))
        wg_id = workgroup.get("id")
        pipeline = workgroup.get("pipeline", [])
        conditions = workgroup.get("conditions", {})
        max_revisions = conditions.get("max_revisions", 3)

        if not pipeline:
            return f"[工作组「{wg_name}」未定义流水线步骤]"

        # 动态规则: coach_first — 开发类任务确保 coach 先跑
        pipeline = self._apply_coach_first(pipeline, wg_id)

        # 动态规则: cleanup_hook — 开发类任务结束后自动追加 cleaner
        pipeline = self._apply_cleanup_hook(pipeline, wg_id)

        # 动态规则: experience_eval_hook — 开发类任务收尾后追加经验评估员（方案 C-4，按工作组 members 开关）
        pipeline = self._apply_experience_eval_hook(workgroup, wg_id)

        # 按 step 编号排序
        sorted_pipeline = sorted(pipeline, key=lambda s: s.get("step", 0))

        # 超时配置
        error_config = self._dispatcher_config.get("error_handling", {})
        timeout = error_config.get("role_timeout", {}).get("timeout_seconds", 120)

        # 执行状态追踪
        step_results: dict[str, str] = {}
        revision_counts: dict[str, int] = {}
        execution_log: list[str] = []

        current_step_idx = 0
        while current_step_idx < len(sorted_pipeline):
            step_def = sorted_pipeline[current_step_idx]
            step_num = step_def.get("step", current_step_idx + 1)
            role_id = step_def.get("role", "")
            action = step_def.get("action", "")
            step_key = f"step_{step_num}"

            # 检查返工上限
            if revision_counts.get(step_key, 0) >= max_revisions:
                print(f"[Master] 步骤 {step_key} 已达最大返工次数 {max_revisions}，跳过")
                execution_log.append(
                    f"⚠ 步骤 {step_num} ({role_id}) 已达返工上限，跳过"
                )
                current_step_idx += 1
                continue

            # 获取主角色实例 + 并行角色实例
            parallel_role_ids = step_def.get("parallel_with", [])
            if isinstance(parallel_role_ids, str):
                parallel_role_ids = [parallel_role_ids]

            all_role_ids = [role_id] + [r for r in parallel_role_ids if r and r != role_id]

            # 收集所有需要执行的角色
            roles_to_run: list[tuple[str, object, str]] = []
            for rid in all_role_ids:
                r = self._loaded_roles.get(rid)
                if not r:
                    print(f"[Master] 工作组 {wg_id} 步骤 {step_num}: "
                          f"角色 {rid} 未注册，跳过")
                    execution_log.append(f"⚠ 步骤 {step_num}: 角色 {rid} 未注册，跳过")
                    continue
                task = self._build_pipeline_task(
                    user_message=user_message,
                    step_def={"role": rid, "action": action if rid == role_id else f"并行辅助: {action}",
                              "input_from": step_def.get("input_from", "user"),
                              "output_to": step_def.get("output_to", ""),
                              "parallel_with": [], "condition": ""},
                    previous_results=step_results,
                    wg_name=wg_name,
                )
                roles_to_run.append((rid, r, task))

            if not roles_to_run:
                current_step_idx += 1
                continue

            # 并行或串行执行
            if len(roles_to_run) > 1:
                print(f"[Master] 工作组 {wg_id} → 步骤 {step_num}: "
                      f"{len(roles_to_run)} 个角色并行执行")

                async def _run_one(rid: str, r: object, t: str) -> tuple[str, str]:
                    tid = generate_id("task")
                    try:
                        res = await asyncio.wait_for(
                            r.execute(t, tid, extra_context=f"工作组: {wg_name}\n步骤: {step_num}"),
                            timeout=timeout,
                        )
                        return (rid, res)
                    except asyncio.TimeoutError:
                        return (rid, f"[⚠ {r.name} 超时 ({timeout}s)]")
                    except Exception as e:
                        return (rid, f"[⚠ {r.name} 执行失败: {e}]")

                parallel_results = await asyncio.gather(
                    *[_run_one(rid, r, t) for rid, r, t in roles_to_run],
                    return_exceptions=True,
                )

                for pr in parallel_results:
                    if isinstance(pr, tuple):
                        rid, res = pr
                        # 主角色存标准 key，并行角色存带后缀的 key
                        if rid == role_id:
                            step_results[step_key] = res
                        else:
                            step_results[f"step_{step_num}_{rid}"] = res
                        ok = "✗" if res.startswith("[⚠") else "✓"
                        execution_log.append(f"{ok} 步骤 {step_num}: {rid} 完成")
                        if step_callback:
                            await step_callback(step_num, rid,
                                               "done" if ok == "✓" else "error",
                                               len(sorted_pipeline), res)
                    else:
                        print(f"[Master] 并行执行异常: {pr}")
            else:
                # 单角色串行执行
                rid, r, task = roles_to_run[0]
                task_id = generate_id("task")
                result = await self._execute_with_retry(
                    role=r,
                    task=task,
                    task_id=task_id,
                    extra_context=f"工作组: {wg_name}\n流水线步骤: {step_num}/{len(sorted_pipeline)}",
                    timeout=timeout,
                    max_retries=1,
                )
                step_results[step_key] = result
                ok = "✗" if result.startswith("[⚠") else "✓"
                execution_log.append(f"{ok} 步骤 {step_num}: {rid} 完成")
                if step_callback:
                    await step_callback(step_num, rid, "done" if ok == "✓" else "error",
                                       len(sorted_pipeline), result)

            # 检查是否需要返工
            condition = step_def.get("condition", "")
            if self._should_revise(condition, step_results, revision_counts, max_revisions):
                revision_counts[step_key] = revision_counts.get(step_key, 0) + 1
                output_to = step_def.get("output_to", "")
                prev_step = self._find_prev_step_by_output(
                    sorted_pipeline, output_to, step_num
                )
                if prev_step is not None:
                    current_step_idx = prev_step
                    print(f"[Master] 返工: 步骤 {step_num} → 步骤 "
                          f"{sorted_pipeline[current_step_idx].get('step')} "
                          f"(第 {revision_counts[step_key]} 次)")
                    continue

            current_step_idx += 1

        # 汇总结果
        return self._aggregate_pipeline_results(
            wg_name=wg_name,
            pipeline=sorted_pipeline,
            step_results=step_results,
            execution_log=execution_log,
            user_message=user_message,
        )

    # ── 动态规则 ──

    def _apply_coach_first(self, pipeline: list[dict], wg_id: str) -> list[dict]:
        """
        动态规则: coach_first — 开发类工作组确保 coach 在最前面

        如果 pipeline 第一个步骤不是 coach，且 members 包含 coach，则前置一个 coach 步骤。
        """
        if not pipeline:
            return pipeline

        first_role = pipeline[0].get("role", "")

        # 检查是否属于 dev 组
        dev_wg_ids = {"dev_full", "dev_design_only", "dev_code_review", "dev_tech_debt"}
        if wg_id not in dev_wg_ids:
            return pipeline
        if first_role == "coach":
            return pipeline  # coach 已经在最前面

        # 检查 members 中是否有 coach
        # 从 pipeline 中收集所有 role
        all_roles = {s.get("role") for s in pipeline}
        if "coach" not in all_roles:
            return pipeline

        # 前置 coach 步骤
        coach_step = {
            "step": 0,
            "role": "coach",
            "action": "Phase 0 需求发现：分析用户需求，拆解任务，产出执行计划",
            "input_from": "user",
            "output_to": "step_1",
            "parallel_with": [],
            "condition": "",
        }
        # 重新编号后续步骤
        result = [coach_step]
        for i, step in enumerate(pipeline):
            renumbered = dict(step)
            renumbered["step"] = i + 1
            # 更新 input_from 引用
            old_input = step.get("input_from", "")
            if old_input.startswith("step"):
                old_num = self._extract_step_num(old_input)
                if old_num is not None:
                    renumbered["input_from"] = f"step_{old_num + 1}"
            result.append(renumbered)

        print(f"[Master] 动态规则 coach_first: 已前置 coach 步骤")
        return result

    def _apply_cleanup_hook(self, pipeline: list[dict], wg_id: str) -> list[dict]:
        """
        动态规则: cleanup_hook — 开发类工作组结束后自动追加 cleaner

        如果 pipeline 最后一个步骤不是 cleaner，且 members 包含 cleaner，则追加。
        """
        if not pipeline:
            return pipeline

        dev_wg_ids = {"dev_full", "dev_code_review", "dev_tech_debt"}
        if wg_id not in dev_wg_ids:
            return pipeline

        last_role = pipeline[-1].get("role", "")
        if last_role == "cleaner":
            return pipeline  # cleaner 已经在最后

        # 检查 cleaner 是否在 members 中
        all_roles = {s.get("role") for s in pipeline}
        if "cleaner" not in all_roles:
            return pipeline

        # 追加 cleaner 步骤
        last_step_num = max(s.get("step", 0) for s in pipeline)
        cleaner_step = {
            "step": last_step_num + 1,
            "role": "cleaner",
            "action": "清理临时文件、构建缓存、中间产物",
            "input_from": f"step_{last_step_num}",
            "output_to": "user",
            "parallel_with": [],
            "condition": "",
        }

        print(f"[Master] 动态规则 cleanup_hook: 已追加 cleaner 步骤")
        return pipeline + [cleaner_step]

    def _apply_experience_eval_hook(self, workgroup: dict, wg_id: str) -> list[dict]:
        """
        动态规则: experience_eval_hook — 开发类工作组收尾后追加经验评估员（方案 C-4）。
        仅当 workgroup 的 members 显式列入 "experience_evaluator" 时才生效（按工作组开关，零侵入）。
        """
        pipeline = workgroup.get("pipeline", [])
        if not pipeline:
            return pipeline

        dev_wg_ids = {"dev_full", "dev_code_review", "dev_tech_debt"}
        if wg_id not in dev_wg_ids:
            return pipeline

        members = set(workgroup.get("members", []))
        if "experience_evaluator" not in members:
            return pipeline

        if pipeline[-1].get("role") == "experience_evaluator":
            return pipeline  # 已存在

        last_step_num = max(s.get("step", 0) for s in pipeline)
        eval_step = {
            "step": last_step_num + 1,
            "role": "experience_evaluator",
            "action": "任务收尾后评估被注入经验的效用，审计知识新鲜度，淘汰失效记忆",
            "input_from": f"step_{last_step_num}",
            "output_to": "user",
            "parallel_with": [],
            "condition": "",
        }
        print(f"[Master] 动态规则 experience_eval_hook: 已追加 experience_evaluator 步骤")
        return pipeline + [eval_step]

    @staticmethod
    def _extract_step_num(step_str: str) -> Optional[int]:
        """从 'step_3' 或 'step3' 中提取数字"""
        if not step_str.startswith("step"):
            return None
        try:
            return int(step_str.replace("step", "").replace("_", ""))
        except ValueError:
            return None

    def _build_pipeline_task(
        self,
        user_message: str,
        step_def: dict,
        previous_results: dict[str, str],
        wg_name: str,
    ) -> str:
        """
        为流水线步骤构建任务包 (防火墙: 最小信息原则)

        :param user_message: 用户原始消息
        :param step_def: 步骤定义
        :param previous_results: 前序步骤的结果 (key: "step_{num}")
        :param wg_name: 工作组名称
        :return: 裁剪后的任务描述
        """
        role_id = step_def.get("role", "")
        action = step_def.get("action", "")
        input_from = step_def.get("input_from", "user")

        parts = [f"工作组: {wg_name}"]
        parts.append(f"你的角色: {role_id}")
        parts.append(f"当前步骤: {action}")

        # 用户原始需求
        if input_from == "user":
            parts.append(f"\n用户需求:\n{user_message}")

        # 注入前序步骤结果 (兼容 step1 / step_1 两种格式)
        if input_from.startswith("step"):
            normalized_key = self._normalize_step_key(input_from)
            prev_result = previous_results.get(normalized_key, "")
            if prev_result:
                parts.append(f"\n前序步骤产出:\n{prev_result}")
            else:
                # 尝试其他可能的 key 格式
                for key, result in previous_results.items():
                    if key.endswith(normalized_key[-2:]) or normalized_key.endswith(key[-2:]):
                        parts.append(f"\n前序步骤产出:\n{result}")
                        break

        # 注入其他相关结果 (参考上下文)
        for key, result in previous_results.items():
            if self._normalize_step_key(input_from) != key and result:
                parts.append(f"\n{key} 产出 (参考):\n{result[:300]}")

        return "\n\n".join(parts)

    @staticmethod
    def _normalize_step_key(raw: str) -> str:
        """
        将 step key 标准化为 "step_{num}" 格式

        支持: "step1", "step_1", "step_2", "step2" → "step_1", "step_2"
        """
        if not raw.startswith("step"):
            return raw
        # 去掉 "step" 前缀和所有下划线，提取数字
        num_part = raw.replace("step", "").replace("_", "").strip()
        return f"step_{num_part}"

    def _should_revise(
        self,
        condition: str,
        step_results: dict[str, str],
        revision_counts: dict[str, int],
        max_revisions: int,
    ) -> bool:
        """
        判断是否需要返工

        :param condition: 步骤的 condition 描述 (如 "inspection_failed", "test_not_passed")
        :param step_results: 所有步骤结果
        :param revision_counts: 返工计数
        :param max_revisions: 最大返工次数
        :return: 是否需要返工
        """
        if not condition:
            return False

        # 从最近的步骤结果中检查失败标记
        failure_markers = [
            "不通过", "失败", "需要返工", "打回", "rejected",
            "[⚠", "未通过", "有错误", "存在问题",
        ]
        for key, result in step_results.items():
            if any(marker in result for marker in failure_markers):
                # 检查是否已达返工上限
                for rk, count in revision_counts.items():
                    if count >= max_revisions:
                        return False
                return True

        return False

    def _find_prev_step_by_output(
        self,
        pipeline: list[dict],
        output_to: str,
        current_step: int,
    ) -> Optional[int]:
        """
        根据 output_to 找到前序步骤的索引

        :param pipeline: 排序后的流水线
        :param output_to: 当前步骤的输出目标
        :param current_step: 当前步骤编号
        :return: 前序步骤的索引，或 None
        """
        # output_to 格式如 "step_3" 或 "step3|user"
        targets = output_to.replace("|", " ").split()
        for target in targets:
            if target.startswith("step"):
                try:
                    # 提取步骤编号
                    num_str = target.replace("step", "").replace("_", "")
                    target_num = int(num_str)
                    for idx, step in enumerate(pipeline):
                        if step.get("step") == target_num:
                            return idx
                except (ValueError, IndexError):
                    pass
        return None

    def _aggregate_pipeline_results(
        self,
        wg_name: str,
        pipeline: list[dict],
        step_results: dict[str, str],
        execution_log: list[str],
        user_message: str = "",
    ) -> str:
        """
        汇总流水线执行结果，生成结构化报告

        :param wg_name: 工作组名称
        :param pipeline: 流水线定义
        :param step_results: 各步骤执行结果
        :param execution_log: 执行日志
        :param user_message: 用户原始消息
        :return: 格式化的汇总文本
        """
        parts = []

        # 执行摘要
        parts.append(f"## 工作组「{wg_name}」执行完成\n")

        # 执行日志
        parts.append("### 执行日志")
        for log_line in execution_log:
            parts.append(f"- {log_line}")
        parts.append("")

        # 各步骤产出 (按步骤顺序)
        parts.append("### 步骤产出")
        for step_def in sorted(pipeline, key=lambda s: s.get("step", 0)):
            step_num = step_def.get("step", 0)
            role_id = step_def.get("role", "")
            step_key = f"step_{step_num}"
            result = step_results.get(step_key, "")

            if result:
                role_name = self._role_pool.get(role_id, {}).get("name", role_id)
                parts.append(f"#### 步骤 {step_num}: {role_name}")
                parts.append(result)
                parts.append("")

        # 最终产出 (最后一个步骤的结果)
        if pipeline:
            last_step = pipeline[-1]
            last_key = f"step_{last_step.get('step', 0)}"
            last_result = step_results.get(last_key, "")
            if last_result and not last_result.startswith("[执行失败]"):
                parts.append("---")
                parts.append(f"### 最终交付")
                parts.append(last_result)

        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    # 任务分发 (含超时/重试/降级/并行)
    # ------------------------------------------------------------------ #

    async def _dispatch_to_roles(
        self, user_message: str, matched_roles: list[dict]
    ) -> dict[str, str]:
        """
        向角色分发任务 (支持跨 GPU 并行、超时、重试、降级)

        策略:
            1. 按 GPU 亲和性分组
            2. 不同 GPU 上的角色并行执行 (asyncio.gather)
            3. 同 GPU 上的角色串行执行
            4. 单角色超时 120 秒，失败自动重试 1 次
            5. 重试仍失败 → 降级处理

        :param user_message: 用户原始消息
        :param matched_roles: 匹配的角色定义列表
        :return: {role_id: result}
        """
        error_config = self._dispatcher_config.get("error_handling", {})
        timeout = error_config.get("role_timeout", {}).get("timeout_seconds", 120)
        max_retries = 1

        # 按 GPU 亲和性分组
        gpu_groups: dict[str, list[dict]] = {}
        for role_def in matched_roles:
            role_id = role_def["id"]
            pool_def = self._role_pool.get(role_id, {})
            gpu = pool_def.get("gpu_affinity", "gpu0")
            gpu_groups.setdefault(gpu, []).append(role_def)

        results: dict[str, str] = {}

        # 跨 GPU 并行执行
        gpu_tasks = []
        for gpu, roles_in_group in gpu_groups.items():
            gpu_tasks.append(self._execute_gpu_group(
                roles_in_group, user_message, timeout, max_retries
            ))

        gpu_results = await asyncio.gather(*gpu_tasks, return_exceptions=True)

        # 合并结果
        for group_result in gpu_results:
            if isinstance(group_result, dict):
                results.update(group_result)
            else:
                print(f"[Master] GPU 组执行异常: {group_result}")

        return results

    async def _execute_gpu_group(
        self,
        roles: list[dict],
        user_message: str,
        timeout: int,
        max_retries: int,
    ) -> dict[str, str]:
        """
        在同一 GPU 上串行执行一组角色 (带超时/重试/降级)

        :param roles: 该 GPU 上的角色列表
        :param user_message: 用户原始消息
        :param timeout: 单角色超时 (秒)
        :param max_retries: 最大重试次数
        :return: {role_id: result}
        """
        results: dict[str, str] = {}

        for role_def in roles:
            role_id = role_def["id"]
            role = self._loaded_roles.get(role_id)

            if not role:
                results[role_id] = f"[未注册] 角色 {role_id} 未加载"
                continue

            task_id = generate_id("task")
            task = self._build_task_packet(user_message, role_def)

            # 黑板下发
            blackboard.publish(
                from_role="master",
                to_role=role_id,
                msg_type="task_dispatch",
                content=f"[{task_id}] {task}",
            )

            # 执行 (含重试)
            result = await self._execute_with_retry(
                role=role,
                task=task,
                task_id=task_id,
                extra_context=user_message,
                timeout=timeout,
                max_retries=max_retries,
            )
            results[role_id] = result

        return results

    async def _execute_with_retry(
        self,
        role: RoleBase,
        task: str,
        task_id: str,
        extra_context: str,
        timeout: int,
        max_retries: int,
    ) -> str:
        """
        带超时和重试的角色执行

        :param role: 角色实例
        :param task: 任务描述
        :param task_id: 任务 ID
        :param extra_context: 附加上下文
        :param timeout: 超时秒数
        :param max_retries: 最大重试次数
        :return: 执行结果
        """
        last_error = ""

        for attempt in range(max_retries + 1):
            try:
                result = await asyncio.wait_for(
                    role.execute(task, task_id, extra_context=extra_context),
                    timeout=timeout,
                )
                return result

            except asyncio.TimeoutError:
                last_error = f"超时 ({timeout}s)"
                print(f"[Master] 角色 {role.id} 超时 (尝试 {attempt + 1}/{max_retries + 1})")

            except Exception as e:
                last_error = str(e)
                print(f"[Master] 角色 {role.id} 执行失败 (尝试 {attempt + 1}/{max_retries + 1}): {e}")

        # 所有重试失败 → 降级处理
        degraded = self._degradation_handler(role.id, task, last_error)
        return degraded

    def _degradation_handler(self, role_id: str, task: str, error: str) -> str:
        """
        降级处理: 角色执行失败后的回退策略

        :param role_id: 失败的角色
        :param task: 原始任务
        :param error: 错误信息
        :return: 降级结果
        """
        # 降级策略: 返回明确的失败信息，供用户决策
        role_name = self._role_pool.get(role_id, {}).get("name", role_id)
        return (
            f"[⚠ 角色「{role_name}」执行失败，已重试耗尽]\n"
            f"错误: {error}\n\n"
            f"建议: 请检查 LLM 服务是否正常运行，或简化任务重试。"
        )

    def _build_task_packet(self, user_message: str, role_def: dict) -> str:
        """
        构建任务包 (防火墙: 最小信息原则)

        :param user_message: 用户原始消息
        :param role_def: 角色定义
        :return: 裁剪后的任务描述
        """
        role_name = role_def["name"]
        capabilities = role_def.get("capabilities", [])

        # 只传递该角色需要的信息
        return f"用户请求: {user_message}\n\n你的角色: {role_name}\n需要你执行的能力: {', '.join(capabilities[:3])}\n\n请完成你的部分并返回结果。"

    # ------------------------------------------------------------------ #
    # 结果汇总
    # ------------------------------------------------------------------ #

    def _aggregate_results(self, user_message: str, results: dict[str, str]) -> str:
        """
        汇总多个角色的结果

        :param user_message: 用户原始消息
        :param results: {role_id: result}
        :return: 汇总后的文本
        """
        if not results:
            # 区分两种空结果：没有匹配到角色 vs 角色执行全部失败
            # 此方法调用的上游已确保 matched_roles 非空，故此处空 results = 执行失败而非匹配失败
            return (
                "抱歉，匹配到的角色未能成功执行任务。这通常是因为：\n"
                "1. LLM 推理服务暂时不可用或超时\n"
                "2. 任务对 14B 模型过于复杂\n"
                "建议：简化请求或稍后重试。您也可以直接描述具体需求，我会尽力直接处理。"
            )

        if len(results) == 1:
            return list(results.values())[0]

        # 多角色结果汇总
        parts = []
        for role_id, result in results.items():
            role_name = self._role_pool.get(role_id, {}).get("name", role_id)
            parts.append(f"### {role_name}\n{result}")

        return "\n\n".join(parts)

    # ------------------------------------------------------------------ #
    # 防火墙路由 (黑板)
    # ------------------------------------------------------------------ #

    def route_message(
        self,
        from_role: str,
        to_role: str,
        content: str,
        msg_type: str = "task_done",
    ) -> Optional[BlackboardEntry]:
        """
        防火墙路由: 脱敏后转发角色间消息

        这是主控的专属方法。其他角色不直接调用。
        主控收到消息后，裁剪敏感信息，然后转发给目标角色。

        :param from_role: 原始发送角色
        :param to_role: 目标接收角色
        :param content: 原始内容
        :param msg_type: 消息类型
        :return: 转发的 BlackboardEntry
        """
        return blackboard.route(
            from_role=from_role,
            to_role=to_role,
            content=content,
            msg_type=msg_type,
            desensitize=True,
            strip_author=True,
        )

    def broadcast_status(self, content: str):
        """向所有角色广播状态更新"""
        return blackboard.route_broadcast(content, msg_type="status")

    # ------------------------------------------------------------------ #
    # 进度报告
    # ------------------------------------------------------------------ #

    def report_progress(self, message: str, current: int = 0, total: int = 0):
        """
        向用户报告进度

        :param message: 进度描述
        :param current: 当前步骤
        :param total: 总步骤
        """
        if total > 0:
            return f"[{current}/{total}] {message}"
        return message

    # ------------------------------------------------------------------ #
    # 工作组管理 (公开 API)
    # ------------------------------------------------------------------ #

    def get_workgroup(self, wg_id: str) -> Optional[dict]:
        """获取工作组配置 (供外部调用)"""
        return self._workgroups.get(wg_id)

    def list_workgroups(self) -> list[dict]:
        """列出所有工作组摘要 (供外部调用)"""
        return [
            {
                "id": wg_id,
                "name": wg.get("name", wg_id),
                "description": wg.get("description", ""),
                "trigger_keywords": wg.get("trigger_keywords", []),
                "members": wg.get("members", []),
                "pipeline_steps": len(wg.get("pipeline", [])),
            }
            for wg_id, wg in self._workgroups.items()
        ]

    async def execute_workgroup(self, wg_id: str, user_message: str) -> dict:
        """
        公开 API: 手动触发工作组执行 (供 API 路由等外部调用)

        :param wg_id: 工作组 ID
        :param user_message: 用户消息
        :return: {"result": str, "type": "workgroup", "roles_used": [...]}
        """
        wg = self._workgroups.get(wg_id)
        if not wg:
            raise ValueError(f"工作组不存在: {wg_id}")

        result = await self._execute_pipeline(wg, user_message)
        return {
            "result": result,
            "type": "workgroup",
            "workgroup": wg_id,
            "roles_used": wg.get("members", []),
        }

    # ------------------------------------------------------------------ #
    # 项目状态检测 (方案书 3.7 节)
    # ------------------------------------------------------------------ #

    def detect_projects(self) -> list[dict]:
        """
        会话启动时检测所有活跃项目

        在用户首次连接 Agent 时调用，返回所有有 PROJECT_STATUS.md 的项目摘要。
        前端可据此询问用户"检测到项目 X，是否继续？"

        :return: 项目摘要列表
        """
        return project_status.list_projects()

    def get_project_status(self, project_name: str) -> Optional[dict]:
        """
        获取指定项目的完整状态快照

        :param project_name: 项目名称
        :return: 状态字典，或 None
        """
        status = project_status.get_status(project_name)
        if not status:
            return None

        return {
            "project_name": status.project_name,
            "current_phase": status.current_phase,
            "last_updated": status.last_updated,
            "active_agent": status.active_agent,
            "completed": [
                {"name": m.name, "note": m.note}
                for m in status.completed
            ],
            "in_progress": [
                {"name": m.name, "note": m.note}
                for m in status.in_progress
            ],
            "pending": [
                {"name": m.name, "note": m.note}
                for m in status.pending
            ],
            "tech_debt": status.tech_debt,
            "blockers": status.blockers,
            "summary": project_status.get_summary(project_name),
        }

    def inject_project_context(self, user_message: str) -> str:
        """
        在调度前注入项目上下文

        检测 user_message 中是否包含开发/项目相关关键词，
        若有活跃项目，将状态摘要注入到消息中，帮助角色理解当前进度。

        :param user_message: 用户原始消息
        :return: 增强后的消息 (含项目状态上下文)
        """
        # 开发相关关键词
        dev_keywords = [
            "开发", "代码", "写", "实现", "修复", "改", "完成",
            "继续", "接着", "下一个", "模块", "组件", "页面",
            "构建", "部署", "测试", "巡检", "审查",
        ]
        if not any(kw in user_message for kw in dev_keywords):
            return user_message

        # 查找活跃项目
        projects = self.detect_projects()
        if not projects:
            return user_message

        # 注入最近更新的项目状态
        latest = projects[0]  # 按文件系统顺序，通常是最近修改的
        context = f"[项目上下文]\n{latest['summary']}\n\n用户消息:\n{user_message}"
        return context

    # ------------------------------------------------------------------ #
    # 状态查询
    # ------------------------------------------------------------------ #

    def get_status(self) -> dict:
        """获取主控状态 (含调度器、工作组、错误处理信息)"""
        status = super().get_status()
        error_config = self._dispatcher_config.get("error_handling", {})
        status.update({
            "registered_roles": len(self._loaded_roles),
            "available_roles": list(self._loaded_roles.keys()),
            "pool_size": len(self._role_pool),
            "dispatcher_loaded": bool(self._dispatcher_config),
            "workgroups_loaded": len(self._workgroups),
            "workgroup_ids": list(self._workgroups.keys()),
            "error_handling": {
                "timeout_seconds": error_config.get("role_timeout", {}).get("timeout_seconds", 120),
                "max_retries": 1,
                "degradation_enabled": True,
            },
            "execution_strategy": "gpu_grouped_parallel",
            "dynamic_rules": ["coach_first", "cleanup_hook"],
        })
        return status