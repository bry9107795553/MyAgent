"""
原始归档层 (Archive) — append-only 零损失存储

职责:
    1. 归档写入: 压缩前将原文 append 到 JSONL 文件
    2. 检索查询: 关键词搜索 + 时间范围过滤
    3. 会话回放: 按 session_id 恢复完整对话
    4. 清理维护: 90 天以上文件 gzip 压缩

设计保证:
    - 写入时序: 压缩前先归档，确认写入成功后再执行压缩
    - 零损失: 原始消息永不丢弃，append-only 不覆盖
    - 不进 LLM 上下文: 仅在用户主动查询时按需检索

文件组织:
    archive/{role}/{date}_{session_id}.jsonl
    例如: archive/developer/2026-08-01_sess_a1b2c3d4.jsonl
"""
import gzip
import re
from pathlib import Path
from typing import Optional

from core.memory.store import (
    ARCHIVE_DIR, archive_path,
    read_jsonl, append_jsonl,
    today_str, now_iso,
)
from core.memory.working_memory import Message


# 90 天以上的文件可压缩
ARCHIVE_COMPRESS_DAYS = 90


class Archive:
    """原始归档管理器 — 每个角色独立实例"""

    def __init__(self, role: str):
        self.role = role
        self._role_dir = ARCHIVE_DIR / role
        self._role_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # 归档写入
    # ------------------------------------------------------------------ #

    def append(self, session_id: str, message: Message) -> bool:
        """
        追加一条消息到归档 (写入时序保证: 压缩前先归档)

        :param session_id: 会话 ID
        :param message: 消息对象
        :return: 写入成功返回 True
        """
        path = archive_path(self.role, today_str(), session_id)
        try:
            append_jsonl(path, {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "timestamp": message.timestamp,
                "importance": message.importance,
                "session_id": message.session_id,
                "turn": message.turn,
            })
            return True
        except Exception as e:
            print(f"[Archive] 归档写入失败: {self.role} - {e}")
            return False

    def append_batch(self, session_id: str, messages: list[Message]) -> int:
        """
        批量归档消息 (压缩时使用)

        :param session_id: 会话 ID
        :param messages: 消息列表
        :return: 成功写入条数
        """
        path = archive_path(self.role, today_str(), session_id)
        count = 0
        for msg in messages:
            try:
                append_jsonl(path, {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp,
                    "importance": msg.importance,
                    "session_id": msg.session_id,
                    "turn": msg.turn,
                })
                count += 1
            except Exception as e:
                print(f"[Archive] 批量归档失败: {self.role} msg={msg.id} - {e}")
        return count

    # ------------------------------------------------------------------ #
    # 检索查询
    # ------------------------------------------------------------------ #

    def search(
        self,
        keyword: str = "",
        min_importance: int = 0,
        role_filter: str = "",
        date_from: str = "",
        date_to: str = "",
        limit: int = 50,
    ) -> list[dict]:
        """
        搜索归档消息

        :param keyword: 关键词 (支持正则)
        :param min_importance: 最低重要性过滤
        :param role_filter: 角色过滤 ("user" | "assistant")
        :param date_from: 起始日期 (YYYY-MM-DD)
        :param date_to: 结束日期 (YYYY-MM-DD)
        :param limit: 最大返回条数
        :return: 匹配的消息列表
        """
        results = []
        pattern = re.compile(keyword, re.IGNORECASE) if keyword else None

        for file_path in sorted(self._list_files()):
            # 日期过滤
            if not self._match_date_range(file_path.name, date_from, date_to):
                continue

            for entry in read_jsonl(file_path):
                # 角色过滤
                if role_filter and entry.get("role") != role_filter:
                    continue
                # 重要性过滤
                if entry.get("importance", 0) < min_importance:
                    continue
                # 关键词匹配
                if pattern:
                    content = entry.get("content", "")
                    if not pattern.search(content):
                        continue

                results.append(entry)
                if len(results) >= limit:
                    return results

        return results

    def search_by_session(
        self,
        session_id: str,
        date_str: str = "",
    ) -> list[dict]:
        """
        按 session_id 获取完整会话消息

        :param session_id: 会话 ID
        :param date_str: 日期 (YYYY-MM-DD)，为空则搜索所有文件
        :return: 按时间排序的消息列表
        """
        if date_str:
            path = archive_path(self.role, date_str, session_id)
            return read_jsonl(path) if path.exists() else []

        # 搜索所有文件
        for file_path in sorted(self._list_files()):
            if session_id in file_path.name:
                return read_jsonl(file_path)
        return []

    def recent_sessions(self, limit: int = 10) -> list[dict]:
        """
        获取最近的会话列表

        :param limit: 最大返回数
        :return: [{"session_id": str, "date": str, "message_count": int, "first_message": str}, ...]
        """
        sessions = {}
        for file_path in sorted(self._list_files(), reverse=True):
            name = file_path.stem  # "2026-08-01_sess_a1b2c3d4"
            parts = name.split("_", 1)
            if len(parts) < 2:
                continue
            date_str = parts[0]
            session_id = parts[1]

            if session_id not in sessions:
                entries = read_jsonl(file_path)
                first_msg = ""
                if entries:
                    first_msg = entries[0].get("content", "")[:80]
                sessions[session_id] = {
                    "session_id": session_id,
                    "date": date_str,
                    "message_count": len(entries),
                    "first_message": first_msg,
                }
            if len(sessions) >= limit:
                break

        return list(sessions.values())

    # ------------------------------------------------------------------ #
    # 维护
    # ------------------------------------------------------------------ #

    def vacuum(self, older_than_days: int = ARCHIVE_COMPRESS_DAYS):
        """
        压缩旧归档文件 (90 天以上)

        :param older_than_days: 压缩阈值 (天)
        """
        import time
        from datetime import datetime, timedelta

        cutoff = datetime.now() - timedelta(days=older_than_days)

        for file_path in self._list_files():
            if file_path.suffix == ".gz":
                continue  # 已压缩

            # 从文件名提取日期
            name = file_path.stem
            parts = name.split("_", 1)
            if len(parts) < 2:
                continue
            try:
                file_date = datetime.strptime(parts[0], "%Y-%m-%d")
            except ValueError:
                continue

            if file_date < cutoff:
                self._gzip_compress(file_path)
                print(f"[Archive] 已压缩: {file_path.name}")

    def _gzip_compress(self, file_path: Path):
        """将 JSONL 文件压缩为 .gz"""
        gz_path = file_path.with_suffix(file_path.suffix + ".gz")
        with open(file_path, "rb") as f_in:
            with gzip.open(gz_path, "wb") as f_out:
                f_out.write(f_in.read())
        file_path.unlink()  # 删除原始文件

    # ------------------------------------------------------------------ #
    # 内部方法
    # ------------------------------------------------------------------ #

    def _list_files(self) -> list[Path]:
        """列出所有归档文件 (按文件名排序)，透明处理 .gz 压缩"""
        files = []
        for f in self._role_dir.glob("*.jsonl*"):
            files.append(f)
        files.sort(key=lambda p: p.name)
        return files

    @staticmethod
    def _match_date_range(filename: str, date_from: str, date_to: str) -> bool:
        """检查文件名中的日期是否在范围内"""
        if not date_from and not date_to:
            return True
        # 提取文件名中的日期部分
        parts = filename.split("_", 1)
        if len(parts) < 2:
            return True
        file_date = parts[0]
        if date_from and file_date < date_from:
            return False
        if date_to and file_date > date_to:
            return False
        return True


# ===== 全局归档注册表 =====

class ArchiveRegistry:
    """管理所有角色的归档实例"""

    def __init__(self):
        self._instances: dict[str, Archive] = {}

    def get(self, role: str) -> Archive:
        """获取或创建角色的归档实例"""
        if role not in self._instances:
            self._instances[role] = Archive(role)
        return self._instances[role]

    def vacuum_all(self, older_than_days: int = ARCHIVE_COMPRESS_DAYS):
        """压缩所有角色的旧归档文件"""
        for archive in self._instances.values():
            archive.vacuum(older_than_days)


# 全局归档注册表单例
archive_registry = ArchiveRegistry()