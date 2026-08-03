"""
Orchestrator — 编排层秘书机制

架构定位:
    Orchestrator 是 L2 编排层的后勤组件。它不是第 17 个角色，而是
    在主控（MasterRole）和角色之间的"上下文管理员"。

    核心职责:
        1. 维护 runtime_state — 阶段、模块、文档指针（不占 LLM 上下文）
        2. 增量摘要 — 每 5-10 轮生成对话摘要，注入主 LLM 上下文
        3. 纠错触发 — 失败计数 + 用户反对计数 → 注入前提质疑提示
        4. 文档检索 — 主 LLM 要翻旧文档时，精准取片段注入
        5. 经验管理 — 记录成功操作的模式，跨会话复用，避免重复试错

设计原则:
    - runtime_state 存在 orchestrator 内存，不占 LLM 上下文
    - 秘书只负责"读状态 → 分析 → 生成片段"，片段注入主 LLM
    - 主 LLM 不需要知道有"外部记忆"——它请求文档，秘书默默塞入
    - 每 5-10 轮激活一次，避免自己的上下文爆炸
    - 经验是"成功的方法论"，不是"又一轮摘要"——记录的是约束条件 + 成功路径

与现有系统的关系:
    - 不是新角色，不需要 GPU 分配
    - 增量摘要调用的 LLM 复用现有 GPU 实例
    - 与记忆系统互补：秘书是"取的时候做"，记忆系统是"存的时候做"
    - 经验管理填补了"跨会话操作记忆"的空白

参考:
    - 搭叩 ChatDashboard: 关键信息保留率 90%, Token 节省 80%+
    - SimpleMem (ICML 2026): 语义压缩 + 记忆融合 + 自适应检索
    - PROPOSAL.md §3.9 秘书机制设计
"""
import asyncio
import json
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from core.memory.store import generate_id, now_iso


# ===== 否定关键词 =====
# 用户消息中匹配这些模式时，user_negation_count +1
NEGATION_PATTERNS = [
    r"不对",
    r"不是",
    r"你错了",
    r"搞错了",
    r"错[了啦]",
    r"你(在|又|还)[是在]?[乱胡乱][说讲弄搞]",
    r"神经病",
    r"傻[逼屌叉]",
    r"我[真就]?服了",
    r"不行",
    r"不[要对]",
    r"错了",
    r"你又",
    r"还在",
    r"重来",
    r"根本不对",
    r"完全错",
    r"你在干什么",
    r"听不懂",
    r"别[再在]",
    r"不要[再在]",
]


# ===== 失败检测关键词 =====
# 角色执行结果中匹配这些模式时，consecutive_failures +1
FAILURE_PATTERNS = [
    r"\[⚠\s*执行失败\]",
    r"\[⚠\s*.*失败\]",
    r"执行失败",
    r"error",
    r"Error",
    r"超时",
    r"timeout",
    r"重试耗尽",
    r"降级处理",
    r"未注册",
    r"未找到",
    r"不存在",
]


# ===== 摘要触发阈值 =====
SUMMARY_INTERVAL = 5          # 每 5 轮生成增量摘要
FAILURE_THRESHOLD = 3         # 连续失败 3 次触发前提质疑
NEGATION_THRESHOLD = 3        # 连续否定 3 次触发反向自检
MAX_CONTEXT_TOKENS = 2000     # 单次检索注入的最大 token 数


@dataclass
class RuntimeState:
    """
    秘书维护的运行时状态

    存在 orchestrator 内存中，不占 LLM 上下文。
    只记录"指针"和"状态"，不存完整内容。
    """

    # ── 项目状态 ──
    active_project: str = ""          # 当前活跃项目名
    current_phase: str = ""           # 当前阶段 (Phase 0/1/2/3)
    completed_modules: list[str] = field(default_factory=list)
    in_progress_module: str = ""      # 进行中模块名

    # ── 文档指针 ──
    project_plan_path: str = ""       # PROJECT_PLAN.md 绝对路径
    status_path: str = ""             # PROJECT_STATUS.md 绝对路径
    tech_debt_path: str = ""          # tech_debt.md 绝对路径

    # ── 对话统计 ──
    total_turns: int = 0              # 总对话轮数
    turns_since_last_summary: int = 0 # 距上次摘要的轮数
    last_summary_at: str = ""         # 上次摘要时间 (ISO)

    # ── 纠错状态 ──
    consecutive_failures: int = 0     # 连续失败次数
    user_negation_count: int = 0      # 连续用户否定次数
    last_failure_scope: str = ""      # 上次失败的任务范围 (用于判断是否同 scope)
    last_user_message: str = ""       # 上一条用户消息
    active_role_id: str = ""          # 当前活跃角色

    # ── 增量摘要 ──
    incremental_summaries: list[str] = field(default_factory=list)
    recent_turns_buffer: list[dict] = field(default_factory=list)
    # 格式: [{"role": "user"|"assistant", "content": "...", "turn": N}, ...]

    def to_dict(self) -> dict:
        return asdict(self)

    def reset_failures(self):
        """重置失败计数 (任务成功完成后调用)"""
        self.consecutive_failures = 0
        self.last_failure_scope = ""

    def reset_negations(self):
        """重置否定计数 (用户表示满意后调用)"""
        self.user_negation_count = 0


# ===== 经验管理 =====

@dataclass
class ExperienceRecord:
    """
    经验记录 — 一次成功操作的模式记忆

    与增量摘要的区别:
        - 摘要记录"对话中发生了什么"
        - 经验记录"这件事怎么做才能成功"
        - 摘要随会话结束而失效，经验跨会话持久化
    """
    task_type: str              # 任务类型标识 (e.g., "git_push", "deploy", "debug")
    keywords: List[str]         # 触发关键词，用于匹配用户请求
    context: str                # 当时的情境描述
    constraints: List[str]      # 已知的环境约束条件
    successful_approach: List[str]  # 成功的步骤（按顺序）
    failed_attempts: List[str]  # 失败过的尝试及原因
    timestamp: str = ""         # 记录时间 (ISO)
    success_count: int = 1      # 该方法成功的次数（自动递增）

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ExperienceRecord":
        return cls(**{
            k: v for k, v in data.items()
            if k in cls.__dataclass_fields__
        })


class ExperienceManager:
    """
    经验管理器 — 秘书的"长期记忆"

    负责:
        1. 记录成功的操作模式
        2. 根据用户请求匹配相关经验
        3. 将经验注入 LLM 上下文（在任务开始前）

    存储位置: data/experiences/{task_type}.json
    """

    def __init__(self, storage_dir: str = ""):
        self._storage_dir = storage_dir or "data/experiences"
        self._experiences: List[ExperienceRecord] = []
        self._load_all()

    # ------------------------------------------------------------------ #
    # 持久化
    # ------------------------------------------------------------------ #

    def _get_experience_dir(self) -> Path:
        return Path(self._storage_dir)

    def _load_all(self):
        """加载所有经验文件"""
        self._experiences = []
        exp_dir = self._get_experience_dir()
        if not exp_dir.exists():
            return
        for f in exp_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for item in data:
                        self._experiences.append(ExperienceRecord.from_dict(item))
                elif isinstance(data, dict):
                    self._experiences.append(ExperienceRecord.from_dict(data))
            except Exception:
                pass

    def _save(self, record: ExperienceRecord):
        """保存单条经验"""
        exp_dir = self._get_experience_dir()
        exp_dir.mkdir(parents=True, exist_ok=True)
        filepath = exp_dir / f"{record.task_type}.json"

        # 加载已有记录
        existing: List[dict] = []
        if filepath.exists():
            try:
                existing = json.loads(filepath.read_text(encoding="utf-8"))
                if isinstance(existing, dict):
                    existing = [existing]
            except Exception:
                existing = []

        # 检查是否已存在相同经验（按 successful_approach 去重）
        new_approach = "\n".join(record.successful_approach)
        for ex in existing:
            old_approach = "\n".join(ex.get("successful_approach", []))
            if new_approach == old_approach:
                # 已存在，增加计数
                ex["success_count"] = ex.get("success_count", 1) + 1
                ex["timestamp"] = record.timestamp
                filepath.write_text(
                    json.dumps(existing, ensure_ascii=False, indent=2),
                    encoding="utf-8"
                )
                return

        existing.append(record.to_dict())
        filepath.write_text(
            json.dumps(existing, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    # ------------------------------------------------------------------ #
    # 核心操作
    # ------------------------------------------------------------------ #

    def record(
        self,
        task_type: str,
        keywords: List[str],
        context: str,
        constraints: List[str],
        successful_approach: List[str],
        failed_attempts: List[str],
    ):
        """
        记录一次成功的操作经验

        :param task_type: 任务类型标识
        :param keywords: 触发关键词
        :param context: 当时的情境
        :param constraints: 环境约束
        :param successful_approach: 成功步骤
        :param failed_attempts: 失败的尝试
        """
        record = ExperienceRecord(
            task_type=task_type,
            keywords=keywords,
            context=context,
            constraints=constraints,
            successful_approach=successful_approach,
            failed_attempts=failed_attempts,
            timestamp=datetime.now(timezone.utc).isoformat(),
            success_count=1,
        )
        self._save(record)
        self._experiences.append(record)
        print(
            f"[Secretary] 经验已记录: {task_type} "
            f"(关键词: {', '.join(keywords[:3])})"
        )

    def find(self, user_message: str) -> List[ExperienceRecord]:
        """
        根据用户消息匹配相关经验

        匹配策略: 关键词匹配（用户消息中包含任一关键词即匹配）
        按 success_count 降序排列（最可靠的经验排前面）

        :param user_message: 用户当前消息
        :return: 匹配的经验列表（按可靠度排序）
        """
        if not user_message:
            return []

        msg_lower = user_message.lower()
        matched = []

        for exp in self._experiences:
            for kw in exp.keywords:
                if kw.lower() in msg_lower:
                    matched.append(exp)
                    break

        # 按成功次数降序
        matched.sort(key=lambda e: e.success_count, reverse=True)
        return matched

    def get_injection(self, user_message: str) -> str:
        """
        获取应注入的经验上下文

        在 LLM 开始执行任务前调用，将相关经验注入上下文。

        :param user_message: 用户当前消息
        :return: 经验注入文本（Markdown 格式），无匹配时返回空字符串
        """
        experiences = self.find(user_message)
        if not experiences:
            return ""

        parts = []
        parts.append("\n\n---\n## 秘书经验提示 (来自过往成功操作)\n")

        for i, exp in enumerate(experiences[:3]):  # 最多注入 3 条
            parts.append(f"### 经验 {i + 1}: {exp.task_type}")
            parts.append(f"**情境**: {exp.context}")
            parts.append(f"**已验证 {exp.success_count} 次**")

            if exp.constraints:
                parts.append(f"\n**⚠️ 环境约束 (必须注意)**:")
                for c in exp.constraints:
                    parts.append(f"  - {c}")

            if exp.failed_attempts:
                parts.append(f"\n**❌ 已知失败方案 (不要重复尝试)**:")
                for f in exp.failed_attempts:
                    parts.append(f"  - {f}")

            if exp.successful_approach:
                parts.append(f"\n**✅ 成功步骤 (请严格遵循)**:")
                for step in exp.successful_approach:
                    parts.append(f"  {step}")

            parts.append("")  # 空行分隔

        # 加上重要提示
        parts.append(
            "> ⚠️ **秘书提示**: 以上经验来自过往成功操作，请优先参考成功步骤，"
            "避免重复已知的失败方案。如果环境发生变化导致经验失效，"
            "请在成功完成后告诉我，我会更新经验。"
        )

        return "\n".join(parts)

    def get_all_types(self) -> List[str]:
        """获取所有已记录的经验类型"""
        return list(set(e.task_type for e in self._experiences))

    def get_status(self) -> dict:
        """获取经验管理器状态"""
        return {
            "total_experiences": len(self._experiences),
            "experience_types": self.get_all_types(),
            "storage_dir": self._storage_dir,
        }


class Secretary:
    """
    秘书 — 上下文管理员 + 经验管理者

    不是角色，是 orchestrator 的方法集合。
    负责:
        1. 运行时状态追踪
        2. 增量摘要生成
        3. 纠错触发判断
        4. 文档检索注入
        5. 经验管理 — 记录成功操作，跨会话复用

    使用方式:
        secretary = Secretary()
        secretary.init(session_id)

        # 每轮对话后
        secretary.record_turn(user_message, role_response, role_id)

        # 任务开始前 — 获取经验注入
        experience_hint = secretary.get_experience_injection(user_message)

        # 任务成功后 — 记录经验
        secretary.record_experience(...)

        # 检查是否需要纠错
        correction = secretary.check_correction()
        if correction:
            # 将 correction 注入下一轮 LLM 上下文

        # 检查是否需要摘要
        if secretary.should_summarize():
            summary = await secretary.generate_summary()
            # 将 summary 注入下一轮 LLM 上下文
    """

    # ------------------------------------------------------------------ #
    # 初始化
    # ------------------------------------------------------------------ #

    def __init__(self):
        self._state = RuntimeState()
        self._session_id: str = ""
        self._llm_call: Optional[callable] = None  # 异步 LLM 调用函数
        self._experience_manager: Optional[ExperienceManager] = None

    def init(self, session_id: str = "", llm_call: Optional[callable] = None,
             experience_dir: str = ""):
        """
        初始化秘书

        :param session_id: 会话 ID
        :param llm_call: 异步 LLM 调用函数 async fn(messages, **kwargs) -> dict
        :param experience_dir: 经验存储目录
        """
        self._session_id = session_id or generate_id("sess")
        self._llm_call = llm_call
        self._state = RuntimeState()
        self._experience_manager = ExperienceManager(
            experience_dir or "data/experiences"
        )
        return self

    # ------------------------------------------------------------------ #
    # 状态查询
    # ------------------------------------------------------------------ #

    @property
    def state(self) -> RuntimeState:
        return self._state

    def get_status(self) -> dict:
        """获取秘书状态摘要"""
        return {
            "active_project": self._state.active_project,
            "current_phase": self._state.current_phase,
            "total_turns": self._state.total_turns,
            "turns_since_summary": self._state.turns_since_last_summary,
            "consecutive_failures": self._state.consecutive_failures,
            "user_negation_count": self._state.user_negation_count,
            "summary_count": len(self._state.incremental_summaries),
            "last_summary_at": self._state.last_summary_at,
        }

    # ------------------------------------------------------------------ #
    # 项目状态设置
    # ------------------------------------------------------------------ #

    def set_project(self, project_name: str, phase: str = "",
                    plan_path: str = "", status_path: str = "",
                    debt_path: str = ""):
        """设置当前活跃项目"""
        self._state.active_project = project_name
        self._state.current_phase = phase
        self._state.project_plan_path = plan_path
        self._state.status_path = status_path
        self._state.tech_debt_path = debt_path

    def update_phase(self, phase: str):
        """更新当前阶段"""
        self._state.current_phase = phase

    def add_completed_module(self, module_name: str):
        """标记模块完成"""
        if module_name not in self._state.completed_modules:
            self._state.completed_modules.append(module_name)
        self._state.in_progress_module = ""

    def set_in_progress(self, module_name: str):
        """设置进行中模块"""
        self._state.in_progress_module = module_name

    # ------------------------------------------------------------------ #
    # 对话记录 (每轮调用)
    # ------------------------------------------------------------------ #

    def record_turn(
        self,
        user_message: str,
        role_response: str,
        role_id: str = "",
    ):
        """
        每轮对话后调用，更新运行时状态

        :param user_message: 用户消息
        :param role_response: 角色响应
        :param role_id: 当前活跃角色
        """
        self._state.total_turns += 1
        self._state.turns_since_last_summary += 1
        self._state.active_role_id = role_id

        # 记录到缓冲区
        self._state.recent_turns_buffer.append({
            "role": "user",
            "content": user_message[:500],
            "turn": self._state.total_turns,
        })
        self._state.recent_turns_buffer.append({
            "role": "assistant",
            "content": role_response[:500],
            "turn": self._state.total_turns,
        })

        # 缓冲区只保留最近 20 轮
        if len(self._state.recent_turns_buffer) > 40:
            self._state.recent_turns_buffer = \
                self._state.recent_turns_buffer[-40:]

        # 检测用户否定
        self._detect_negation(user_message)

        # 检测执行失败
        self._detect_failure(role_response, role_id)

        # 保存上一条用户消息
        self._state.last_user_message = user_message

    def _detect_negation(self, user_message: str):
        """检测用户消息中是否包含否定"""
        for pattern in NEGATION_PATTERNS:
            if re.search(pattern, user_message):
                self._state.user_negation_count += 1
                return
        # 没有否定 → 重置计数器 (用户表示了满意或中性)
        self._state.reset_negations()

    def _detect_failure(self, role_response: str, role_id: str):
        """检测角色执行结果是否失败"""
        current_scope = role_id or "unknown"

        for pattern in FAILURE_PATTERNS:
            if re.search(pattern, role_response):
                # 检查是否同 scope
                if current_scope == self._state.last_failure_scope:
                    self._state.consecutive_failures += 1
                else:
                    self._state.consecutive_failures = 1
                    self._state.last_failure_scope = current_scope
                return

        # 没有失败 → 重置
        self._state.reset_failures()

    # ------------------------------------------------------------------ #
    # 增量摘要
    # ------------------------------------------------------------------ #

    def should_summarize(self) -> bool:
        """判断是否需要生成增量摘要"""
        return self._state.turns_since_last_summary >= SUMMARY_INTERVAL

    async def generate_summary(self) -> str:
        """
        生成增量摘要

        使用 LLM 将最近 N 轮对话压缩为结构化摘要。
        异步执行，不阻塞主对话。

        :return: 增量摘要文本
        """
        if not self._llm_call:
            return self._generate_summary_local()

        # 取最近缓冲区
        recent = self._state.recent_turns_buffer[-20:]

        # 构建提示词
        messages = [
            {
                "role": "system",
                "content": (
                    "你是上下文摘要助手。将以下对话压缩为简洁的结构化摘要，"
                    "只保留关键信息。\n\n"
                    "输出格式 (Markdown):\n"
                    "## 本轮摘要\n"
                    "- **用户意图**: 一句话\n"
                    "- **角色动作**: 做了什么\n"
                    "- **关键决策**: 如有\n"
                    "- **当前状态**: 项目阶段/进度\n"
                    "- **待解决问题**: 如有\n"
                    "- **用户情绪**: 满意/中性/不满"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"项目: {self._state.active_project or '无'}\n"
                    f"阶段: {self._state.current_phase or '无'}\n"
                    f"已完成: {', '.join(self._state.completed_modules) or '无'}\n\n"
                    f"对话:\n" +
                    "\n".join(
                        f"[{t['role']}] {t['content'][:300]}"
                        for t in recent
                    )
                ),
            },
        ]

        try:
            result = await self._llm_call(messages, max_tokens=300)
            summary = result.get("content", "")
        except Exception:
            summary = self._generate_summary_local()

        # 更新状态
        self._state.incremental_summaries.append(summary)
        self._state.turns_since_last_summary = 0
        self._state.last_summary_at = now_iso()

        # 只保留最近 10 条摘要
        if len(self._state.incremental_summaries) > 10:
            self._state.incremental_summaries = \
                self._state.incremental_summaries[-10:]

        return summary

    def _generate_summary_local(self) -> str:
        """本地摘要生成 (无 LLM 时的降级方案)"""
        recent = self._state.recent_turns_buffer[-10:]
        user_msgs = [t["content"][:100] for t in recent if t["role"] == "user"]
        assistant_msgs = [t["content"][:100] for t in recent if t["role"] == "assistant"]

        summary = (
            f"## 本轮摘要 (本地)\n"
            f"- **用户意图**: {user_msgs[-1] if user_msgs else '无'}\n"
            f"- **角色动作**: {assistant_msgs[-1][:80] if assistant_msgs else '无'}\n"
            f"- **当前状态**: {self._state.current_phase or '无'}\n"
            f"- **对话轮数**: {self._state.total_turns}\n"
        )
        return summary

    def get_latest_summaries(self, n: int = 3) -> str:
        """获取最近 N 条增量摘要 (用于注入 LLM 上下文)"""
        if not self._state.incremental_summaries:
            return ""
        summaries = self._state.incremental_summaries[-n:]
        return "\n\n---\n\n".join(summaries)

    # ------------------------------------------------------------------ #
    # 纠错触发
    # ------------------------------------------------------------------ #

    def check_correction(self) -> Optional[str]:
        """
        检查是否需要纠错注入

        返回纠错提示文本，或 None（不需要纠错）。

        两把锁:
            1. consecutive_failures >= FAILURE_THRESHOLD → 前提质疑
            2. user_negation_count >= NEGATION_THRESHOLD → 反向自检
            3. 两者都触发 → 强制换人信号
        """
        failures = self._state.consecutive_failures
        negations = self._state.user_negation_count

        # 两者都触发 → 强制换人
        if failures >= FAILURE_THRESHOLD and negations >= NEGATION_THRESHOLD:
            return self._build_force_switch_prompt(failures, negations)

        # 失败计数触发
        if failures >= FAILURE_THRESHOLD:
            return self._build_failure_prompt(failures)

        # 否定计数触发
        if negations >= NEGATION_THRESHOLD:
            return self._build_negation_prompt(negations)

        return None

    def _build_failure_prompt(self, failures: int) -> str:
        """构建'前提质疑'提示"""
        scope = self._state.last_failure_scope or "当前任务"
        return (
            f"\n\n[系统提示 — 秘书]\n"
            f"你刚才在「{scope}」上连续失败了 {failures} 次。"
            f"这是系统层面的硬提示：**立即停下**。\n\n"
            f"不要换方案、不要换参数、不要换变量。\n\n"
            f"请回答两个问题：\n"
            f"1. 你的根本假设是什么？\n"
            f"2. 这个假设的哪个部分已经被证伪了？\n\n"
            f"如果假设被证伪，请**推翻前提重新思考**，而不是在现有方向上继续尝试。"
        )

    def _build_negation_prompt(self, negations: int) -> str:
        """构建'反向自检'提示"""
        last_msg = self._state.last_user_message[:200]
        return (
            f"\n\n[系统提示 — 秘书]\n"
            f"用户连续 {negations} 次表达了否定。"
            f"最近一次用户说：「{last_msg}」\n\n"
            f"请回答：\n"
            f"- 你现在坚持的方向，用户反对的可能原因是什么？\n"
            f"- 如果让你扮演用户，站在用户的角度，你会不会也这样反驳？\n"
            f"- 用户真正想要的是什么？（不是你认为用户该要的，而是用户表达的）"
        )

    def _build_force_switch_prompt(self, failures: int, negations: int) -> str:
        """构建'强制换人'信号"""
        scope = self._state.last_failure_scope or "当前任务"
        return (
            f"\n\n[系统提示 — 秘书 — 强制换人]\n"
            f"你在「{scope}」上连续失败 {failures} 次，"
            f"且用户连续 {negations} 次表达不满。\n\n"
            f"**系统已触发强制切换。** 你的当前会话将被终止，"
            f"任务将移交给新的角色实例。\n\n"
            f"在移交之前，请用一段话总结：\n"
            f"1. 你尝试了什么方向？\n"
            f"2. 为什么失败了？\n"
            f"3. 你认为正确的方向应该是什么？\n\n"
            f"这份总结将交给接手的新角色，它不会看到你的对话历史。"
        )

    def should_force_switch(self) -> bool:
        """判断是否需要强制换人"""
        return (
            self._state.consecutive_failures >= FAILURE_THRESHOLD
            and self._state.user_negation_count >= NEGATION_THRESHOLD
        )

    # ------------------------------------------------------------------ #
    # 文档检索
    # ------------------------------------------------------------------ #

    def retrieve_document(self, doc_name: str) -> Optional[str]:
        """
        根据文档名检索内容

        支持: PROJECT_PLAN, PROJECT_STATUS, tech_debt

        :param doc_name: 文档名（模糊匹配）
        :return: 裁剪后的文档内容，或 None
        """
        doc_lower = doc_name.lower()
        target_path = ""

        if "plan" in doc_lower or "计划" in doc_lower:
            target_path = self._state.project_plan_path
        elif "status" in doc_lower or "状态" in doc_lower:
            target_path = self._state.status_path
        elif "debt" in doc_lower or "债" in doc_lower:
            target_path = self._state.tech_debt_path

        if not target_path:
            return None

        try:
            path = Path(target_path)
            if not path.exists():
                return None

            content = path.read_text(encoding="utf-8")
            # 裁剪到 ~2000 tokens
            return self._trim_content(content, MAX_CONTEXT_TOKENS)
        except Exception:
            return None

    def retrieve_recent_context(self) -> str:
        """
        获取最近对话上下文摘要

        用于注入新角色上下文（强制换人时使用）

        :return: 结构化上下文摘要
        """
        parts = []

        parts.append(f"## 项目状态")
        parts.append(f"- 项目: {self._state.active_project or '无'}")
        parts.append(f"- 阶段: {self._state.current_phase or '无'}")
        parts.append(f"- 已完成: {', '.join(self._state.completed_modules) or '无'}")
        parts.append(f"- 进行中: {self._state.in_progress_module or '无'}")

        parts.append(f"\n## 对话统计")
        parts.append(f"- 总轮数: {self._state.total_turns}")
        parts.append(f"- 连续失败: {self._state.consecutive_failures} 次")
        parts.append(f"- 用户否定: {self._state.user_negation_count} 次")

        if self._state.incremental_summaries:
            parts.append(f"\n## 增量摘要")
            for i, s in enumerate(self._state.incremental_summaries[-3:]):
                parts.append(f"### 摘要 {i + 1}")
                parts.append(s)

        return "\n".join(parts)

    # ------------------------------------------------------------------ #
    # 上下文注入 (供 MasterRole 在 dispatch 前调用)
    # ------------------------------------------------------------------ #

    def build_context_injection(self, user_message: str = "") -> str:
        """
        构建需要注入主 LLM 的上下文

        在 MasterRole 组装 LLM 上下文前调用。
        返回的文本将被注入到 system prompt 之后。

        注入顺序:
            1. 经验提示（如果有匹配的历史经验）
            2. 纠错触发（如果有）
            3. 增量摘要
            4. 项目状态

        :param user_message: 当前用户消息，用于经验匹配
        :return: 注入的上下文文本
        """
        parts = []

        # 0. 经验注入（优先级最高，放在最前面）
        if user_message:
            experience_injection = self.get_experience_injection(user_message)
            if experience_injection:
                parts.append(experience_injection)

        # 1. 纠错触发
        correction = self.check_correction()
        if correction:
            parts.append(correction)

        # 2. 增量摘要
        summaries = self.get_latest_summaries(2)
        if summaries:
            parts.append(f"\n\n## 对话历史摘要 (秘书)\n{summaries}")

        # 3. 项目状态摘要 (如果有活跃项目)
        if self._state.active_project:
            project_ctx = (
                f"\n\n## 项目状态 (秘书)\n"
                f"- 项目: {self._state.active_project}\n"
                f"- 阶段: {self._state.current_phase or '未开始'}\n"
                f"- 已完成: {', '.join(self._state.completed_modules) or '无'}\n"
                f"- 进行中: {self._state.in_progress_module or '无'}"
            )
            parts.append(project_ctx)

        return "\n".join(parts) if parts else ""

    # ------------------------------------------------------------------ #
    # 经验管理 (Secretary 便捷方法)
    # ------------------------------------------------------------------ #

    def record_experience(
        self,
        task_type: str,
        keywords: list[str],
        context: str,
        constraints: list[str],
        successful_approach: list[str],
        failed_attempts: list[str] = None,
    ):
        """
        记录一次成功的操作经验

        在任务成功完成后调用，让秘书记住"这件事怎么做"。

        使用示例:
            secretary.record_experience(
                task_type="git_push",
                keywords=["推送", "push", "github", "git", "提交代码"],
                context="TRAE 环境推送到 GitHub 仓库",
                constraints=[
                    "文件系统白名单限制: 只能操作 c:\\users\\阿拉丁 和 g:\\trae workdesktop\\个人智能助手",
                    "gh CLI 通常未安装",
                ],
                successful_approach=[
                    "1. 使用便携版 Git: G:\\workburddy\\.workbuddy\\vendor\\PortableGit\\cmd\\git.exe",
                    "2. 在允许的路径下创建临时目录",
                    "3. 设置环境变量绕过 Git 配置问题",
                    "4. 使用 --force 推送",
                ],
                failed_attempts=[
                    "在 G:\\temp 下操作会被文件系统白名单拦截",
                    "使用 gh CLI 推送（gh 未安装）",
                ],
            )

        :param task_type: 任务类型标识
        :param keywords: 触发关键词
        :param context: 情境描述
        :param constraints: 环境约束
        :param successful_approach: 成功步骤
        :param failed_attempts: 失败尝试
        """
        if self._experience_manager:
            self._experience_manager.record(
                task_type=task_type,
                keywords=keywords,
                context=context,
                constraints=constraints,
                successful_approach=successful_approach,
                failed_attempts=failed_attempts or [],
            )

    def get_experience_injection(self, user_message: str) -> str:
        """
        获取应注入的经验上下文

        在 LLM 执行任务前调用，将相关经验注入。

        :param user_message: 用户当前消息
        :return: 经验注入文本
        """
        if self._experience_manager:
            return self._experience_manager.get_injection(user_message)
        return ""

    def get_experience_status(self) -> dict:
        """获取经验管理器状态"""
        if self._experience_manager:
            return self._experience_manager.get_status()
        return {"total_experiences": 0, "experience_types": []}

    # ------------------------------------------------------------------ #
    # 工具方法
    # ------------------------------------------------------------------ #

    @staticmethod
    def _trim_content(content: str, max_tokens: int) -> str:
        """
        粗略裁剪内容到指定 token 数

        :param content: 原始内容
        :param max_tokens: 最大 token 数
        :return: 裁剪后的内容
        """
        # 粗略估算: 1 token ≈ 4 字符 (中文) 或 1 token ≈ 0.75 词 (英文)
        char_limit = max_tokens * 3  # 保守估计

        if len(content) <= char_limit:
            return content

        # 截取前 N 字符 + 省略标记
        trimmed = content[:char_limit]
        return trimmed + "\n\n[内容已裁剪，超出上下文限制]"

    def __repr__(self) -> str:
        return (
            f"<Secretary project={self._state.active_project} "
            f"turns={self._state.total_turns} "
            f"failures={self._state.consecutive_failures} "
            f"negations={self._state.user_negation_count}>"
        )


# 全局秘书单例
secretary = Secretary()