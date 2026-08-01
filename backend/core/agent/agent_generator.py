"""
Agent 生成器 — 调用 LLM 根据自然语言描述生成 Agent 配置

核心流程:
    1. 构造 Prompt (含角色池 + 用户描述)
    2. 调用 LLM 生成 config.yaml 和 prompt.txt
    3. Pydantic 校验 + 补充默认值
    4. 通过 AgentLifecycle 创建 Agent 目录
"""
import json
import uuid
import yaml
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from config.settings import settings
from core.llm.gateway import llm_gateway
from core.agent.agent_schemas import (
    AgentConfig,
    AgentGenerateRequest,
    AgentGenerateResponse,
    get_role_summary,
)
from core.agent.lifecycle import agent_lifecycle


# ===== Agent 生成 Prompt 模板 =====

AGENT_GEN_PROMPT = """你是一个 AI Agent 配置专家。根据用户的需求描述，为一个多角色协作的 AI Agent 平台生成配置。

## 可用角色池

系统有 15 个预定义角色，Agent 的 role_pool 决定了它能调度哪些角色:

{role_summary}

## 角色选择原则

- 选择与用户需求直接相关的角色，不要贪多
- 只写作用 = 选 writer + quality_checker
- 只写代码 = 选 coach + developer + inspector + tester
- 只做翻译 = 选 translator
- 全能助手 = 选全部 15 个角色
- master 是必须的（调度中心），其他角色按需选择

## 工具开关

- web_search: 需要联网搜索时开启
- file_read: 需要读取文件时开启
- file_write: 需要写入文件时开启
- code_exec: 需要执行代码时开启（仅开发类 Agent）

## 输出格式

请严格输出一个 JSON 对象（不要输出 markdown 代码块，不要输出其他内容）:

{{
  "agent_id": "英文小写标识符",
  "name": "中文名称",
  "description": "功能描述",
  "personality": {{
    "tone": "语气风格",
    "expertise": "专业领域",
    "behavior": "行为模式"
  }},
  "role_pool": ["master", "..."],
  "tools": {{
    "web_search": false,
    "file_read": true,
    "file_write": false,
    "code_exec": false
  }},
  "prompt": "完整的系统提示词，包含人格设定、对话风格、行为原则、语言偏好"
}}

## 提示词 (prompt) 编写规范

prompt 字段必须包含完整、结构化的系统提示词，使用 Markdown 格式，包含以下部分:

1. ## 人格设定 — 一句话定义角色身份
2. ## 对话风格 — 3-4 条风格要点
3. ## 行为原则 — 4-6 条行为准则
4. ## 语言 — 默认语言和切换规则

## 示例

用户需求: "一个英文翻译助手，帮我翻各种文档"

输出:
{{
  "agent_id": "en_translator",
  "name": "英文翻译助手",
  "description": "专业中英文翻译，支持文档、邮件、对话等多种格式的翻译",
  "personality": {{
    "tone": "准确、高效、简洁",
    "expertise": "中英文翻译与本地化",
    "behavior": "接收原文，快速准确翻译，必要时提供翻译说明"
  }},
  "role_pool": ["master", "translator", "quality_checker"],
  "tools": {{
    "web_search": false,
    "file_read": true,
    "file_write": false,
    "code_exec": false
  }},
  "prompt": "# 英文翻译助手\\n\\n## 人格设定\\n\\n你是「英文翻译助手」——一个专业的中英文翻译专家。你以准确、高效、简洁的方式提供翻译服务。\\n\\n## 对话风格\\n\\n- 快速准确：接收原文后立即给出翻译，不拖泥带水\\n- 适度说明：翻译中有歧义或文化差异时简要说明\\n- 格式保留：保持原文的段落、标题、列表等格式\\n- 专业术语准确：使用准确的术语翻译，不确定时标注\\n\\n## 行为原则\\n\\n- 用户发送原文，直接返回翻译，不需要确认\\n- 翻译质量第一，宁可多花时间确保准确\\n- 遇到专业术语不确定时，提供多个可能的翻译并标注\\n- 默认为中译英和英译中，其他语言对询问用户\\n- 保留原文的格式结构（段落、标题、列表等）\\n\\n## 语言\\n\\n- 默认使用中文回复\\n- 翻译文本时保持目标语言一致性"
}}"""


class AgentGenerator:
    """Agent 生成器 — LLM 驱动的配置生成"""

    def __init__(self):
        self.agents_dir = Path(settings.agents_dir)

    async def generate(self, req: AgentGenerateRequest) -> AgentGenerateResponse:
        """
        用自然语言生成 Agent 配置并创建 Agent

        :param req: Agent 生成请求（含描述和可选的模板名/agent_id）
        :return: AgentGenerateResponse
        """
        # 1. 检查 LLM 可用性
        if not llm_gateway.available:
            return AgentGenerateResponse(
                success=False,
                error="LLM 推理引擎未就绪，请检查 llama-server 是否已启动",
            )

        # 2. 构造 Prompt
        role_summary = get_role_summary()
        prompt = AGENT_GEN_PROMPT.format(role_summary=role_summary)

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"用户需求: {req.description}"},
        ]

        # 3. 调用 LLM
        try:
            result = await llm_gateway.chat(messages, temperature=0.3)
            raw_output = result["content"]
        except Exception as e:
            return AgentGenerateResponse(
                success=False,
                error=f"LLM 调用失败: {e}",
            )

        # 4. 解析 JSON
        parsed = self._extract_json(raw_output)
        if parsed is None:
            return AgentGenerateResponse(
                success=False,
                error="LLM 输出无法解析为 JSON",
                raw_output=raw_output[:500],
            )

        # 5. 提取 prompt 字段（从 JSON 中分离）
        prompt_text = parsed.pop("prompt", "")

        # 6. 补充 agent_id（用户指定或自动生成）
        if req.agent_id:
            parsed["agent_id"] = req.agent_id
        elif "agent_id" not in parsed or not parsed["agent_id"]:
            # 从 name 推断 agent_id
            name = parsed.get("name", "custom_agent")
            parsed["agent_id"] = self._name_to_id(name)

        # 确保 agent_id 唯一
        parsed["agent_id"] = self._ensure_unique_id(parsed["agent_id"])

        # 7. 补充 memory 默认值
        parsed.setdefault("memory", {"max_history": 50, "long_term_enabled": True})

        # 8. Pydantic 校验
        try:
            config = AgentConfig(**parsed)
        except ValidationError as e:
            return AgentGenerateResponse(
                success=False,
                error=f"配置校验失败: {e}",
                raw_output=raw_output[:500],
            )

        # 9. 通过 AgentLifecycle 创建 Agent
        try:
            # 将 Pydantic 模型转为 dict
            config_dict = config.model_dump()

            # 调用 lifecycle 创建 Agent 目录
            lifecycle_result = agent_lifecycle.create_agent(
                agent_id=config_dict["agent_id"],
                name=config_dict["name"],
                description=config_dict["description"],
                system_prompt=prompt_text,  # LLM 生成的提示词
                role_pool=config_dict["role_pool"],
                template=req.template_name,
            )

            # 10. 覆盖 config.yaml（用 LLM 生成的完整配置）
            config_path = self.agents_dir / config_dict["agent_id"] / "config.yaml"
            self._write_config_yaml(config_path, config_dict)

            print(
                f"[AgentGenerator] Agent 已生成: {config_dict['agent_id']} "
                f"({config_dict['name']}) — 角色池: {len(config_dict['role_pool'])} 个角色"
            )

            return AgentGenerateResponse(
                success=True,
                agent={
                    "agent_id": config_dict["agent_id"],
                    "name": config_dict["name"],
                    "description": config_dict["description"],
                    "personality": config_dict["personality"],
                    "role_pool": config_dict["role_pool"],
                    "tools": config_dict["tools"],
                    "path": lifecycle_result.get("path", ""),
                },
            )

        except ValueError as e:
            return AgentGenerateResponse(
                success=False,
                error=f"Agent 创建失败: {e}",
            )

    # ------------------------------------------------------------------ #
    # 工具方法
    # ------------------------------------------------------------------ #

    def _name_to_id(self, name: str) -> str:
        """将中文名称转换为英文 agent_id"""
        # 简单映射常用词
        mapping = {
            "写作": "writer",
            "翻译": "translator",
            "代码": "coder",
            "开发": "developer",
            "设计": "designer",
            "日程": "scheduler",
            "邮件": "email",
            "办公": "office",
            "生活": "life",
            "知识": "knowledge",
            "行业": "industry",
            "通用": "general",
            "助手": "assistant",
            "专家": "expert",
            "管家": "manager",
            "顾问": "consultant",
            "教练": "coach",
            "伙伴": "companion",
        }
        aid = name
        for cn, en in mapping.items():
            aid = aid.replace(cn, en)
        # 如果还有中文，用拼音首字母
        if any('\u4e00' <= c <= '\u9fff' for c in aid):
            aid = f"custom_{uuid.uuid4().hex[:6]}"
        # 清理特殊字符
        aid = aid.lower().replace(" ", "_").replace("-", "_")
        return aid

    def _ensure_unique_id(self, agent_id: str) -> str:
        """确保 agent_id 唯一（已存在时追加后缀）"""
        base_id = agent_id
        counter = 1
        while (self.agents_dir / agent_id).exists():
            agent_id = f"{base_id}_{counter}"
            counter += 1
        return agent_id

    def _write_config_yaml(self, config_path: Path, config_dict: dict):
        """将 Agent 配置写入 config.yaml（去除不适合写入的字段）"""
        # 只保留标准 config.yaml 字段
        clean_config = {
            "agent_id": config_dict.get("agent_id"),
            "name": config_dict.get("name"),
            "description": config_dict.get("description", ""),
            "personality": config_dict.get("personality", {}),
            "role_pool": config_dict.get("role_pool", []),
            "tools": config_dict.get("tools", {}),
            "memory": config_dict.get("memory", {}),
            "privacy": config_dict.get("privacy", {}),
            "ui_layout": config_dict.get("ui_layout", "ui_layout.json"),
        }
        # 可选扩展字段
        for ext in ["knowledge", "email", "industry", "role"]:
            if ext in config_dict and config_dict[ext]:
                clean_config[ext] = config_dict[ext]

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(clean_config, f, allow_unicode=True, default_flow_style=False)

    def _extract_json(self, text: str) -> Optional[dict]:
        """从 LLM 输出中提取 JSON (容错处理)"""
        text = text.strip()

        # 去除 markdown 代码块标记
        if text.startswith("```"):
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


# 全局 Agent 生成器单例
agent_generator = AgentGenerator()