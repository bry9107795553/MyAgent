"""
Lifecycle Manager — 子 Agent 生命周期管理
- 从模板创建新 Agent (复制骨架目录)
- 删除 Agent (删除目录，watchdog 自动注销)
- 导出 Agent 为模板 JSON
- 导入模板 JSON 为新 Agent
"""
from pathlib import Path
import shutil
import json
import yaml
import time
from typing import Optional

from config.settings import settings


# 默认角色池 (新建 Agent 时自动分配的基础角色)
DEFAULT_ROLE_POOL = ["master", "knowledge_retriever", "writer", "quality_checker"]


class AgentLifecycle:
    """Agent 生命周期管理器"""

    def __init__(self):
        self.templates_dir = Path(settings.agents_dir).parent / "templates"
        self.templates_dir.mkdir(parents=True, exist_ok=True)

    def create_agent(
        self,
        agent_id: str,
        name: str,
        description: str = "",
        template: str = "default",
        system_prompt: str = "",
        role_pool: list[str] | None = None,
    ) -> dict:
        """
        创建新 Agent — 复制模板目录到 data/agents/{agent_id}/
        watchdog 检测到新目录后自动注册

        :param agent_id: Agent 唯一标识
        :param name: Agent 名称
        :param description: Agent 描述
        :param template: 模板名称 (对应 data/templates/ 下的目录)
        :param system_prompt: 自定义系统提示词 (为空则使用模板默认值)
        :param role_pool: 角色池 (为空则使用默认基础角色)
        """
        agent_dir = Path(settings.agents_dir) / agent_id
        if agent_dir.exists():
            raise ValueError(f"Agent 已存在: {agent_id}")

        # 尝试从模板复制
        template_dir = self.templates_dir / template
        if template_dir.exists():
            shutil.copytree(template_dir, agent_dir)
        else:
            # 没有模板就创建空骨架
            self._create_skeleton(agent_dir)

        # 写入 config.yaml (v2 新格式: personality + role_pool)
        config = {
            "agent_id": agent_id,
            "name": name,
            "description": description,
            "personality": {
                "tone": "专业、友好",
                "expertise": description or "通用助手",
                "behavior": "根据用户需求提供帮助，复杂任务自动调度角色池处理",
            },
            "role_pool": role_pool or DEFAULT_ROLE_POOL,
            "tools": {
                "file_read": True,
                "file_write": False,
                "web_search": False,
                "code_exec": False,
            },
            "memory": {
                "max_history": 50,
                "long_term_enabled": True,
            },
            "privacy": {
                "tag": "local_only",
            },
            "ui_layout": "ui_layout.json",
        }
        config_path = agent_dir / "config.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

        # 写入提示词 (如果模板中没有 prompt.txt 或用户提供了自定义)
        prompt_path = agent_dir / "prompt.txt"
        if not prompt_path.exists() or system_prompt:
            prompt_content = system_prompt if system_prompt else (
                f"# {name}\n\n"
                f"## 人格设定\n\n"
                f"你是「{name}」——{description or '一个智能助手'}。\n\n"
                f"## 对话风格\n\n"
                f"- 简洁直接，不绕弯子\n"
                f"- 专业但不学究\n"
                f"- 友好自然\n\n"
                f"## 语言\n\n"
                f"- 默认使用中文回复\n"
            )
            prompt_path.write_text(prompt_content, encoding="utf-8")

        # 写入默认 UI 布局 (如果模板中没有)
        ui_path = agent_dir / "ui_layout.json"
        if not ui_path.exists():
            ui_layout = {
                "agent_id": agent_id,
                "panels": [
                    {
                        "id": "chat",
                        "module": "chat_view",
                        "x": 0, "y": 0, "w": 12, "h": 10,
                    }
                ],
            }
            with open(ui_path, "w", encoding="utf-8") as f:
                json.dump(ui_layout, f, ensure_ascii=False, indent=2)

        print(f"[Lifecycle] Agent 已创建: {agent_id} (目录: {agent_dir})")
        return {"agent_id": agent_id, "name": name, "path": str(agent_dir)}

    def delete_agent(self, agent_id: str) -> dict:
        """
        删除 Agent — 删除整个目录
        watchdog 检测到目录消失后自动注销
        """
        agent_dir = Path(settings.agents_dir) / agent_id
        if not agent_dir.exists():
            raise ValueError(f"Agent 不存在: {agent_id}")

        shutil.rmtree(agent_dir)
        print(f"[Lifecycle] Agent 已删除: {agent_id}")
        return {"agent_id": agent_id, "deleted": True}

    def export_agent(self, agent_id: str) -> dict:
        """导出 Agent 为 JSON (可分享给其他用户导入)"""
        agent_dir = Path(settings.agents_dir) / agent_id
        if not agent_dir.exists():
            raise ValueError(f"Agent 不存在: {agent_id}")

        export_data = {
            "agent_id": agent_id,
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "config": None,
            "prompt": "",
            "ui_layout": None,
        }

        # 读取配置
        config_path = agent_dir / "config.yaml"
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                export_data["config"] = yaml.safe_load(f)

        # 读取提示词
        prompt_path = agent_dir / "prompt.txt"
        if prompt_path.exists():
            export_data["prompt"] = prompt_path.read_text(encoding="utf-8")

        # 读取 UI 布局
        ui_path = agent_dir / "ui_layout.json"
        if ui_path.exists():
            with open(ui_path, "r", encoding="utf-8") as f:
                export_data["ui_layout"] = json.load(f)

        return export_data

    def import_agent(self, export_data: dict, new_id: Optional[str] = None) -> dict:
        """从导出的 JSON 导入 Agent"""
        agent_id = new_id or export_data.get("agent_id", f"imported_{int(time.time())}")

        config = export_data.get("config", {})
        self.create_agent(
            agent_id=agent_id,
            name=config.get("name", agent_id),
            description=config.get("description", ""),
            system_prompt=export_data.get("prompt", ""),
            role_pool=config.get("role_pool"),
        )

        # 覆盖 UI 布局
        if export_data.get("ui_layout"):
            ui_path = Path(settings.agents_dir) / agent_id / "ui_layout.json"
            with open(ui_path, "w", encoding="utf-8") as f:
                json.dump(export_data["ui_layout"], f, ensure_ascii=False, indent=2)

        print(f"[Lifecycle] Agent 已导入: {agent_id}")
        return {"agent_id": agent_id, "imported": True}

    def _create_skeleton(self, agent_dir: Path):
        """创建空 Agent 骨架目录结构"""
        (agent_dir / "memory").mkdir(parents=True, exist_ok=True)
        (agent_dir / "knowledge" / "raw_files").mkdir(parents=True, exist_ok=True)
        (agent_dir / "tools").mkdir(parents=True, exist_ok=True)
        (agent_dir / "capabilities").mkdir(parents=True, exist_ok=True)


# 全局生命周期管理器单例
agent_lifecycle = AgentLifecycle()