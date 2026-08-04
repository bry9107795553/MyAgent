"""
共享黑板 (Blackboard) — 角色间唯一合法通信通道

职责:
    1. 发布消息: 角色完成任务后发布通知
    2. 路由转发: 主控决定谁该看到这条消息 (防火墙)
    3. 读取未读: 目标角色拉取未读消息，标记已读
    4. 脱敏裁剪: 主控转发前裁剪敏感上下文
    5. 访问控制: 角色不直接通信，所有消息经主控路由

通信流程:
    角色完成任务 → publish(task_done) → 主控收到
    主控 → route(from, to, content) → 脱敏 → 转发到目标角色
    目标角色 → fetch_unread(role) → 获取未读 → mark_read

消息类型:
    task_done  — 任务完成通知 (开发 → "SummaryCard 已完成" → 巡检)
    handoff    — 任务交接 (写作 → "初稿已就绪" → 质检)
    question   — 跨角色提问 (巡检 → "这个命名规范有依据吗" → 主控)
    status     — 状态广播 (部署 → "构建中 60%" → 主控)

防火墙规则:
    - minimal_info: 只传递执行任务所需的最小信息
    - no_author_identity: 不附作者信息
    - no_cross_talk: 角色间不直接通信
    - desensitize: 裁剪内部推理过程，只保留结论

存储位置:
    data/memory/blackboard.json

访问控制:
    | 角色    | 发布 | 读取            | 路由 |
    |---------|------|----------------|------|
    | 主控    | 是   | 全部            | 是   |
    | 其他角色 | 是   | 仅主控转发的    | 否   |
"""
from dataclasses import dataclass, field, asdict
from typing import Optional

from core.memory.store import (
    MEMORY_ROOT, read_json, write_json,
    generate_id, now_iso,
)


# 黑板文件路径
BLACKBOARD_PATH = MEMORY_ROOT / "blackboard.json"

# 有效消息类型
VALID_MSG_TYPES = {"task_done", "handoff", "question", "status"}


# ===== 数据类 =====

@dataclass
class BlackboardEntry:
    """黑板消息"""
    id: str
    from_role: str          # 发送角色
    to_role: str            # 接收角色 ("broadcast" = 广播)
    msg_type: str           # 消息类型
    content: str            # 消息内容
    timestamp: str          # 发送时间
    read_by: list[str] = field(default_factory=list)  # 已读角色列表
    priority: str = "normal"  # "urgent" | "normal" | "low"


# ===== 黑板管理器 =====

class Blackboard:
    """共享黑板 — 角色间通信总线"""

    def __init__(self):
        self._path = BLACKBOARD_PATH
        self._data: dict = self._load()
        # 内存中缓存未读消息 (按角色)
        self._unread_cache: dict[str, list[str]] = {}

    # ------------------------------------------------------------------ #
    # 数据加载/保存
    # ------------------------------------------------------------------ #

    def _load(self) -> dict:
        """从磁盘加载黑板数据"""
        raw = read_json(self._path)
        if not raw:
            return {
                "version": "1.0",
                "messages": [],
                "stats": {
                    "total_messages": 0,
                    "last_updated": "",
                },
            }
        raw.setdefault("messages", [])
        raw.setdefault("stats", {
            "total_messages": len(raw["messages"]),
            "last_updated": raw.get("stats", {}).get("last_updated", ""),
        })
        return raw

    def _save(self):
        """持久化到磁盘"""
        self._data["stats"]["total_messages"] = len(self._data["messages"])
        self._data["stats"]["last_updated"] = now_iso()
        write_json(self._path, self._data)

    # ------------------------------------------------------------------ #
    # 发布消息
    # ------------------------------------------------------------------ #

    def publish(
        self,
        from_role: str,
        to_role: str,
        msg_type: str,
        content: str,
        priority: str = "normal",
    ) -> BlackboardEntry:
        """
        发布一条黑板消息

        :param from_role: 发送角色
        :param to_role: 接收角色 ("broadcast" = 广播给所有角色)
        :param msg_type: 消息类型 (task_done | handoff | question | status)
        :param content: 消息内容
        :param priority: 优先级 (urgent | normal | low)
        :return: 创建的 BlackboardEntry
        """
        if msg_type not in VALID_MSG_TYPES:
            raise ValueError(
                f"无效的消息类型: {msg_type}。"
                f"有效类型: {', '.join(sorted(VALID_MSG_TYPES))}"
            )

        entry = BlackboardEntry(
            id=generate_id("bb"),
            from_role=from_role,
            to_role=to_role,
            msg_type=msg_type,
            content=content,
            timestamp=now_iso(),
            read_by=[],
            priority=priority,
        )
        self._data["messages"].append(asdict(entry))

        # 更新未读缓存
        if to_role != from_role:  # 不发给自己
            self._unread_cache.setdefault(to_role, []).append(entry.id)

        self._save()
        print(f"[Blackboard] {from_role} → {to_role} [{msg_type}]: {content[:60]}...")
        return entry

    # ------------------------------------------------------------------ #
    # 路由转发 (主控防火墙)
    # ------------------------------------------------------------------ #

    def route(
        self,
        from_role: str,
        to_role: str,
        content: str,
        msg_type: str = "task_done",
        desensitize: bool = True,
        strip_author: bool = True,
    ) -> Optional[BlackboardEntry]:
        """
        主控防火墙路由: 脱敏后转发消息

        这是主控的专属方法。其他角色不直接调用。
        主控收到消息后，裁剪敏感信息，然后转发给目标角色。

        :param from_role: 原始发送角色
        :param to_role: 目标接收角色
        :param content: 原始内容
        :param msg_type: 消息类型
        :param desensitize: 是否脱敏 (去除内部推理)
        :param strip_author: 是否去除作者身份
        :return: 转发的 BlackboardEntry
        """
        # 脱敏: 保留结论和产出，去除内部推理
        if desensitize:
            content = self._desensitize(content)

        # 去作者: 用 "某角色" 替代具体角色名
        if strip_author:
            content = self._strip_author(content, from_role)

        return self.publish(
            from_role="master",
            to_role=to_role,
            msg_type=msg_type,
            content=content,
        )

    def route_broadcast(
        self,
        content: str,
        msg_type: str = "status",
        exclude_roles: list[str] | None = None,
    ) -> list[BlackboardEntry]:
        """
        主控向所有角色广播 (状态更新等)

        :param content: 广播内容
        :param msg_type: 消息类型
        :param exclude_roles: 排除的角色列表
        :return: 创建的 BlackboardEntry 列表
        """
        exclude = set(exclude_roles or [])
        exclude.add("master")  # 主控不给自己广播

        entries = []
        for role in self._get_all_roles():
            if role not in exclude:
                entry = self.publish(
                    from_role="master",
                    to_role=role,
                    msg_type=msg_type,
                    content=content,
                )
                entries.append(entry)
        return entries

    # ------------------------------------------------------------------ #
    # 读取消息
    # ------------------------------------------------------------------ #

    def fetch_unread(self, role: str) -> list[dict]:
        """
        获取指定角色的未读消息

        :param role: 角色名
        :return: 未读消息列表 (按时间排序)
        """
        unread = []
        for msg in self._data["messages"]:
            # 只获取发给该角色或广播的消息，且未读
            if msg["to_role"] not in (role, "broadcast"):
                continue
            if role in msg.get("read_by", []):
                continue
            unread.append(msg)

        return sorted(unread, key=lambda m: m["timestamp"])

    def fetch_all(self, role: str, limit: int = 50) -> list[dict]:
        """
        获取指定角色的所有消息 (含已读)

        :param role: 角色名
        :param limit: 最大返回数
        :return: 消息列表
        """
        messages = []
        for msg in self._data["messages"]:
            if msg["to_role"] in (role, "broadcast"):
                messages.append(msg)
        return sorted(
            messages,
            key=lambda m: m["timestamp"],
            reverse=True,
        )[:limit]

    def fetch_by_type(self, role: str, msg_type: str) -> list[dict]:
        """按类型获取消息"""
        return [
            m for m in self._data["messages"]
            if m["to_role"] in (role, "broadcast")
            and m["msg_type"] == msg_type
        ]

    # ------------------------------------------------------------------ #
    # 标记已读
    # ------------------------------------------------------------------ #

    def mark_read(self, role: str, message_ids: list[str]):
        """
        标记消息为已读

        :param role: 角色名
        :param message_ids: 消息 ID 列表
        """
        for msg in self._data["messages"]:
            if msg["id"] in message_ids:
                read_by = msg.setdefault("read_by", [])
                if role not in read_by:
                    read_by.append(role)

        # 更新缓存
        if role in self._unread_cache:
            ids_set = set(message_ids)
            self._unread_cache[role] = [
                mid for mid in self._unread_cache[role]
                if mid not in ids_set
            ]

        self._save()

    def mark_all_read(self, role: str):
        """标记该角色的所有消息为已读"""
        ids = []
        for msg in self._data["messages"]:
            if msg["to_role"] in (role, "broadcast"):
                if role not in msg.get("read_by", []):
                    msg.setdefault("read_by", []).append(role)
                    ids.append(msg["id"])

        self._unread_cache.pop(role, None)
        self._save()
        print(f"[Blackboard] {role}: 已标记 {len(ids)} 条消息为已读")

    # ------------------------------------------------------------------ #
    # 查询与统计
    # ------------------------------------------------------------------ #

    def get_unread_count(self, role: str) -> int:
        """获取未读消息数"""
        return len(self.fetch_unread(role))

    def get_stats(self) -> dict:
        """获取黑板统计"""
        types_count = {}
        for msg in self._data["messages"]:
            t = msg["msg_type"]
            types_count[t] = types_count.get(t, 0) + 1

        return {
            "total_messages": len(self._data["messages"]),
            "by_type": types_count,
            "last_updated": self._data["stats"]["last_updated"],
        }

    def has_unread(self, role: str) -> bool:
        """是否有未读消息"""
        return self.get_unread_count(role) > 0

    # ------------------------------------------------------------------ #
    # 维护
    # ------------------------------------------------------------------ #

    def cleanup_old(self, max_keep: int = 500):
        """
        清理旧消息 (保留最近 N 条)

        :param max_keep: 最大保留条数
        """
        if len(self._data["messages"]) <= max_keep:
            return

        self._data["messages"] = self._data["messages"][-max_keep:]
        self._save()
        print(f"[Blackboard] 清理旧消息: 保留最近 {max_keep} 条")

    def clear(self):
        """清空所有消息 (慎用)"""
        self._data["messages"] = []
        self._unread_cache = {}
        self._save()
        print("[Blackboard] 已清空所有消息")

    # ------------------------------------------------------------------ #
    # 脱敏工具 (防火墙规则)
    # ------------------------------------------------------------------ #

    def _desensitize(self, content: str) -> str:
        """
        脱敏: 去除内部推理，保留结论和产出

        规则:
        - 移除 "我认为"、"我觉得"、"根据分析" 等主观表达
        - 移除推理过程标记 (如 "步骤1/2/3")
        - 保留结论、数据、代码片段
        """
        # 简化版: 去除常见推理前缀
        lines = content.split("\n")
        cleaned = []
        for line in lines:
            stripped = line.strip()
            # 跳过推理标记行
            if any(stripped.startswith(p) for p in [
                "我认为", "我觉得", "根据分析", "推理过程",
                "步骤", "首先", "其次", "然后", "最后",
                "我的思路", "分析如下",
            ]):
                continue
            cleaned.append(line)
        return "\n".join(cleaned).strip()

    def _strip_author(self, content: str, author_role: str) -> str:
        """
        去除作者身份信息

        :param content: 原始内容
        :param author_role: 作者角色名
        :return: 去身份后的内容
        """
        # 移除角色名引用
        name_map = {
            "developer": "开发",
            "designer": "设计",
            "writer": "写作",
            "inspector": "巡检",
            "tester": "测试",
            "deployer": "部署",
            "cleaner": "清洁",
            "translator": "翻译",
            "knowledge_retriever": "检索",
            "quality_checker": "质检",
            "scheduler": "日程",
            "creative": "创意",
            "visual_analyzer": "视觉分析",
            "coach": "教练",
            "master": "主控",
        }
        role_name = name_map.get(author_role, author_role)
        content = content.replace(f"我({role_name})", "某角色")
        content = content.replace(f"我（{role_name}）", "某角色")
        return content

    # ------------------------------------------------------------------ #
    # 内部方法
    # ------------------------------------------------------------------ #

    def _get_all_roles(self) -> list[str]:
        """从消息中提取所有出现的角色名"""
        roles = set()
        for msg in self._data["messages"]:
            roles.add(msg["from_role"])
            if msg["to_role"] != "broadcast":
                roles.add(msg["to_role"])
        return sorted(roles)


# 全局黑板单例
blackboard = Blackboard()