"""
工作记忆 (Working Memory) — 热层 L0 管理

职责:
    1. 滑动窗口: 保留最近 N 轮原文消息（默认 N=20）
    2. 压缩触发: token 数 > 4K 或 轮次 > 20 时触发压缩
    3. 上下文组装: 按需组装角色上下文 (L0 + L1 + L2 + L3 + 黑板)
    4. 崩溃恢复: 每 30 秒将内存状态转储到 cache/

数据结构:
    Message = {
        id: str, role: str, content: str,
        timestamp: str, importance: int,
        session_id: str, turn: int
    }

    SummaryL1 = {
        id: str, summary: str,
        turn_range: [int, int],
        key_decisions: [str],
        entities: [str],
        timestamp: str
    }

    SummaryL2 = {
        id: str, bullets: [str],
        source_l1_ids: [str],
        timestamp: str
    }

使用方式:
    wm = WorkingMemory()
    wm.add_message("developer", Message(...))
    context = wm.get_context("developer", task_hint="修复 SummaryCard")
"""
import asyncio
from dataclasses import dataclass, field, asdict
from typing import Optional

from core.memory.store import (
    generate_id, generate_session_id, now_iso,
    dump_cache, load_cache, clear_cache,
    session_path, read_json, write_json,
)


# ===== 数据类 =====

@dataclass
class Message:
    """L0 原文消息"""
    id: str
    role: str           # "system" | "user" | "assistant"
    content: str
    timestamp: str
    importance: int     # 1=低 2=中 3=高
    session_id: str
    turn: int


@dataclass
class SummaryL1:
    """L1 轻度摘要"""
    id: str
    summary: str
    turn_range: tuple   # (start_turn, end_turn)
    key_decisions: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    timestamp: str = ""


@dataclass
class SummaryL2:
    """L2 稠密摘要"""
    id: str
    bullets: list[str] = field(default_factory=list)
    source_l1_ids: list[str] = field(default_factory=list)
    timestamp: str = ""


# ===== 压缩阈值常量 =====

MAX_L0_TOKENS = 4000       # L0 token 上限
MAX_L0_TURNS = 20           # L0 轮次上限
MAX_L1_COUNT = 5            # L1 摘要数上限 (触发 L2 压缩)
MAX_L2_COUNT = 10           # L2 摘要数上限 (触发 L3 实体提取)
CACHE_DUMP_INTERVAL = 30    # 缓存转储间隔 (秒)
EST_CHARS_PER_TOKEN = 2.5   # 中英文混合时每 token 约 2.5 字符


# ===== 工作记忆管理器 =====

class WorkingMemory:
    """热层 L0 管理器 — 每个角色独立实例"""

    def __init__(self, role: str):
        self.role = role
        self.session_id = generate_session_id()
        self._messages: list[Message] = []    # L0 滑动窗口
        self._l1_summaries: list[SummaryL1] = []  # L1 摘要
        self._l2_summaries: list[SummaryL2] = []  # L2 摘要
        self._turn = 0
        self._dump_task: Optional[asyncio.Task] = None

        # 尝试从崩溃缓存恢复
        self._restore_from_cache()

    # ------------------------------------------------------------------ #
    # L0 消息写入
    # ------------------------------------------------------------------ #

    def add_message(self, role: str, content: str, importance: int = 2) -> Message:
        """
        添加一条消息到 L0 滑动窗口

        :param role: "user" | "assistant" | "system"
        :param content: 消息内容
        :param importance: 重要性 1=低 2=中 3=高
        :return: 创建的 Message 对象
        """
        self._turn += 1
        msg = Message(
            id=generate_id("msg"),
            role=role,
            content=content,
            timestamp=now_iso(),
            importance=importance,
            session_id=self.session_id,
            turn=self._turn,
        )
        self._messages.append(msg)

        # 限额裁剪 (保留最近 MAX_L0_TURNS 轮)
        if len(self._messages) > MAX_L0_TURNS * 2:
            self._messages = self._messages[-(MAX_L0_TURNS * 2):]

        return msg

    # ------------------------------------------------------------------ #
    # 压缩触发检测
    # ------------------------------------------------------------------ #

    def should_compress(self) -> dict:
        """
        检测是否需要触发压缩

        :return: {
            "should_compress": bool,
            "reason": str,           # "token_limit" | "turn_limit" | "none"
            "token_count": int,      # 估算 token 数
            "turn_count": int,       # 当前轮次
            "message_count": int,    # 当前消息数
        }
        """
        token_count = self._estimate_tokens()
        turn_count = self._turn
        message_count = len(self._messages)

        if token_count > MAX_L0_TOKENS:
            return {
                "should_compress": True,
                "reason": "token_limit",
                "token_count": token_count,
                "turn_count": turn_count,
                "message_count": message_count,
            }
        if turn_count > MAX_L0_TURNS:
            return {
                "should_compress": True,
                "reason": "turn_limit",
                "token_count": token_count,
                "turn_count": turn_count,
                "message_count": message_count,
            }
        return {
            "should_compress": False,
            "reason": "none",
            "token_count": token_count,
            "turn_count": turn_count,
            "message_count": message_count,
        }

    def should_compress_l2(self) -> bool:
        """L1 摘要数 > MAX_L1_COUNT 时触发 L2 压缩"""
        return len(self._l1_summaries) > MAX_L1_COUNT

    # ------------------------------------------------------------------ #
    # 上下文组装
    # ------------------------------------------------------------------ #

    def get_context(self, task_hint: str = "") -> list[dict]:
        """
        按需组装角色上下文，供 LLM 调用

        :param task_hint: 任务提示，用于关键词匹配 L1 摘要
        :return: 消息列表 (OpenAI 格式)
        """
        context = []

        # 1. L0 原文: 最近 MAX_L0_TURNS 轮
        context.extend(self._messages_to_dicts(self._messages[-MAX_L0_TURNS * 2:]))

        # 2. L1 摘要: 任务引用过去工作时关键词匹配
        if task_hint and self._l1_summaries:
            relevant = self._search_l1(task_hint)
            context.extend([
                {"role": "system", "content": f"[历史摘要] {s.summary}"}
                for s in relevant
            ])

        # 3. L2 要点: 全量注入 (体积小)
        if self._l2_summaries:
            bullets_text = "\n".join(
                f"• {b}" for s in self._l2_summaries for b in s.bullets
            )
            context.append({
                "role": "system",
                "content": f"[关键历史要点]\n{bullets_text}",
            })

        return context

    def get_recent(self, n: int = 20) -> list[dict]:
        """获取最近 N 条消息"""
        return self._messages_to_dicts(self._messages[-n:])

    def get_all_messages(self) -> list[Message]:
        """获取全部 L0 消息 (用于压缩)"""
        return list(self._messages)

    # ------------------------------------------------------------------ #
    # L1/L2 摘要管理
    # ------------------------------------------------------------------ #

    def add_l1(self, summary: SummaryL1):
        """添加 L1 摘要"""
        self._l1_summaries.append(summary)

    def add_l2(self, summary: SummaryL2):
        """添加 L2 摘要"""
        self._l2_summaries.append(summary)

    def get_l1_summaries(self) -> list[SummaryL1]:
        """获取所有 L1 摘要"""
        return list(self._l1_summaries)

    def get_l2_summaries(self) -> list[SummaryL2]:
        """获取所有 L2 摘要"""
        return list(self._l2_summaries)

    # ------------------------------------------------------------------ #
    # 清理 L0 (压缩后调用)
    # ------------------------------------------------------------------ #

    def trim_l0(self, keep_turns: int = 5):
        """
        压缩后清理 L0，只保留最近 N 轮

        :param keep_turns: 保留的轮次数量
        """
        keep = keep_turns * 2  # 每轮 user + assistant
        if len(self._messages) > keep:
            self._messages = self._messages[-keep:]

    # ------------------------------------------------------------------ #
    # 持久化
    # ------------------------------------------------------------------ #

    def save_to_disk(self):
        """将 L1/L2 摘要持久化到 sessions/ 文件"""
        data = {
            "role": self.role,
            "session_id": self.session_id,
            "updated_at": now_iso(),
            "l1": [asdict(s) for s in self._l1_summaries],
            "l2": [asdict(s) for s in self._l2_summaries],
        }
        write_json(session_path(self.role), data)

    def load_from_disk(self):
        """从 sessions/ 文件恢复 L1/L2 摘要"""
        data = read_json(session_path(self.role))
        if not data:
            return

        self.session_id = data.get("session_id", self.session_id)
        for s in data.get("l1", []):
            self._l1_summaries.append(SummaryL1(
                id=s["id"],
                summary=s["summary"],
                turn_range=tuple(s["turn_range"]),
                key_decisions=s.get("key_decisions", []),
                entities=s.get("entities", []),
                timestamp=s.get("timestamp", ""),
            ))
        for s in data.get("l2", []):
            self._l2_summaries.append(SummaryL2(
                id=s["id"],
                bullets=s.get("bullets", []),
                source_l1_ids=s.get("source_l1_ids", []),
                timestamp=s.get("timestamp", ""),
            ))

    # ------------------------------------------------------------------ #
    # 崩溃恢复
    # ------------------------------------------------------------------ #

    def start_cache_dump(self):
        """启动定期缓存转储 (每 30 秒)"""
        async def _dump_loop():
            while True:
                await asyncio.sleep(CACHE_DUMP_INTERVAL)
                self._dump_to_cache()

        self._dump_task = asyncio.create_task(_dump_loop())

    def stop_cache_dump(self):
        """停止缓存转储"""
        if self._dump_task:
            self._dump_task.cancel()
            self._dump_task = None

    def _dump_to_cache(self):
        """将当前状态转储到 cache/"""
        dump_cache(self.role, {
            "session_id": self.session_id,
            "turn": self._turn,
            "messages": [asdict(m) for m in self._messages],
            "l1_count": len(self._l1_summaries),
            "l2_count": len(self._l2_summaries),
        })

    def _restore_from_cache(self):
        """从缓存恢复状态"""
        cached = load_cache(self.role)
        if cached:
            self.session_id = cached.get("session_id", self.session_id)
            self._turn = cached.get("turn", 0)
            for m in cached.get("messages", []):
                self._messages.append(Message(**m))
            print(f"[WorkingMemory] {self.role}: 从缓存恢复 {len(self._messages)} 条消息, "
                  f"turn={self._turn}")

    # ------------------------------------------------------------------ #
    # 内部方法
    # ------------------------------------------------------------------ #

    def _estimate_tokens(self) -> int:
        """估算当前 L0 的 token 数量"""
        total_chars = sum(len(m.content) for m in self._messages)
        return int(total_chars / EST_CHARS_PER_TOKEN)

    def _search_l1(self, hint: str) -> list[SummaryL1]:
        """简单关键词匹配 L1 摘要"""
        keywords = set(hint.lower().split())
        scored = []
        for s in self._l1_summaries:
            text = (s.summary + " ".join(s.key_decisions) + " ".join(s.entities)).lower()
            score = sum(1 for kw in keywords if kw in text)
            if score > 0:
                scored.append((score, s))
        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored[:3]]

    @staticmethod
    def _messages_to_dicts(messages: list[Message]) -> list[dict]:
        """将 Message 列表转为 OpenAI 消息格式"""
        return [
            {"role": m.role, "content": m.content}
            for m in messages
        ]


# ===== 全局工作记忆注册表 =====

class WorkingMemoryRegistry:
    """管理所有角色的工作记忆实例"""

    def __init__(self):
        self._instances: dict[str, WorkingMemory] = {}

    def get(self, role: str) -> WorkingMemory:
        """获取或创建角色的工作记忆"""
        if role not in self._instances:
            wm = WorkingMemory(role)
            wm.load_from_disk()
            self._instances[role] = wm
        return self._instances[role]

    def save_all(self):
        """持久化所有角色的工作记忆"""
        for wm in self._instances.values():
            wm.save_to_disk()

    def shutdown(self):
        """关闭所有实例，停止缓存转储"""
        for wm in self._instances.values():
            wm.stop_cache_dump()
        self.save_all()
        print(f"[WorkingMemory] 已关闭，已保存 {len(self._instances)} 个角色")


# 全局注册表单例
wm_registry = WorkingMemoryRegistry()