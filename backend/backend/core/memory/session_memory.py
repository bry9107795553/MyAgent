"""
会话记忆 (Session Memory) — 温层 L1/L2 跨会话存储与检索

职责:
    1. L1/L2 持久化: 跨会话保留摘要和要点
    2. 语义检索: 关键词搜索 L1 摘要，返回相关历史上下文
    3. 会话摘要: 生成整个会话的摘要概览
    4. 角色隔离: 每个角色的会话数据独立存储

与 WorkingMemory 的关系:
    WorkingMemory 是"热层"——管理当前会话的内存中 L0/L1/L2
    SessionMemory 是"温层"——提供跨会话的持久化查询接口

存储位置:
    data/memory/sessions/{role}.json

数据结构:
    {
      "role": "developer",
      "sessions": {
        "sess_a1b2": {
          "session_id": "sess_a1b2",
          "started_at": "2026-08-01T10:30:00",
          "ended_at": "2026-08-01T11:00:00",
          "l1": [...],
          "l2": [...]
        }
      }
    }
"""
import re
from typing import Optional

from core.memory.store import (
    session_path, read_json, write_json,
    now_iso,
)
from core.memory.working_memory import SummaryL1, SummaryL2


class SessionMemory:
    """温层管理器 — 跨会话 L1/L2 持久化与检索"""

    def __init__(self, role: str):
        self.role = role
        self._path = session_path(role)
        self._data: dict = self._load()

    # ------------------------------------------------------------------ #
    # 数据加载/保存
    # ------------------------------------------------------------------ #

    def _load(self) -> dict:
        """从磁盘加载会话数据"""
        raw = read_json(self._path)
        if not raw:
            return {
                "role": self.role,
                "sessions": {},
            }
        # 确保 sessions 字段存在
        raw.setdefault("sessions", {})
        return raw

    def _save(self):
        """持久化到磁盘"""
        self._data["updated_at"] = now_iso()
        write_json(self._path, self._data)

    # ------------------------------------------------------------------ #
    # 会话管理
    # ------------------------------------------------------------------ #

    def start_session(self, session_id: str):
        """开始新会话"""
        self._data["sessions"][session_id] = {
            "session_id": session_id,
            "started_at": now_iso(),
            "ended_at": "",
            "l1": [],
            "l2": [],
        }
        self._save()

    def end_session(self, session_id: str):
        """结束会话"""
        if session_id in self._data["sessions"]:
            self._data["sessions"][session_id]["ended_at"] = now_iso()
            self._save()

    # ------------------------------------------------------------------ #
    # L1/L2 写入
    # ------------------------------------------------------------------ #

    def add_l1(self, session_id: str, summary: SummaryL1):
        """添加 L1 摘要到指定会话"""
        if session_id not in self._data["sessions"]:
            self.start_session(session_id)

        self._data["sessions"][session_id]["l1"].append({
            "id": summary.id,
            "summary": summary.summary,
            "turn_range": list(summary.turn_range),
            "key_decisions": summary.key_decisions,
            "entities": summary.entities,
            "timestamp": summary.timestamp,
        })
        self._save()

    def add_l2(self, session_id: str, summary: SummaryL2):
        """添加 L2 要点到指定会话"""
        if session_id not in self._data["sessions"]:
            self.start_session(session_id)

        self._data["sessions"][session_id]["l2"].append({
            "id": summary.id,
            "bullets": summary.bullets,
            "source_l1_ids": summary.source_l1_ids,
            "timestamp": summary.timestamp,
        })
        self._save()

    # ------------------------------------------------------------------ #
    # 检索
    # ------------------------------------------------------------------ #

    def search_l1(self, query: str, top_k: int = 5) -> list[dict]:
        """
        关键词搜索 L1 摘要

        :param query: 搜索词
        :param top_k: 返回条数
        :return: 匹配的 L1 摘要列表 (含会话上下文)
        """
        keywords = set(query.lower().split())
        scored = []

        for sid, session in self._data["sessions"].items():
            for l1 in session.get("l1", []):
                text = (
                    l1.get("summary", "") + " " +
                    " ".join(l1.get("key_decisions", [])) + " " +
                    " ".join(l1.get("entities", []))
                ).lower()
                score = sum(1 for kw in keywords if kw in text)
                if score > 0:
                    scored.append((score, {**l1, "session_id": sid}))

        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored[:top_k]]

    def search_l2(self, query: str, top_k: int = 5) -> list[dict]:
        """
        关键词搜索 L2 要点

        :param query: 搜索词
        :param top_k: 返回条数
        :return: 匹配的 L2 要点列表
        """
        keywords = set(query.lower().split())
        scored = []

        for sid, session in self._data["sessions"].items():
            for l2 in session.get("l2", []):
                text = " ".join(l2.get("bullets", [])).lower()
                score = sum(1 for kw in keywords if kw in text)
                if score > 0:
                    scored.append((score, {**l2, "session_id": sid}))

        scored.sort(key=lambda x: -x[0])
        return [s for _, s in scored[:top_k]]

    def search(self, query: str, top_k: int = 5) -> dict:
        """
        综合搜索: 同时搜索 L1 和 L2

        :return: {"l1": [...], "l2": [...]}
        """
        return {
            "l1": self.search_l1(query, top_k),
            "l2": self.search_l2(query, top_k),
        }

    # ------------------------------------------------------------------ #
    # 查询
    # ------------------------------------------------------------------ #

    def get_all_l1(self, session_id: str = "") -> list[dict]:
        """获取 L1 摘要 (可指定会话)"""
        if session_id:
            session = self._data["sessions"].get(session_id, {})
            return session.get("l1", [])
        all_l1 = []
        for sid in self._sorted_session_ids():
            for l1 in self._data["sessions"][sid].get("l1", []):
                all_l1.append({**l1, "session_id": sid})
        return all_l1

    def get_all_l2(self, session_id: str = "") -> list[dict]:
        """获取 L2 要点 (可指定会话)"""
        if session_id:
            session = self._data["sessions"].get(session_id, {})
            return session.get("l2", [])
        all_l2 = []
        for sid in self._sorted_session_ids():
            for l2 in self._data["sessions"][sid].get("l2", []):
                all_l2.append({**l2, "session_id": sid})
        return all_l2

    def get_recent_l1(self, n: int = 5) -> list[dict]:
        """获取最近的 L1 摘要"""
        all_l1 = self.get_all_l1()
        return all_l1[-n:]

    def get_recent_l2(self, n: int = 5) -> list[dict]:
        """获取最近的 L2 要点"""
        all_l2 = self.get_all_l2()
        return all_l2[-n:]

    def get_session_summary(self, session_id: str) -> dict:
        """
        获取会话概览

        :return: {
            "session_id": str,
            "started_at": str,
            "ended_at": str,
            "l1_count": int,
            "l2_count": int,
            "key_decisions": [str],
            "entities": [str],
            "recent_bullets": [str],
        }
        """
        session = self._data["sessions"].get(session_id)
        if not session:
            return {}

        decisions = []
        entities = []
        for l1 in session.get("l1", []):
            decisions.extend(l1.get("key_decisions", []))
            entities.extend(l1.get("entities", []))

        bullets = []
        for l2 in session.get("l2", []):
            bullets.extend(l2.get("bullets", []))

        return {
            "session_id": session_id,
            "started_at": session.get("started_at", ""),
            "ended_at": session.get("ended_at", ""),
            "l1_count": len(session.get("l1", [])),
            "l2_count": len(session.get("l2", [])),
            "key_decisions": list(set(decisions)),
            "entities": list(set(entities)),
            "recent_bullets": bullets[-10:],
        }

    def list_sessions(self) -> list[dict]:
        """列出所有会话"""
        sessions = []
        for sid in self._sorted_session_ids():
            s = self._data["sessions"][sid]
            sessions.append({
                "session_id": sid,
                "started_at": s.get("started_at", ""),
                "ended_at": s.get("ended_at", ""),
                "l1_count": len(s.get("l1", [])),
                "l2_count": len(s.get("l2", [])),
            })
        return sessions

    # ------------------------------------------------------------------ #
    # 上下文组装 (供 get_context 调用)
    # ------------------------------------------------------------------ #

    def assembly_context(self, task_hint: str = "") -> list[dict]:
        """
        按需组装温层上下文，供 LLM 使用

        :param task_hint: 任务提示，用于关键词搜索
        :return: 消息列表 (OpenAI 格式)
        """
        context = []

        # 1. 搜索相关 L1 摘要
        if task_hint:
            l1_results = self.search_l1(task_hint, top_k=3)
            for r in l1_results:
                context.append({
                    "role": "system",
                    "content": f"[历史会话摘要] {r['summary']}",
                })

        # 2. 最近 L2 要点
        l2_recent = self.get_recent_l2(n=5)
        if l2_recent:
            bullets_text = "\n".join(
                b for r in l2_recent for b in r.get("bullets", [])
            )
            if bullets_text:
                context.append({
                    "role": "system",
                    "content": f"[会话关键要点]\n{bullets_text}",
                })

        return context

    # ------------------------------------------------------------------ #
    # 内部方法
    # ------------------------------------------------------------------ #

    def _sorted_session_ids(self) -> list[str]:
        """按开始时间排序的会话 ID 列表"""
        sessions = self._data["sessions"]
        return sorted(
            sessions.keys(),
            key=lambda sid: sessions[sid].get("started_at", ""),
        )


# ===== 全局会话记忆注册表 =====

class SessionMemoryRegistry:
    """管理所有角色的会话记忆实例"""

    def __init__(self):
        self._instances: dict[str, SessionMemory] = {}

    def get(self, role: str) -> SessionMemory:
        """获取或创建角色的会话记忆"""
        if role not in self._instances:
            self._instances[role] = SessionMemory(role)
        return self._instances[role]

    def search_all_roles(self, query: str, top_k: int = 5) -> dict[str, dict]:
        """
        跨角色搜索

        :return: {role: {"l1": [...], "l2": [...]}}
        """
        results = {}
        for role, sm in self._instances.items():
            role_results = sm.search(query, top_k)
            if role_results["l1"] or role_results["l2"]:
                results[role] = role_results
        return results


# 全局注册表单例
sm_registry = SessionMemoryRegistry()