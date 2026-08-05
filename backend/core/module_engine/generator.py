"""
模块生成器 — 调用 LLM 生成模块配置，Pydantic 校验后保存

核心流程:
    1. 构造 Prompt (含模板列表 + 用户描述)
    2. 调用 LLM 生成 JSON
    3. Pydantic 校验 + 补充默认值
    4. 保存到 data/modules/
"""
import json
import uuid
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from config.settings import settings
from core.llm.gateway import llm_gateway
from core.module_engine.schemas import ModuleConfig, FieldDef
from core.module_engine.templates import TEMPLATE_REGISTRY, get_template


# 模块生成 Prompt 模板
MODULE_GEN_PROMPT = """你是一个 UI 模块设计专家。根据用户的需求描述，生成一个 JSON 模块配置。

可用的模板类型 (template 字段):
{templates}

可用布局类型 (layout 字段):
- single_column: 单栏
- sidebar_list: 左侧列表 + 右侧详情
- tabbed: 标签页
- split_horizontal: 水平分栏
- split_vertical: 垂直分栏

可用数据源 (data_source 字段):
- local_storage: 本地存储
- session_context: 会话上下文
- agent_context: Agent 上下文

可用字段类型 (fields 中的 type):
- string, text, markdown, number, datetime, enum, boolean, image, url, tags, code, json

请严格输出以下 JSON 格式 (不要输出其他内容，不要 markdown 代码块):
{{
  "template": "模板类型",
  "name": "模块名称",
  "description": "模块描述",
  "fields": [
    {{"name": "字段名(英文)", "type": "类型", "label": "显示名", "required": false}}
  ],
  "layout": "布局类型",
  "data_source": "数据源",
  "default_size": {{"w": 6, "h": 8}}
}}

注意:
- name 和 description 使用中文
- fields 中的 name 使用英文标识符
- enum 类型的字段需要包含 options 数组
- default_size 的 w 范围 1-12, h 范围 1-20
"""


class ModuleGenerator:
    """模块生成器 — LLM 驱动的配置生成"""

    def __init__(self):
        self.modules_dir = Path(settings.data_dir) / "modules"
        self.modules_dir.mkdir(parents=True, exist_ok=True)

    async def generate(
        self,
        description: str,
        agent_id: str = "default",
    ) -> dict:
        """
        用自然语言生成模块配置

        :param description: 用户的自然语言描述
        :param agent_id: 关联的 Agent ID
        :return: {"success": bool, "module": dict, "error": str}
        """
        if not llm_gateway.available:
            return {
                "success": False,
                "error": "LLM 推理引擎未就绪，请检查 llama-server 是否已启动",
            }

        # 构造模板列表文本
        template_list = "\n".join(
            f"- {tid}: {t['name']} ({t['category']}) — {t['description']}"
            for tid, t in TEMPLATE_REGISTRY.items()
        )
        prompt = MODULE_GEN_PROMPT.format(templates=template_list)

        # 调用 LLM
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"用户需求: {description}"},
        ]

        try:
            result = await llm_gateway.chat(messages, temperature=0.3)
            raw_output = result["content"]
        except Exception as e:
            return {"success": False, "error": f"LLM 调用失败: {e}"}

        # 解析 JSON
        parsed = self._extract_json(raw_output)
        if parsed is None:
            return {
                "success": False,
                "error": "LLM 输出无法解析为 JSON",
                "raw_output": raw_output[:500],
            }

        # 补充生成信息
        module_id = f"mod_{uuid.uuid4().hex[:8]}"
        parsed["module_id"] = module_id
        parsed["created_by_agent"] = agent_id

        # 补充模板默认值
        template_def = get_template(parsed.get("template", ""))
        if template_def:
            parsed.setdefault("category", template_def.get("category"))
            parsed.setdefault("icon", template_def.get("icon"))
            if "default_size" not in parsed:
                parsed["default_size"] = template_def.get("default_size", {"w": 6, "h": 8})

        # Pydantic 校验
        try:
            config = ModuleConfig(**parsed)
        except ValidationError as e:
            return {
                "success": False,
                "error": f"配置校验失败: {e}",
                "raw_output": raw_output[:500],
            }

        # 保存
        save_path = self.modules_dir / f"{module_id}.json"
        config_dict = config.model_dump()
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, ensure_ascii=False, indent=2)

        print(f"[ModuleEngine] 模块已生成: {module_id} ({config.name})")
        return {"success": True, "module": config_dict}

    def list_modules(self) -> list[dict]:
        """列出所有已生成的模块"""
        modules = []
        for mod_file in self.modules_dir.glob("*.json"):
            try:
                with open(mod_file, "r", encoding="utf-8") as f:
                    mod = json.load(f)
                    modules.append({
                        "module_id": mod.get("module_id"),
                        "name": mod.get("name"),
                        "template": mod.get("template"),
                        "layout": mod.get("layout"),
                        "category": mod.get("category"),
                        "description": mod.get("description", ""),
                    })
            except (json.JSONDecodeError, KeyError):
                continue
        return modules

    def create_from_template(
        self,
        template_id: str,
        name: str,
        description: str,
        config: dict,
        position: dict = None,
    ) -> dict:
        """
        从模板直接创建模块 (不走 LLM)
        用于工作台一键添加默认模块的场景
        """
        from core.module_engine.templates import get_template
        tpl = get_template(template_id)
        if not tpl:
            return {"error": f"模板不存在: {template_id}"}

        module_id = generate_id("mod")
        now = now_iso()
        pos = position or {}

        module = {
            "module_id": module_id,
            "name": name or tpl.get("name", template_id),
            "description": description or tpl.get("description", ""),
            "template": template_id,
            "category": tpl.get("category", "其他"),
            "icon": tpl.get("icon", "note"),
            "config": config or {},
            "layout": {
                "x": pos.get("x", 0),
                "y": pos.get("y", 0),
                "w": pos.get("w", tpl.get("default_size", {}).get("w", 6)),
                "h": pos.get("h", tpl.get("default_size", {}).get("h", 8)),
            },
            "default_size": tpl.get("default_size", {"w": 6, "h": 8}),
            "created_at": now,
            "updated_at": now,
        }

        # 持久化
        save_path = self.modules_dir / f"{module_id}.json"
        self.modules_dir.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(module, f, ensure_ascii=False, indent=2)

        return module

    def get_module(self, module_id: str) -> Optional[dict]:
        """获取单个模块配置"""
        mod_path = self.modules_dir / f"{module_id}.json"
        if not mod_path.exists():
            return None
        with open(mod_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def delete_module(self, module_id: str) -> bool:
        """删除模块"""
        mod_path = self.modules_dir / f"{module_id}.json"
        if mod_path.exists():
            mod_path.unlink()
            return True
        return False

    def _extract_json(self, text: str) -> Optional[dict]:
        """从 LLM 输出中提取 JSON (容错处理)"""
        text = text.strip()

        # 去除 markdown 代码块标记
        if text.startswith("```"):
            # 去掉第一行 (```json 或 ```)
            lines = text.split("\n")
            text = "\n".join(lines[1:])
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取第一个 JSON 对象
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        return None
