"""
秘书机制 — 上下文管理与纠错 + 经验管理

架构定位:
    秘书是 orchestrator 级别的机制，不是第 17 个角色。
    负责: 运行时状态追踪、增量摘要生成、纠错触发、文档检索注入、经验管理。

五层分工:
    对话层 — 主 LLM（Master/Coach/Receiver）跟用户聊、做决策、派单
    摘要层 — 秘书 每 5-10 轮生成增量摘要 → 注入 LLM 上下文
    状态层 — 秘书 维护 runtime_state（阶段/模块/文档指针）→ orchestrator 内存
    检索层 — 秘书 主 LLM 要翻旧文档时，精准取片段 → orchestrator 内存 → 注入
    经验层 — 秘书 记录成功操作的模式 → 跨会话复用 → 下次遇到同类任务时自动注入

设计原则:
    - runtime_state 不占 LLM 上下文
    - 秘书只负责"读状态 → 分析 → 生成片段"，把片段注入主 LLM
    - 主 LLM 不需要知道自己有"外部记忆"
    - 秘书每 5-10 轮才激活一次，避免上下文爆炸
    - 经验是"成功的方法论"——记录约束条件 + 成功路径，不是又一轮摘要
"""
import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union


# ===== 否定关键词模式 =====

NEGATION_PATTERNS = [
    r"不对",
    r"不是",
    r"你错了",
    r"错了",
    r"傻逼",
    r"神经病",
    r"不行",
    r"别",
    r"不要",
    r"停",
    r"你在干什么",
    r"你搞错了",
    r"你理解错了",
    r"你又来",
    r"我不是这个意思",
    r"完全错误",
    r"大错特错",
    r"搞什么",
    r"我服了",
    r"我真服了",
    r"别这样",
    r"重来",
    r"重新想",
    r"你到底",
    r"你有没有在听",
    r"听不懂人话",
    r"我说的是",
    r"我要的是",
    r"这不是我要的",
]

# ===== 失败关键词模式 =====

FAILURE_PATTERNS = [
    r"(?:error|Error|错误|失败|异常|报错|不行|不工作|无法|崩溃|挂了)",
    r"(?:timeout|超时|连接失败|拒绝连接|not found|404|500)",
    r"(?:build failed|编译失败|部署失败|启动失败)",
    r"(?:我试了.*不行|试了.*没用|换了.*还是)",
]


# ===== 运行时状态 =====

@dataclass
class RuntimeState:
    """
    秘书维护的运行时状态

    存在 orchestrator 内存中，不占 LLM 上下文。
    只记录"指针"和"状态"，不存完整内容。
    """

    # ── 项目状态 ──
    active_project: str = ""
    current_phase: str = ""
    completed_modules: List[str] = field(default_factory=list)
    in_progress_module: str = ""

    # ── 文档指针 ──
    project_plan_path: str = ""
    status_path: str = ""
    tech_debt_path: str = ""

    # ── 对话统计 ──
    total_turns: int = 0
    turns_since_last_summary: int = 0
    last_summary_at: str = ""

    # ── 纠错状态 ──
    consecutive_failures: int = 0
    user_negation_count: int = 0
    last_failure_scope: str = ""
    last_user_message: str = ""
    active_role_id: str = ""

    # ── 增量摘要 ──
    incremental_summaries: List[str] = field(default_factory=list)
    recent_turns_buffer: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "active_project": self.active_project,
            "current_phase": self.current_phase,
            "completed_modules": self.completed_modules,
            "in_progress_module": self.in_progress_module,
            "project_plan_path": self.project_plan_path,
            "status_path": self.status_path,
            "tech_debt_path": self.tech_debt_path,
            "total_turns": self.total_turns,
            "turns_since_last_summary": self.turns_since_last_summary,
            "last_summary_at": self.last_summary_at,
            "consecutive_failures": self.consecutive_failures,
            "user_negation_count": self.user_negation_count,
            "last_failure_scope": self.last_failure_scope,
            "active_role_id": self.active_role_id,
            "incremental_summaries": self.incremental_summaries,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RuntimeState":
        return cls(
            active_project=data.get("active_project", ""),
            current_phase=data.get("current_phase", ""),
            completed_modules=data.get("completed_modules", []),
            in_progress_module=data.get("in_progress_module", ""),
            project_plan_path=data.get("project_plan_path", ""),
            status_path=data.get("status_path", ""),
            tech_debt_path=data.get("tech_debt_path", ""),
            total_turns=data.get("total_turns", 0),
            turns_since_last_summary=data.get("turns_since_last_summary", 0),
            last_summary_at=data.get("last_summary_at", ""),
            consecutive_failures=data.get("consecutive_failures", 0),
            user_negation_count=data.get("user_negation_count", 0),
            last_failure_scope=data.get("last_failure_scope", ""),
            active_role_id=data.get("active_role_id", ""),
            incremental_summaries=data.get("incremental_summaries", []),
        )


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
    task_type: str = ""
    keywords: List[str] = field(default_factory=list)
    context: str = ""
    constraints: List[str] = field(default_factory=list)
    successful_approach: List[str] = field(default_factory=list)
    failed_attempts: List[str] = field(default_factory=list)
    timestamp: str = ""
    success_count: int = 1

    def to_dict(self) -> dict:
        return {
            "task_type": self.task_type, "keywords": self.keywords,
            "context": self.context, "constraints": self.constraints,
            "successful_approach": self.successful_approach,
            "failed_attempts": self.failed_attempts,
            "timestamp": self.timestamp, "success_count": self.success_count,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExperienceRecord":
        return cls(**{k: data.get(k, v.default if hasattr(v, 'default') else v.default_factory() if hasattr(v, 'default_factory') else "")
                      for k, v in cls.__dataclass_fields__.items()})


class ExperienceManager:
    """经验管理器 — 秘书的长期记忆"""

    def __init__(self, storage_dir: str = ""):
        self._storage_dir = storage_dir or "data/experiences"
        self._experiences: List[ExperienceRecord] = []
        self._load_all()

    def _load_all(self):
        exp_dir = self._storage_dir
        if not os.path.isdir(exp_dir):
            return
        for fn in os.listdir(exp_dir):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(exp_dir, fn), "r", encoding="utf-8") as f:
                    data = json.load(f)
                items = data if isinstance(data, list) else [data]
                for item in items:
                    self._experiences.append(ExperienceRecord.from_dict(item))
            except Exception:
                pass

    def _save(self, record: ExperienceRecord):
        exp_dir = self._storage_dir
        os.makedirs(exp_dir, exist_ok=True)
        fp = os.path.join(exp_dir, f"{record.task_type}.json")
        existing = []
        if os.path.exists(fp):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if isinstance(existing, dict):
                    existing = [existing]
            except Exception:
                existing = []
        new_approach = "\n".join(record.successful_approach)
        for ex in existing:
            if "\n".join(ex.get("successful_approach", [])) == new_approach:
                ex["success_count"] = ex.get("success_count", 1) + 1
                ex["timestamp"] = record.timestamp
                with open(fp, "w", encoding="utf-8") as f:
                    json.dump(existing, f, ensure_ascii=False, indent=2)
                return
        existing.append(record.to_dict())
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)

    def record(self, task_type, keywords, context, constraints,
               successful_approach, failed_attempts):
        record = ExperienceRecord(
            task_type=task_type, keywords=keywords, context=context,
            constraints=constraints, successful_approach=successful_approach,
            failed_attempts=failed_attempts,
            timestamp=datetime.now(timezone.utc).isoformat(), success_count=1,
        )
        self._save(record)
        self._experiences.append(record)

    def find(self, user_message: str) -> List[ExperienceRecord]:
        if not user_message:
            return []
        msg_lower = user_message.lower()
        matched = [e for e in self._experiences
                   if any(kw.lower() in msg_lower for kw in e.keywords)]
        matched.sort(key=lambda e: e.success_count, reverse=True)
        return matched

    def get_injection(self, user_message: str) -> str:
        experiences = self.find(user_message)
        if not experiences:
            return ""
        parts = ["\n\n---\n## 秘书经验提示 (来自过往成功操作)\n"]
        for i, exp in enumerate(experiences[:3]):
            parts.append(f"### 经验 {i+1}: {exp.task_type}")
            parts.append(f"**情境**: {exp.context}")
            parts.append(f"**已验证 {exp.success_count} 次**")
            if exp.constraints:
                parts.append("\n**⚠️ 环境约束**:")
                for c in exp.constraints:
                    parts.append(f"  - {c}")
            if exp.failed_attempts:
                parts.append("\n**❌ 已知失败方案 (不要重复)**:")
                for f in exp.failed_attempts:
                    parts.append(f"  - {f}")
            if exp.successful_approach:
                parts.append("\n**✅ 成功步骤 (请严格遵循)**:")
                for step in exp.successful_approach:
                    parts.append(f"  {step}")
            parts.append("")
        parts.append(
            "> ⚠️ 以上经验来自过往成功操作，请优先参考成功步骤，"
            "避免重复已知的失败方案。"
        )
        return "\n".join(parts)


# ===== 秘书类 =====

class Secretary:
    """
    秘书 — 上下文管理员

    不是角色，是 orchestrator 的方法集合。
    负责:
        1. 运行时状态追踪
        2. 增量摘要生成
        3. 纠错触发判断
        4. 文档检索注入

    使用方式:
        secretary = Secretary()
        secretary.init(session_id, llm_call=my_llm_function)

        # 每轮对话后
        secretary.record_turn(user_message, role_response, role_id)

        # 检查是否需要纠错
        correction = secretary.check_correction()
        if correction:
            pass  # 将 correction 注入下一轮 LLM 上下文

        # 检查是否需要摘要
        if secretary.should_summarize():
            summary = await secretary.generate_summary()
    """

    SUMMARY_INTERVAL = 5
    FAILURE_THRESHOLD = 3
    NEGATION_THRESHOLD = 3
    RECENT_BUFFER_SIZE = 20
    MAX_DOC_TOKENS = 2000

    def __init__(self):
        self._state: Optional[RuntimeState] = None
        self._session_id: str = ""
        self._llm_call: Optional[Callable] = None
        self._state_dir: str = ""
        self._experience_manager: Optional[ExperienceManager] = None

    # ------------------------------------------------------------------ #
    # 初始化
    # ------------------------------------------------------------------ #

    def init(self, session_id: str, llm_call: Optional[Callable] = None, state_dir: str = ""):
        self._session_id = session_id
        self._llm_call = llm_call
        self._state_dir = state_dir or "data"
        self._state = self._load_state()
        if self._state is None:
            self._state = RuntimeState()
        self._experience_manager = ExperienceManager(
            os.path.join(self._state_dir, "experiences")
        )
        print(f"[Secretary] 已初始化 | 会话: {session_id} | 轮次: {self._state.total_turns}")
        return self

    # ------------------------------------------------------------------ #
    # 状态持久化
    # ------------------------------------------------------------------ #

    def _get_state_file(self) -> str:
        return os.path.join(self._state_dir, "sessions", f"secretary_{self._session_id}.json")

    def _load_state(self) -> Optional[RuntimeState]:
        fn = self._get_state_file()
        if os.path.exists(fn):
            try:
                with open(fn, "r", encoding="utf-8") as f:
                    return RuntimeState.from_dict(json.load(f))
            except Exception:
                pass
        return None

    def _save_state(self):
        if not self._state:
            return
        fn = self._get_state_file()
        os.makedirs(os.path.dirname(fn), exist_ok=True)
        with open(fn, "w", encoding="utf-8") as f:
            json.dump(self._state.to_dict(), f, ensure_ascii=False, indent=2)

    # ------------------------------------------------------------------ #
    # 每轮记录
    # ------------------------------------------------------------------ #

    def record_turn(self, user_message: str, role_response: str, role_id: str = ""):
        if not self._state:
            return

        self._state.total_turns += 1
        self._state.turns_since_last_summary += 1
        self._state.last_user_message = user_message
        self._state.active_role_id = role_id

        turn = self._state.total_turns
        self._state.recent_turns_buffer.append({
            "role": "user", "content": user_message[:500], "turn": turn,
        })
        self._state.recent_turns_buffer.append({
            "role": "assistant", "content": role_response[:500] if role_response else "", "turn": turn,
        })

        if len(self._state.recent_turns_buffer) > self.RECENT_BUFFER_SIZE * 2:
            self._state.recent_turns_buffer = self._state.recent_turns_buffer[-self.RECENT_BUFFER_SIZE * 2:]

        if self._detect_negation(user_message):
            self._state.user_negation_count += 1
        else:
            self._state.user_negation_count = 0

        if self._detect_failure(role_response):
            self._state.consecutive_failures += 1
        else:
            self._state.consecutive_failures = 0

        self._save_state()

    # ------------------------------------------------------------------ #
    # 检测
    # ------------------------------------------------------------------ #

    def _detect_negation(self, message: str) -> bool:
        if not message:
            return False
        for pattern in NEGATION_PATTERNS:
            if re.search(pattern, message):
                return True
        return False

    def _detect_failure(self, response: str) -> bool:
        if not response:
            return False
        for pattern in FAILURE_PATTERNS:
            if re.search(pattern, response):
                return True
        return False

    # ------------------------------------------------------------------ #
    # 摘要生成
    # ------------------------------------------------------------------ #

    def should_summarize(self) -> bool:
        if not self._state:
            return False
        return self._state.turns_since_last_summary >= self.SUMMARY_INTERVAL

    async def generate_summary(self) -> str:
        if not self._state or not self._llm_call:
            return ""

        turns = self._state.recent_turns_buffer
        if not turns:
            return ""

        conversation_text = "\n".join(
            f"[{t['role']}] {t['content'][:300]}" for t in turns[-10:]
        )

        summary_prompt = f"""你是上下文摘要员。请将以下对话片段压缩为 3-5 条关键要点:

{conversation_text}

要求:
- 每条要点一行，以 "•" 开头
- 保留决策、偏好、技术选型、关键结论
- 去除寒暄、确认、填充内容
- 控制在 200 字以内"""

        try:
            summary = await self._llm_call([
                {"role": "system", "content": "你是专业的上下文摘要员，只输出关键要点。"},
                {"role": "user", "content": summary_prompt},
            ])

            if summary:
                self._state.incremental_summaries.append(summary)
                self._state.turns_since_last_summary = 0
                self._state.last_summary_at = datetime.now(timezone.utc).isoformat()
                self._save_state()
                print(f"[Secretary] 已生成增量摘要 ({len(summary)} 字符)")
                return summary
        except Exception as e:
            print(f"[Secretary] 摘要生成失败: {e}")

        return ""

    # ------------------------------------------------------------------ #
    # 纠错触发
    # ------------------------------------------------------------------ #

    def check_correction(self) -> Optional[str]:
        if not self._state:
            return None

        failures = self._state.consecutive_failures
        negations = self._state.user_negation_count

        if failures >= self.FAILURE_THRESHOLD and negations >= self.NEGATION_THRESHOLD:
            return self._build_force_switch_prompt(failures, negations)

        if failures >= self.FAILURE_THRESHOLD:
            return self._build_premise_question_prompt(failures)

        if negations >= self.NEGATION_THRESHOLD:
            return self._build_reverse_check_prompt(negations)

        return None

    def _build_premise_question_prompt(self, failure_count: int) -> str:
        return f"""[系统提示 — 秘书纠错]
你刚才 {failure_count} 次尝试都失败了。这是系统层面的硬提示：立即停下。

不要换方案、不要换参数、不要换变量。

回答两个问题：
1. 你的根本假设是什么？
2. 这个假设的哪个部分已经被证伪了？

基于以上分析，重新评估整个方向。"""

    def _build_reverse_check_prompt(self, negation_count: int) -> str:
        return f"""[系统提示 — 秘书纠错]
用户连续 {negation_count} 次表达否定。请回答：

- 你现在坚持的方向，用户反对的可能原因是什么？
- 如果让你扮演用户，你会不会也这样反驳？

基于以上分析，重新理解用户意图。"""

    def _build_force_switch_prompt(self, failure_count: int, negation_count: int) -> str:
        return f"""[系统提示 — 秘书纠错 · 最高级]
你已连续失败 {failure_count} 次，且用户连续 {negation_count} 次否定你的方向。

当前角色已不适合继续处理此任务。请：
1. 立即停止当前方向的所有尝试
2. 输出一段简短的状态摘要（当前状态、失败原因、剩余工作）
3. 主动建议将任务转交给其他角色重新评估

不要尝试继续修复。不要做任何建设性工作。只做交接。"""

    # ------------------------------------------------------------------ #
    # 上下文注入
    # ------------------------------------------------------------------ #

    def get_context_injection(self, user_message: str = "") -> str:
        if not self._state:
            return ""

        parts = []

        # 0. 经验注入（优先级最高）
        if user_message and self._experience_manager:
            exp_injection = self._experience_manager.get_injection(user_message)
            if exp_injection:
                parts.append(exp_injection)

        summaries = self._state.incremental_summaries
        if summaries:
            recent = summaries[-3:]
            parts.append("## 历史摘要\n" + "\n---\n".join(recent))

        if self._state.active_project:
            parts.append(
                f"## 项目状态\n"
                f"- 项目: {self._state.active_project}\n"
                f"- 阶段: {self._state.current_phase or '未开始'}\n"
                f"- 已完成模块: {', '.join(self._state.completed_modules) if self._state.completed_modules else '无'}\n"
                f"- 进行中: {self._state.in_progress_module or '无'}"
            )

        correction = self.check_correction()
        if correction:
            parts.append(correction)

        return "\n\n".join(parts) if parts else ""

    # ------------------------------------------------------------------ #
    # 文档检索
    # ------------------------------------------------------------------ #

    def get_document(self, doc_name: str, max_tokens: int = None) -> str:
        if not self._state:
            return ""

        max_chars = (max_tokens or self.MAX_DOC_TOKENS) * 2
        doc_name_lower = doc_name.lower()

        path_map = {
            "project_plan": self._state.project_plan_path,
            "project_status": self._state.status_path,
            "tech_debt": self._state.tech_debt_path,
        }

        path = None
        for key, val in path_map.items():
            if key in doc_name_lower:
                path = val
                break

        if not path or not os.path.exists(path):
            return f"[秘书] 未找到文档: {doc_name}"

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            if len(content) > max_chars:
                content = content[:max_chars] + "\n\n[... 内容已截断 ...]"
            return content
        except Exception as e:
            return f"[秘书] 读取文档失败: {e}"

    def set_project_docs(self, project_plan: str = "", status: str = "", tech_debt: str = ""):
        if not self._state:
            return
        if project_plan:
            self._state.project_plan_path = project_plan
        if status:
            self._state.status_path = status
        if tech_debt:
            self._state.tech_debt_path = tech_debt
        self._save_state()

    def set_project(self, name: str, phase: str = ""):
        if not self._state:
            return
        self._state.active_project = name
        if phase:
            self._state.current_phase = phase
        self._save_state()

    def add_completed_module(self, module_name: str):
        if not self._state:
            return
        if module_name not in self._state.completed_modules:
            self._state.completed_modules.append(module_name)
        self._state.in_progress_module = ""
        self._save_state()

    def set_in_progress(self, module_name: str):
        if not self._state:
            return
        self._state.in_progress_module = module_name
        self._save_state()

    # ------------------------------------------------------------------ #
    # 经验管理 (Secretary 便捷方法)
    # ------------------------------------------------------------------ #

    def record_experience(self, task_type: str, keywords: List[str],
                          context: str, constraints: List[str],
                          successful_approach: List[str],
                          failed_attempts: List[str] = None):
        """记录一次成功的操作经验"""
        if self._experience_manager:
            self._experience_manager.record(
                task_type=task_type, keywords=keywords, context=context,
                constraints=constraints, successful_approach=successful_approach,
                failed_attempts=failed_attempts or [],
            )

    def get_experience_injection(self, user_message: str) -> str:
        """获取经验注入文本"""
        if self._experience_manager:
            return self._experience_manager.get_injection(user_message)
        return ""

    # ------------------------------------------------------------------ #
    # 状态查询
    # ------------------------------------------------------------------ #

    @property
    def state(self) -> Optional[RuntimeState]:
        return self._state

    def get_status(self) -> dict:
        if not self._state:
            return {"status": "未初始化"}
        return {
            "session_id": self._session_id,
            "total_turns": self._state.total_turns,
            "turns_since_summary": self._state.turns_since_last_summary,
            "consecutive_failures": self._state.consecutive_failures,
            "user_negation_count": self._state.user_negation_count,
            "summary_count": len(self._state.incremental_summaries),
            "active_project": self._state.active_project,
            "current_phase": self._state.current_phase,
        }


# ===== 全局单例 =====

secretary = Secretary()