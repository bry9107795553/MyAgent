"""
Agent 配置 Schema — Pydantic 模型定义

所有 Agent 配置都通过这些模型校验，确保 LLM 输出的 JSON 格式正确。
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from enum import Enum


# ===== 枚举定义 =====

class ToolName(str, Enum):
    """支持的 Agent 工具"""
    WEB_SEARCH = "web_search"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    CODE_EXEC = "code_exec"


class PrivacyTag(str, Enum):
    """隐私标签"""
    LOCAL_ONLY = "local_only"
    CLOUD_ALLOWED = "cloud_allowed"


# ===== 子模型 =====

class AgentPersonality(BaseModel):
    """Agent 人格设定"""
    tone: str = Field(
        "专业、友好",
        description="语气风格 (如: 简洁专业、温暖鼓励、严谨准确)"
    )
    expertise: str = Field(
        "通用助手",
        description="专业领域 (如: 代码开发、写作编辑、知识问答)"
    )
    behavior: str = Field(
        "根据用户需求提供帮助",
        description="行为模式 (如: 主动提问引导、直接给出答案)"
    )


class AgentTools(BaseModel):
    """Agent 工具开关"""
    web_search: bool = Field(False, description="联网搜索")
    file_read: bool = Field(True, description="文件读取")
    file_write: bool = Field(False, description="文件写入")
    code_exec: bool = Field(False, description="代码执行")


class AgentMemory(BaseModel):
    """Agent 记忆配置"""
    max_history: int = Field(50, ge=10, le=500, description="最大对话轮次")
    long_term_enabled: bool = Field(True, description="是否启用长期记忆")


class AgentPrivacy(BaseModel):
    """Agent 隐私配置"""
    tag: PrivacyTag = Field(PrivacyTag.LOCAL_ONLY, description="隐私标签")


# ===== 主模型 =====

class AgentConfig(BaseModel):
    """Agent 完整配置 — 对应 config.yaml"""
    agent_id: str = Field(..., description="唯一标识符 (英文，小写，用下划线连接)")
    name: str = Field(..., description="Agent 显示名称 (中文)")
    description: str = Field("", description="Agent 功能描述")
    personality: AgentPersonality = Field(
        default_factory=AgentPersonality,
        description="人格设定"
    )
    role_pool: list[str] = Field(
        default_factory=lambda: ["master", "knowledge_retriever", "writer", "quality_checker"],
        description="可用角色池 (角色 ID 列表)"
    )
    tools: AgentTools = Field(
        default_factory=AgentTools,
        description="工具开关"
    )
    memory: AgentMemory = Field(
        default_factory=AgentMemory,
        description="记忆配置"
    )
    privacy: AgentPrivacy = Field(
        default_factory=AgentPrivacy,
        description="隐私配置"
    )
    ui_layout: str = Field("ui_layout.json", description="UI 布局文件名")

    # 可选扩展字段 (特定模板使用)
    knowledge: Optional[dict] = Field(None, description="知识库配置 (knowledge_qa 模板)")
    email: Optional[dict] = Field(None, description="邮件工具配置 (schedule_email 模板)")
    industry: Optional[str] = Field(None, description="行业领域 (industry_service 模板)")
    role: Optional[str] = Field(None, description="服务角色 (industry_service 模板)")

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        """校验 agent_id 格式: 仅小写字母、数字、下划线"""
        import re
        if not re.match(r"^[a-z][a-z0-9_]*$", v):
            raise ValueError(
                f"agent_id 必须以小写字母开头，只能包含小写字母、数字和下划线，收到: {v}"
            )
        return v

    @field_validator("role_pool")
    @classmethod
    def validate_role_pool(cls, v: list[str]) -> list[str]:
        """校验角色池不为空，且包含 master"""
        if not v:
            raise ValueError("role_pool 不能为空")
        if "master" not in v:
            # 自动添加 master
            v = ["master"] + v
        return v


# ===== 请求/响应模型 =====

class AgentGenerateRequest(BaseModel):
    """Agent 生成请求"""
    description: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="用户对 Agent 的自然语言描述 (如: '一个专业写作助手，帮我写报告和文章，写完后要检查质量')"
    )
    template_name: str = Field(
        "default",
        description="参考模板名称 (可选，为空则从描述中推断)"
    )
    agent_id: Optional[str] = Field(
        None,
        description="指定 agent_id (可选，为空则自动生成)"
    )


class AgentGenerateResponse(BaseModel):
    """Agent 生成响应"""
    success: bool
    agent: Optional[dict] = None
    error: Optional[str] = None
    raw_output: Optional[str] = None


# ===== 可用角色列表 (供 LLM prompt 使用) =====

AVAILABLE_ROLES = [
    {
        "id": "master",
        "name": "主控",
        "group": "通用",
        "description": "前台接待+调度中心，接需求/分发/收结果/报进度/防火墙",
        "capabilities": ["调度", "防火墙", "汇总", "进度报告"],
    },
    {
        "id": "coach",
        "name": "教练",
        "group": "开发",
        "description": "产品教练+导师，需求发现三步走/教学/认知适配/调度开发团队",
        "capabilities": ["需求发现", "竞品调研", "教学", "认知适配"],
    },
    {
        "id": "knowledge_retriever",
        "name": "知识检索",
        "group": "通用",
        "description": "RAG+联网搜索，资料收集/多源搜索/文档解析",
        "capabilities": ["知识检索", "联网搜索", "文档解析", "来源验证"],
    },
    {
        "id": "writer",
        "name": "写作",
        "group": "通用",
        "description": "报告/邮件/文案写作，风格记忆/初稿/修改",
        "capabilities": ["报告写作", "邮件起草", "文案创作", "风格适配"],
    },
    {
        "id": "quality_checker",
        "name": "质检",
        "group": "通用",
        "description": "事实核查+逻辑验证，只检查不修改内容",
        "capabilities": ["事实核查", "逻辑验证", "质量评分"],
    },
    {
        "id": "scheduler",
        "name": "日程",
        "group": "通用",
        "description": "时间管理+冲突检测，安排日程/提醒/时间规划",
        "capabilities": ["日程管理", "冲突检测", "时间规划"],
    },
    {
        "id": "creative",
        "name": "创意",
        "group": "通用",
        "description": "头脑风暴+洞察提炼，创意策划/方案构思",
        "capabilities": ["头脑风暴", "洞察提炼", "创意策划"],
    },
    {
        "id": "translator",
        "name": "翻译",
        "group": "通用",
        "description": "多语言翻译，中英/英中/多语种互译",
        "capabilities": ["翻译", "本地化"],
    },
    {
        "id": "visual_analyzer",
        "name": "视觉分析",
        "group": "通用",
        "description": "图片分析（多模态），截图解读/图表分析",
        "capabilities": ["图片分析", "截图解读", "图表分析"],
    },
    {
        "id": "designer",
        "name": "设计师",
        "group": "开发",
        "description": "设计系统+页面样图，UI设计/组件库/响应式",
        "capabilities": ["设计系统", "页面样图", "组件库", "响应式"],
    },
    {
        "id": "developer",
        "name": "开发",
        "group": "开发",
        "description": "代码实现+技术债管理，模块实现/返工修复",
        "capabilities": ["代码实现", "技术债管理", "模块开发"],
    },
    {
        "id": "inspector",
        "name": "巡检",
        "group": "开发",
        "description": "架构审查+代码规范检查，14项工业标准核查",
        "capabilities": ["架构审查", "代码规范", "技术债识别"],
    },
    {
        "id": "tester",
        "name": "测试",
        "group": "开发",
        "description": "tsc/eslint/vitest检查，自动化测试",
        "capabilities": ["单元测试", "编译检查", "Lint检查"],
    },
    {
        "id": "deployer",
        "name": "部署",
        "group": "开发",
        "description": "构建+部署+回滚，打包上线",
        "capabilities": ["构建", "部署", "回滚"],
    },
    {
        "id": "cleaner",
        "name": "清洁员",
        "group": "后勤",
        "description": "文件系统清理，垃圾文件/临时文件/重复资源",
        "capabilities": ["垃圾清理", "文件检测", "安全清理"],
    },
]

# 供 prompt 使用的角色摘要文本
def get_role_summary() -> str:
    """生成角色池摘要文本 (供 LLM prompt 使用)"""
    lines = []
    for r in AVAILABLE_ROLES:
        lines.append(
            f"  - {r['id']} ({r['name']}, {r['group']}组): {r['description']}"
        )
    return "\n".join(lines)