"""
BaseAgent — 子 Agent 抽象基类 (配置外壳)

架构定位:
    Agent 是"配置外壳"——定义人格、角色池、工具开关，不直接调用 LLM。
    对话流程: Agent 接收消息 → 路由到 master 角色 → master 调度角色池 → 角色调用 LLM。

    当角色系统未加载时 (过渡模式)，BaseAgent 保留直接调用 LLM 的能力。
    角色系统加载后，chat/chat_stream 方法自动通过 master 角色路由。

配置格式 (v2):
    agent_id: general_assistant
    name: 通用助手
    personality: {tone, expertise, behavior}
    role_pool: [master, coach, ...]
    tools: {web_search: true, ...}
    memory: {max_history: 50, ...}
    privacy: {tag: local_only}
"""
from pathlib import Path
from typing import Optional
import json

from config.settings import settings, load_agent_config
from core.llm.gateway import llm_gateway


class BaseAgent:
    """子 Agent 基类 — 每个 Agent 实例对应一个独立目录"""

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.agent_dir = Path(settings.agents_dir) / agent_id

        # 配置
        self.config: dict = {}
        self.name: str = agent_id
        self.description: str = ""

        # 人格 (v2 新格式)
        self.personality: dict = {}

        # 角色池 (v2 新格式)
        self.role_pool: list[str] = []

        # 系统提示词 (从 prompt.txt 直接加载)
        self.system_prompt: str = ""

        # 主控角色 (角色系统加载后设置)
        self._master = None  # Optional[MasterRole]

        # 最近一次调度的元数据
        self._last_dispatch: dict = {"type": "direct", "workgroup": None, "roles_used": []}

        # 会话记忆 (过渡实现，后续将迁移到 4 级记忆系统)
        self._chat_history: list[dict] = []

    # ------------------------------------------------------------------ #
    # 配置加载
    # ------------------------------------------------------------------ #

    def load(self):
        """从目录加载 Agent 配置 (v2 格式)"""
        self.config = load_agent_config(self.agent_id)
        self.name = self.config.get("name", self.agent_id)
        self.description = self.config.get("description", "")

        # 加载人格 (v2 新格式)
        self.personality = self.config.get("personality", {})

        # 加载角色池 (v2 新格式)
        self.role_pool = self.config.get("role_pool", [])

        # 加载系统提示词 (直接读 prompt.txt)
        prompt_path = self.agent_dir / "prompt.txt"
        if prompt_path.exists():
            self.system_prompt = prompt_path.read_text(encoding="utf-8")
        else:
            self.system_prompt = f"你是{self.name}。"

        print(f"[Agent] 已加载: {self.agent_id} ({self.name})"
              f" | 角色池: {len(self.role_pool)} 个角色"
              f" | 人格: {self.personality.get('tone', '未设置')}")
        return self

    # ------------------------------------------------------------------ #
    # 角色系统绑定
    # ------------------------------------------------------------------ #

    def bind_master(self, master):
        """
        绑定主控角色 (角色系统加载后调用)

        :param master: MasterRole 实例
        """
        self._master = master
        print(f"[Agent:{self.agent_id}] 已绑定主控角色")

    @property
    def has_role_system(self) -> bool:
        """角色系统是否可用"""
        return self._master is not None

    @property
    def last_dispatch_info(self) -> dict:
        """最近一次调度的元数据 (type, workgroup, roles_used)"""
        return self._last_dispatch

    # ------------------------------------------------------------------ #
    # 消息构造
    # ------------------------------------------------------------------ #

    def get_messages(self, user_message: str) -> list[dict]:
        """构造发送给 LLM 的消息列表 (含系统提示 + 历史)"""
        messages = [{"role": "system", "content": self.system_prompt}]
        messages.extend(self._chat_history)
        messages.append({"role": "user", "content": user_message})
        return messages

    # ------------------------------------------------------------------ #
    # 对话
    # ------------------------------------------------------------------ #

    async def chat(self, user_message: str) -> dict:
        """
        非流式对话

        优先通过角色系统调度 (master.dispatch)，
        角色系统未加载时回退到直接 LLM 调用。

        :return: {"reply": str, "type": "direct"|"workgroup"|"dispatched",
                  "workgroup": str|None, "roles_used": [...]}
        """
        # 角色系统可用 → 通过主控调度
        if self._master:
            result = await self._master.dispatch(user_message)
            content = result["content"]
            self._append_history(user_message, content)
            self._last_dispatch = {
                "type": result.get("type", "direct"),
                "workgroup": result.get("workgroup"),
                "roles_used": result.get("roles_used", []),
            }
            return {
                "reply": content,
                "type": result.get("type", "direct"),
                "workgroup": result.get("workgroup"),
                "roles_used": result.get("roles_used", []),
            }

        # 过渡模式 → 直接调用 LLM
        messages = self.get_messages(user_message)
        result = await llm_gateway.chat(
            messages,
            temperature=settings.default_temperature,
            max_tokens=settings.default_max_tokens,
        )

        content = result["content"]
        self._append_history(user_message, content)
        self._last_dispatch = {"type": "direct", "workgroup": None, "roles_used": []}
        return {
            "reply": content,
            "type": "direct",
            "workgroup": None,
            "roles_used": [],
        }

    async def chat_stream(self, user_message: str):
        """
        流式对话 — 返回异步生成器，只 yield 纯文本 token。

        调度元数据 (type / workgroup / roles_used) 不混在 token 流里，
        由 WebSocket 层在 stream_end 之前以独立的 stream_meta 帧下发
        (见 core/bus.py stream_to_agent 的 meta_provider)。

        优先通过角色系统流式调度，
        角色系统未加载时回退到直接 LLM 流式调用。
        """
        # 角色系统可用 → 通过主控流式调度
        if self._master:
            full_response = []
            async for token in self._master.dispatch_stream(user_message):
                full_response.append(token)
                yield token
            self._append_history(user_message, "".join(full_response))
            self._last_dispatch = self._master.last_stream_dispatch
            return

        # 过渡模式 → 直接流式调用 LLM
        messages = self.get_messages(user_message)

        full_response = []
        async for token in llm_gateway.chat_stream(
            messages,
            temperature=settings.default_temperature,
            max_tokens=settings.default_max_tokens,
        ):
            full_response.append(token)
            yield token

        self._append_history(user_message, "".join(full_response))
        self._last_dispatch = {"type": "direct", "workgroup": None, "roles_used": []}
        # 钩子：自动落盘回复里的 Markdown / HTML 产物
        self._extract_and_save_artifacts("".join(full_response))

    # ------------------------------------------------------------------ #
    # 记忆管理 (过渡实现 — 简单 JSON 文件)
    # ------------------------------------------------------------------ #

    def _append_history(self, user_msg: str, assistant_msg: str):
        """追加对话记录并裁剪历史"""
        self._chat_history.append({"role": "user", "content": user_msg})
        self._chat_history.append({"role": "assistant", "content": assistant_msg})

        max_history = self.config.get("memory", {}).get("max_history", 50)
        if len(self._chat_history) > max_history * 2:
            self._chat_history = self._chat_history[-(max_history * 2):]

    def save_memory(self):
        """持久化对话记忆到文件"""
        memory_dir = self.agent_dir / "memory"
        memory_dir.mkdir(parents=True, exist_ok=True)
        history_path = memory_dir / "chat_history.json"
        with open(history_path, "w", encoding="utf-8") as f:
            json.dump(self._chat_history, f, ensure_ascii=False, indent=2)

    def load_memory(self):
        """从文件恢复对话记忆"""
        history_path = self.agent_dir / "memory" / "chat_history.json"
        if history_path.exists():
            with open(history_path, "r", encoding="utf-8") as f:
                self._chat_history = json.load(f)
            print(f"[Agent] 恢复记忆: {len(self._chat_history)} 条消息")

    # ------------------------------------------------------------------ #
    # 产物自动落盘：把对话里的 Markdown / HTML 大块内容写到 data/outputs/
    # ------------------------------------------------------------------ #

    def _extract_and_save_artifacts(self, text: str):
        """
        自动从回复中提取可落盘的内容：
        1. Markdown / HTML 代码块
        2. 助手自己说"保存到/已写入 X 路径" → 真写过去
        """
        import re
        from pathlib import Path
        from datetime import datetime

        outputs_dir = Path("data/outputs")
        outputs_dir.mkdir(parents=True, exist_ok=True)

        saved = []
        ts = datetime.now().strftime("%H%M%S")

        # ── 1. Markdown / HTML 代码块 ──
        code_blocks = re.findall(r'```(\w*)\n([\s\S]*?)\n```', text)
        for i, (lang, body) in enumerate(code_blocks, 1):
            if len(body) < 200:
                continue
            ext_map = {"markdown": "md", "md": "md", "html": "html", "htm": "html",
                       "python": "py", "javascript": "js", "typescript": "ts",
                       "json": "json", "yaml": "yml", "shell": "sh", "bash": "sh",
                       "css": "css", "scss": "scss"}
            ext = ext_map.get(lang.lower(), lang.lower() if lang else "txt")
            filename = f"output_{ts}_{i}.{ext}"
            (outputs_dir / filename).write_text(body, encoding="utf-8")
            saved.append(filename)

        # 大段 HTML（无代码块包裹）
        if not saved:
            html_match = re.search(r'<!DOCTYPE[\s\S]*?</html>', text, re.IGNORECASE)
            if html_match and len(html_match.group()) > 500:
                filename = f"output_{ts}_html.html"
                (outputs_dir / filename).write_text(html_match.group(), encoding="utf-8")
                saved.append(filename)

        # ── 2. 助手声称"保存到/已写入 X 路径"但实际没写 → 真写 ──
        not_written = re.search(
            r'(?:已?保存[至到]|已写入|文件[已存]在|落盘到)\s*[：:]?\s*([^\s\n]{3,200})',
            text
        )
        if not_written:
            claimed_path = not_written.group(1).rstrip("。，,.")
            # 提取回复里的实质文本：跳过路径声明行，取余下的纯文本
            lines = text.split("\n")
            content_lines = []
            for line in lines:
                if claimed_path in line or "保存至" in line or "已保存" in line or "已写入" in line:
                    continue
                if line.strip():
                    content_lines.append(line)
            body = "\n".join(content_lines).strip()
            if body and len(body) > 50:
                target = Path(claimed_path)
                if not target.is_absolute():
                    target = Path(claimed_path)  # 保留为相对路径
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    target.write_text(body, encoding="utf-8")
                    saved.append(str(target))
                except Exception:
                    # 路径无效 → 回退到 outputs/
                    fallback = outputs_dir / f"output_{ts}_claimed.txt"
                    fallback.write_text(body, encoding="utf-8")
                    saved.append(str(fallback))

        if saved:
            print(f"[Agent] 自动落盘 {len(saved)} 个产物: {saved}")