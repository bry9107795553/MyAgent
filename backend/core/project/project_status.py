"""
ProjectStatusManager — 项目状态快照管理器

职责:
    1. 管理 data/projects/{project_name}/PROJECT_STATUS.md 的读写
    2. 供教练在每阶段结束时自动更新状态
    3. 供主控在会话启动时检测并呈现状态摘要

设计原则:
    - 状态文件是 Markdown 格式，人类和 Agent 可读
    - 结构化字段可编程读写，非结构化内容以 Markdown 段落保存
    - 所有写操作通过原子写入保证一致性

与方案书 3.7 节的对应关系:
    本模块是方案书描述的"项目状态快照机制"的完整实现
"""

import re
from pathlib import Path
from datetime import datetime
from typing import Optional, NamedTuple

from core.memory.store import read_json, write_json


# ===== 路径常量 =====

PROJECTS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data" / "projects"
)


# ===== 数据结构 =====

class ModuleEntry(NamedTuple):
    """模块条目"""
    name: str
    status: str          # "done" | "in_progress" | "pending"
    note: str = ""       # 附加说明 (如 "developer — 已实现 3/5 状态")


class ProjectStatus(NamedTuple):
    """项目状态快照"""
    project_name: str
    current_phase: str       # e.g. "Phase 2 — 开发中（60%）"
    last_updated: str        # ISO 时间戳
    active_agent: str        # 最后活跃的 Agent 名称
    completed: list[ModuleEntry]
    in_progress: list[ModuleEntry]
    pending: list[ModuleEntry]
    tech_debt: list[str]     # 技术债条目
    blockers: list[str]      # 阻塞项
    raw_content: str = ""    # 原始 Markdown 全文


# ===== 核心管理器 =====

class ProjectStatusManager:
    """
    项目状态管理器

    使用方式:
        manager = ProjectStatusManager()
        status = manager.get_status("todo_app")
        manager.mark_module_complete("todo_app", "TaskCard 组件")
        summary = manager.get_summary("todo_app")
    """

    # ------------------------------------------------------------------ #
    # 读取
    # ------------------------------------------------------------------ #

    def get_status(self, project_name: str) -> Optional[ProjectStatus]:
        """
        读取项目状态快照

        :param project_name: 项目名称 (目录名)
        :return: ProjectStatus 或 None (文件不存在)
        """
        status_path = self._status_path(project_name)
        if not status_path.exists():
            return None

        content = status_path.read_text(encoding="utf-8")
        return self._parse_status(project_name, content)

    def get_summary(self, project_name: str) -> Optional[str]:
        """
        获取状态摘要 (供主控向用户呈现)

        返回格式: 当前阶段 + 完成数/总数 + 进行中 + 阻塞项

        :param project_name: 项目名称
        :return: 摘要文本，或 None
        """
        status = self.get_status(project_name)
        if not status:
            return None

        lines = [
            f"项目「{project_name}」",
            f"当前阶段: {status.current_phase}",
            f"已完成: {len(status.completed)} 个模块",
        ]

        if status.in_progress:
            names = ", ".join(m.name for m in status.in_progress)
            lines.append(f"进行中: {names}")

        lines.append(f"待完成: {len(status.pending)} 个模块")

        if status.blockers:
            lines.append(f"阻塞: {', '.join(status.blockers)}")

        lines.append(f"最后更新: {status.last_updated}")

        return "\n".join(lines)

    def list_projects(self) -> list[dict]:
        """
        列出所有有状态文件的项目

        :return: [{project_name, current_phase, last_updated, summary}]
        """
        _ensure_dir()
        results = []

        for proj_dir in PROJECTS_DIR.iterdir():
            if not proj_dir.is_dir():
                continue
            status_file = proj_dir / "PROJECT_STATUS.md"
            if not status_file.exists():
                continue

            status = self.get_status(proj_dir.name)
            if not status:
                results.append({
                    "project_name": proj_dir.name,
                    "current_phase": "未知",
                    "last_updated": "",
                    "summary": "状态文件无法解析",
                })
                continue

            results.append({
                "project_name": status.project_name,
                "current_phase": status.current_phase,
                "last_updated": status.last_updated,
                "active_agent": status.active_agent,
                "completed_count": len(status.completed),
                "in_progress_count": len(status.in_progress),
                "pending_count": len(status.pending),
                "blocker_count": len(status.blockers),
                "summary": self.get_summary(status.project_name),
            })

        return results

    # ------------------------------------------------------------------ #
    # 更新
    # ------------------------------------------------------------------ #

    def create_status(
        self,
        project_name: str,
        current_phase: str = "Phase 0 — 需求分析",
        active_agent: str = "",
        plan_summary: str = "",
    ) -> ProjectStatus:
        """
        创建新的项目状态文件 (教练 Phase 0 完成后调用)

        :param project_name: 项目名称
        :param current_phase: 当前阶段描述
        :param active_agent: 活跃 Agent 名称
        :param plan_summary: 来自 PROJECT_PLAN 的模块列表摘要
        :return: 创建的 ProjectStatus
        """
        _ensure_dir()
        proj_dir = PROJECTS_DIR / project_name
        proj_dir.mkdir(parents=True, exist_ok=True)

        now = _now_str()
        status = ProjectStatus(
            project_name=project_name,
            current_phase=current_phase,
            last_updated=now,
            active_agent=active_agent,
            completed=[],
            in_progress=[],
            pending=[],
            tech_debt=[],
            blockers=[],
        )

        self._write_status(project_name, status)
        print(f"[ProjectStatus] 已创建项目状态: {project_name} ({current_phase})")
        return status

    def update_phase(
        self,
        project_name: str,
        new_phase: str,
        active_agent: str = "",
    ) -> bool:
        """
        更新当前阶段 (教练在阶段切换时调用)

        :param project_name: 项目名称
        :param new_phase: 新阶段描述
        :param active_agent: 活跃 Agent 名称
        :return: 是否成功
        """
        status = self.get_status(project_name)
        if not status:
            return False

        updated = status._replace(
            current_phase=new_phase,
            last_updated=_now_str(),
            active_agent=active_agent or status.active_agent,
        )
        self._write_status(project_name, updated)
        print(f"[ProjectStatus] 阶段更新: {project_name} → {new_phase}")
        return True

    def mark_module_complete(
        self,
        project_name: str,
        module_name: str,
        active_agent: str = "",
    ) -> bool:
        """
        将模块标记为已完成 (从"进行中"移到"已完成")

        :param project_name: 项目名称
        :param module_name: 模块名称
        :param active_agent: 活跃 Agent
        :return: 是否成功
        """
        return self._move_module(
            project_name, module_name,
            from_status="in_progress", to_status="done",
            active_agent=active_agent,
        )

    def mark_module_in_progress(
        self,
        project_name: str,
        module_name: str,
        note: str = "",
        active_agent: str = "",
    ) -> bool:
        """
        将模块标记为进行中 (从"待完成"移到"进行中")

        :param project_name: 项目名称
        :param module_name: 模块名称
        :param note: 附加说明
        :param active_agent: 活跃 Agent
        :return: 是否成功
        """
        return self._move_module(
            project_name, module_name,
            from_status="pending", to_status="in_progress",
            note=note, active_agent=active_agent,
        )

    def add_module(
        self,
        project_name: str,
        module_name: str,
        status: str = "pending",
        note: str = "",
        active_agent: str = "",
    ) -> bool:
        """
        新增模块到待完成列表

        :param project_name: 项目名称
        :param module_name: 模块名称
        :param status: 初始状态 (pending | in_progress)
        :param note: 附加说明
        :param active_agent: 活跃 Agent
        :return: 是否成功
        """
        snap = self.get_status(project_name)
        if not snap:
            return False

        entry = ModuleEntry(name=module_name, status=status, note=note)
        updated = snap._replace(
            pending=snap.pending + [entry] if status == "pending" else snap.pending,
            in_progress=snap.in_progress + [entry] if status == "in_progress" else snap.in_progress,
            last_updated=_now_str(),
            active_agent=active_agent or snap.active_agent,
        )
        self._write_status(project_name, updated)
        print(f"[ProjectStatus] 新增模块: {project_name} / {module_name} ({status})")
        return True

    def add_tech_debt(
        self,
        project_name: str,
        debt_item: str,
        active_agent: str = "",
    ) -> bool:
        """
        新增技术债条目

        :param project_name: 项目名称
        :param debt_item: 技术债描述
        :param active_agent: 活跃 Agent
        :return: 是否成功
        """
        snap = self.get_status(project_name)
        if not snap:
            return False

        updated = snap._replace(
            tech_debt=snap.tech_debt + [debt_item],
            last_updated=_now_str(),
            active_agent=active_agent or snap.active_agent,
        )
        self._write_status(project_name, updated)
        return True

    def set_blockers(
        self,
        project_name: str,
        blockers: list[str],
        active_agent: str = "",
    ) -> bool:
        """
        设置阻塞项 (替换全部)

        :param project_name: 项目名称
        :param blockers: 阻塞项列表
        :param active_agent: 活跃 Agent
        :return: 是否成功
        """
        snap = self.get_status(project_name)
        if not snap:
            return False

        updated = snap._replace(
            blockers=blockers,
            last_updated=_now_str(),
            active_agent=active_agent or snap.active_agent,
        )
        self._write_status(project_name, updated)
        return True

    def touch(self, project_name: str, active_agent: str = "") -> bool:
        """
        更新最后活跃时间 (会话结束时调用)

        :param project_name: 项目名称
        :param active_agent: 活跃 Agent
        :return: 是否成功
        """
        snap = self.get_status(project_name)
        if not snap:
            return False

        updated = snap._replace(
            last_updated=_now_str(),
            active_agent=active_agent or snap.active_agent,
        )
        self._write_status(project_name, updated)
        return True

    # ------------------------------------------------------------------ #
    # 内部方法
    # ------------------------------------------------------------------ #

    def _move_module(
        self,
        project_name: str,
        module_name: str,
        from_status: str,
        to_status: str,
        note: str = "",
        active_agent: str = "",
    ) -> bool:
        """内部方法: 在状态列表间移动模块"""
        snap = self.get_status(project_name)
        if not snap:
            return False

        from_list = getattr(snap, from_status, [])
        to_list = getattr(snap, to_status, [])

        # 查找匹配的模块
        found = None
        remaining = []
        for entry in from_list:
            if entry.name == module_name:
                found = entry
            else:
                remaining.append(entry)

        if not found:
            # 模块不存在于来源列表，尝试新建
            entry = ModuleEntry(name=module_name, status=to_status, note=note)
            to_list = to_list + [entry]
            remaining = from_list
        else:
            entry = ModuleEntry(
                name=found.name,
                status=to_status,
                note=note or found.note,
            )
            to_list = to_list + [entry]

        kwargs = {
            from_status: remaining,
            to_status: to_list,
            "last_updated": _now_str(),
            "active_agent": active_agent or snap.active_agent,
        }
        updated = snap._replace(**kwargs)
        self._write_status(project_name, updated)
        print(f"[ProjectStatus] 模块移动: {project_name} / {module_name} "
              f"({from_status} → {to_status})")
        return True

    def _write_status(self, project_name: str, status: ProjectStatus):
        """将状态快照写入 PROJECT_STATUS.md (原子写入)"""
        _ensure_dir()
        proj_dir = PROJECTS_DIR / project_name
        proj_dir.mkdir(parents=True, exist_ok=True)

        content = self._format_status(status)
        status_path = proj_dir / "PROJECT_STATUS.md"

        # 原子写入: 临时文件 → rename
        tmp_path = status_path.with_name(f".PROJECT_STATUS.tmp")
        try:
            tmp_path.write_text(content, encoding="utf-8")
            tmp_path.replace(status_path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    def _parse_status(self, project_name: str, content: str) -> ProjectStatus:
        """
        解析 PROJECT_STATUS.md 内容为结构化数据

        解析策略:
            - 正则匹配固定字段 (当前阶段 / 最后更新 / 活跃 Agent)
            - 分别解析已完成 / 进行中 / 待完成 / 技术债 / 阻塞项 列表
        """
        last_updated = _extract_field(content, r"最后更新[：:]\s*(.+)", default="")
        active_agent = _extract_field(content, r"活跃\s*Agent[：:]\s*(.+)", default="")
        current_phase = _extract_field(content, r"^##\s*当前阶段\s*\n(.+)", default="")

        completed = _parse_module_list(content, "已完成")
        in_progress = _parse_module_list(content, "进行中")
        pending = _parse_module_list(content, "待完成")
        tech_debt = _parse_simple_list(content, "技术债")
        blockers = _parse_simple_list(content, "阻塞项")

        return ProjectStatus(
            project_name=project_name,
            current_phase=current_phase.strip(),
            last_updated=last_updated.strip(),
            active_agent=active_agent.strip(),
            completed=completed,
            in_progress=in_progress,
            pending=pending,
            tech_debt=tech_debt,
            blockers=blockers,
            raw_content=content,
        )

    def _format_status(self, status: ProjectStatus) -> str:
        """将结构化状态格式化为 Markdown"""
        lines = [
            f"# 项目状态：{status.project_name}",
            "",
            f"> 最后更新：{status.last_updated}"
            + (f" | 活跃 Agent：{status.active_agent}" if status.active_agent else ""),
            "",
            "## 当前阶段",
            status.current_phase,
            "",
        ]

        # 已完成
        lines.append("## 已完成")
        if status.completed:
            for m in status.completed:
                lines.append(f"- [x] {m.name}"
                             + (f" ({m.note})" if m.note else ""))
        else:
            lines.append("- (暂无)")
        lines.append("")

        # 进行中
        lines.append("## 进行中")
        if status.in_progress:
            for m in status.in_progress:
                lines.append(f"- [~] {m.name}"
                             + (f" ({m.note})" if m.note else ""))
        else:
            lines.append("- (暂无)")
        lines.append("")

        # 待完成
        lines.append("## 待完成")
        if status.pending:
            for m in status.pending:
                lines.append(f"- [ ] {m.name}"
                             + (f" ({m.note})" if m.note else ""))
        else:
            lines.append("- (暂无)")
        lines.append("")

        # 技术债
        lines.append("## 技术债")
        if status.tech_debt:
            for d in status.tech_debt:
                lines.append(f"- {d}")
        else:
            lines.append("- (暂无)")
        lines.append("")

        # 阻塞项
        lines.append("## 阻塞项")
        if status.blockers:
            for b in status.blockers:
                lines.append(f"- {b}")
        else:
            lines.append("- 无")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _status_path(project_name: str) -> Path:
        """获取 PROJECT_STATUS.md 路径"""
        return PROJECTS_DIR / project_name / "PROJECT_STATUS.md"


# ===== 辅助函数 =====

def _ensure_dir():
    """确保项目目录存在"""
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)


def _now_str() -> str:
    """返回当前时间字符串"""
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _extract_field(content: str, pattern: str, default: str = "") -> str:
    """从 Markdown 中提取单个字段"""
    match = re.search(pattern, content, re.MULTILINE)
    return match.group(1).strip() if match else default


def _parse_module_list(content: str, section: str) -> list[ModuleEntry]:
    """
    解析模块列表

    格式:
        ## 已完成
        - [x] 模块名 (备注)
        - [x] 模块名
    """
    results = []
    in_section = False

    for line in content.split("\n"):
        line = line.strip()

        if line.startswith(f"## {section}"):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break

        if not in_section:
            continue

        # 匹配模块行: - [x] 模块名 (备注) 或 - [~] 模块名 或 - [ ] 模块名
        match = re.match(r"- \[([x~ ])\]\s+(.+?)(?:\s*\((.+)\))?$", line)
        if not match:
            continue

        checkbox = match.group(1)
        name = match.group(2).strip()
        note = match.group(3).strip() if match.group(3) else ""

        status_map = {"x": "done", "~": "in_progress", " ": "pending"}
        results.append(ModuleEntry(
            name=name,
            status=status_map.get(checkbox, "pending"),
            note=note,
        ))

    return results


def _parse_simple_list(content: str, section: str) -> list[str]:
    """解析简单列表 (无 checkbox 状态)"""
    results = []
    in_section = False

    for line in content.split("\n"):
        line = line.strip()

        if line.startswith(f"## {section}"):
            in_section = True
            continue
        if in_section and line.startswith("## "):
            break

        if not in_section:
            continue

        # 匹配列表项: - 内容
        match = re.match(r"- (.+)", line)
        if match:
            item = match.group(1).strip()
            if item and item != "(暂无)" and item != "无":
                results.append(item)

    return results


# 全局单例
project_status = ProjectStatusManager()