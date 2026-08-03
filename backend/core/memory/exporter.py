"""
对话导出器 (ConversationExporter) — 从归档提取角色对话并输出为 Markdown 文档

职责:
    1. 按角色提取: 从 Archive 中提取指定角色的完整对话记录
    2. 跨角色汇总: 合并多个角色的对话记录，按时间线排列
    3. 日期过滤: 支持按日期范围筛选
    4. 会话过滤: 支持按 session_id 筛选
    5. 格式输出: 生成 Markdown 文档，含会话元信息、逐轮对话、统计摘要
    6. 安全脱敏: 自动脱敏用户敏感信息 (邮箱、手机号、IP 等)

使用方式:
    from core.memory.exporter import ConversationExporter

    exporter = ConversationExporter()
    doc = exporter.export(
        roles=["writer", "coach"],
        date_from="2026-07-01",
        date_to="2026-08-01",
        output_path="exports/writer_analysis.md",
    )
"""
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.memory.archive import archive_registry, Archive
from core.memory.store import (
    ARCHIVE_DIR, read_jsonl, generate_id, now_iso,
)


# ===== 敏感信息脱敏规则 =====

SENSITIVE_PATTERNS = [
    # 邮箱
    (re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"), "[邮箱已脱敏]"),
    # 手机号 (中国)
    (re.compile(r"1[3-9]\d{9}"), "[手机号已脱敏]"),
    # IP 地址
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "[IP已脱敏]"),
    # 身份证号 (中国)
    (re.compile(r"\b\d{17}[\dXx]\b"), "[身份证已脱敏]"),
]


def desensitize(text: str) -> str:
    """对文本进行敏感信息脱敏"""
    for pattern, replacement in SENSITIVE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ===== 对话导出器 =====

class ConversationExporter:
    """对话导出器 — 从归档中提取并格式化对话记录"""

    def __init__(self):
        self._export_dir: Optional[Path] = None

    # ------------------------------------------------------------------ #
    # 导出入口
    # ------------------------------------------------------------------ #

    def export(
        self,
        roles: list[str],
        date_from: str = "",
        date_to: str = "",
        session_id: str = "",
        output_path: str = "",
        desensitize_content: bool = True,
        limit: int = 500,
    ) -> str:
        """
        导出角色对话为 Markdown 文档

        :param roles: 要导出的角色 ID 列表，如 ["writer", "coach"]
        :param date_from: 起始日期 (YYYY-MM-DD)，空则不限制
        :param date_to: 结束日期 (YYYY-MM-DD)，空则不限制
        :param session_id: 指定会话 ID，空则导出所有匹配会话
        :param output_path: 输出文件路径，空则返回字符串不写文件
        :param desensitize_content: 是否脱敏敏感信息
        :param limit: 最大消息条数 (防止导出过大)
        :return: Markdown 格式的对话文档
        """
        # 1. 提取所有角色的对话消息
        all_messages: list[dict] = []
        for role_id in roles:
            archive = archive_registry.get(role_id)
            messages = self._extract_messages(
                archive, role_id, date_from, date_to, session_id,
            )
            all_messages.extend(messages)

        # 2. 按时间戳排序
        all_messages.sort(key=lambda m: m.get("timestamp", ""))

        # 3. 限制数量
        if len(all_messages) > limit:
            all_messages = all_messages[-limit:]

        # 4. 格式化为 Markdown
        markdown = self._format_markdown(
            messages=all_messages,
            roles=roles,
            date_from=date_from,
            date_to=date_to,
            session_id=session_id,
            desensitize=desensitize_content,
        )

        # 5. 写入文件
        if output_path:
            self._write_file(output_path, markdown)

        return markdown

    def export_by_session(
        self,
        role_id: str,
        session_id: str,
        date_str: str = "",
        output_path: str = "",
        desensitize_content: bool = True,
    ) -> str:
        """
        按会话导出单个角色的完整对话

        :param role_id: 角色 ID
        :param session_id: 会话 ID
        :param date_str: 日期 (YYYY-MM-DD)
        :param output_path: 输出文件路径
        :param desensitize_content: 是否脱敏
        :return: Markdown 格式的对话文档
        """
        archive = archive_registry.get(role_id)
        messages = archive.search_by_session(session_id, date_str)

        return self._format_markdown(
            messages=messages,
            roles=[role_id],
            session_id=session_id,
            desensitize=desensitize_content,
        )

    # ------------------------------------------------------------------ #
    # 消息提取
    # ------------------------------------------------------------------ #

    def _extract_messages(
        self,
        archive: Archive,
        role_id: str,
        date_from: str,
        date_to: str,
        session_id: str,
    ) -> list[dict]:
        """从单个角色的归档中提取消息"""
        results = []

        for file_path in sorted(archive._list_files()):
            # 日期过滤
            if not archive._match_date_range(file_path.name, date_from, date_to):
                continue

            for entry in read_jsonl(file_path):
                # 会话过滤
                if session_id and entry.get("session_id") != session_id:
                    continue

                # 标记来源角色
                entry["_source_role"] = role_id
                results.append(entry)

        return results

    # ------------------------------------------------------------------ #
    # Markdown 格式化
    # ------------------------------------------------------------------ #

    def _format_markdown(
        self,
        messages: list[dict],
        roles: list[str],
        date_from: str = "",
        date_to: str = "",
        session_id: str = "",
        desensitize: bool = True,
    ) -> str:
        """将消息列表格式化为 Markdown 文档"""
        if not messages:
            return self._empty_doc(roles, date_from, date_to, session_id)

        parts = []

        # ── 文档头部 ──
        parts.append("# 角色对话导出报告")
        parts.append("")
        parts.append(f"**导出时间**: {now_iso()}")
        parts.append(f"**导出角色**: {', '.join(roles)}")
        if date_from:
            parts.append(f"**起始日期**: {date_from}")
        if date_to:
            parts.append(f"**结束日期**: {date_to}")
        if session_id:
            parts.append(f"**会话 ID**: {session_id}")
        parts.append(f"**消息总数**: {len(messages)}")
        parts.append("")
        parts.append("---")
        parts.append("")

        # ── 统计摘要 ──
        stats = self._compute_stats(messages)
        parts.append("## 统计摘要")
        parts.append("")
        parts.append(f"| 指标 | 数值 |")
        parts.append(f"|------|------|")
        parts.append(f"| 总消息数 | {stats['total']} |")
        parts.append(f"| 用户消息 | {stats['user_count']} |")
        parts.append(f"| 助手消息 | {stats['assistant_count']} |")
        parts.append(f"| 涉及会话数 | {stats['session_count']} |")
        parts.append(f"| 时间跨度 | {stats['time_span']} |")
        if stats['roles_detail']:
            for role_name, count in stats['roles_detail'].items():
                parts.append(f"| {role_name} 消息 | {count} |")
        parts.append("")
        parts.append("---")
        parts.append("")

        # ── 逐轮对话 ──
        parts.append("## 对话记录")
        parts.append("")

        current_session = ""
        current_turn = 0

        for i, msg in enumerate(messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            timestamp = msg.get("timestamp", "")
            msg_session = msg.get("session_id", "")
            source_role = msg.get("_source_role", "")

            # 会话切换标记
            if msg_session and msg_session != current_session:
                current_session = msg_session
                current_turn = 0
                parts.append(f"### 📁 会话: `{current_session[:12]}...`")
                parts.append("")

            current_turn += 1

            # 脱敏
            if desensitize:
                content = desensitize(content)

            # 角色标签
            role_label = "👤 用户" if role == "user" else f"🤖 {source_role or '助手'}"

            parts.append(f"**{role_label}** · `{timestamp[:19]}` · 轮次 #{current_turn}")
            parts.append("")
            parts.append(content)
            parts.append("")
            parts.append("---")
            parts.append("")

        # ── 文档尾部 ──
        parts.append("")
        parts.append(f"> 此文档由 MyAgent 对话导出器自动生成 · {now_iso()}")
        parts.append("> 敏感信息已自动脱敏 (邮箱/手机号/IP/身份证)")

        return "\n".join(parts)

    def _compute_stats(self, messages: list[dict]) -> dict:
        """计算消息统计信息"""
        user_count = sum(1 for m in messages if m.get("role") == "user")
        assistant_count = sum(1 for m in messages if m.get("role") == "assistant")
        sessions = set(m.get("session_id", "") for m in messages if m.get("session_id"))

        # 角色分布
        roles_detail = {}
        for m in messages:
            if m.get("role") == "assistant":
                src = m.get("_source_role", "unknown")
                roles_detail[src] = roles_detail.get(src, 0) + 1

        # 时间跨度
        timestamps = [m.get("timestamp", "") for m in messages if m.get("timestamp")]
        time_span = "N/A"
        if timestamps:
            first = timestamps[0][:10]
            last = timestamps[-1][:10]
            time_span = f"{first} ~ {last}"

        return {
            "total": len(messages),
            "user_count": user_count,
            "assistant_count": assistant_count,
            "session_count": len(sessions),
            "time_span": time_span,
            "roles_detail": roles_detail,
        }

    def _empty_doc(self, roles: list[str], date_from: str, date_to: str, session_id: str) -> str:
        """生成空文档"""
        return f"""# 角色对话导出报告

**导出时间**: {now_iso()}
**导出角色**: {', '.join(roles)}
**日期范围**: {date_from or '不限'} ~ {date_to or '不限'}
**会话 ID**: {session_id or '不限'}

---

## 结果

> ⚠ 未找到匹配的对话记录。

> 此文档由 MyAgent 对话导出器自动生成 · {now_iso()}
"""

    # ------------------------------------------------------------------ #
    # 文件写入
    # ------------------------------------------------------------------ #

    def _write_file(self, path: str, content: str):
        """写入文件 (自动创建目录)"""
        file_path = Path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"[Exporter] 已导出到: {file_path}")

    # ------------------------------------------------------------------ #
    # 便捷方法
    # ------------------------------------------------------------------ #

    def list_exportable_sessions(
        self,
        role_id: str,
        limit: int = 20,
    ) -> list[dict]:
        """
        列出可导出的会话列表

        :param role_id: 角色 ID
        :param limit: 最大返回数
        :return: 会话列表
        """
        archive = archive_registry.get(role_id)
        return archive.recent_sessions(limit)

    def export_all_roles(
        self,
        date_from: str = "",
        date_to: str = "",
        output_dir: str = "",
        desensitize_content: bool = True,
    ) -> dict[str, str]:
        """
        导出所有角色的对话 (每个角色一个文件)

        :param date_from: 起始日期
        :param date_to: 结束日期
        :param output_dir: 输出目录
        :param desensitize_content: 是否脱敏
        :return: {role_id: file_path} 映射
        """
        results = {}
        for role_dir in ARCHIVE_DIR.iterdir():
            if not role_dir.is_dir():
                continue
            role_id = role_dir.name

            output_path = ""
            if output_dir:
                output_path = str(
                    Path(output_dir) / f"{role_id}_{date_from or 'all'}_{date_to or 'all'}.md"
                )

            markdown = self.export(
                roles=[role_id],
                date_from=date_from,
                date_to=date_to,
                output_path=output_path,
                desensitize_content=desensitize_content,
            )
            results[role_id] = output_path or "(仅返回内容)"

        return results


# 全局导出器单例
exporter = ConversationExporter()