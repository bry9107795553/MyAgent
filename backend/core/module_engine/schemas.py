"""
模块配置 Schema — Pydantic 模型定义

所有模块配置都通过这些模型校验，确保 LLM 输出的 JSON 格式正确。
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional, Literal
from enum import Enum


# ===== 枚举定义 =====

class TemplateType(str, Enum):
    """31 种模板类型"""
    # 内容记录 (4)
    CATEGORY_NOTES_CRUD = "category_notes_crud"
    MARKDOWN_EDITOR = "markdown_editor"
    CHAT_HISTORY_SEARCH = "chat_history_search"
    BOOKMARK_COLLECTION = "bookmark_collection"
    # 任务管理 (3)
    KANBAN_TASK = "kanban_task"
    TIMER_POMODORO = "timer_pomodoro"
    CALENDAR_SCHEDULE = "calendar_schedule"
    # 数据展示 (3)
    DATA_DASHBOARD = "data_dashboard"
    MEMORY_DASHBOARD = "memory_dashboard"
    TIMELINE_BROWSE = "timeline_browse"
    # 内容消费 (4)
    EMBEDDED_BROWSER = "embedded_browser"
    IMAGE_VIEWER = "image_viewer"
    TRANSLATION_PANEL = "translation_panel"
    BILINGUAL_COMPARE = "bilingual_compare"
    # 创作辅助 (3)
    DUAL_COLUMN_COMPARE = "dual_column_compare"
    MATERIAL_COLLAGE = "material_collage"
    VERSION_HISTORY = "version_history"
    # 系统工具 (4)
    TERMINAL_PANEL = "terminal_panel"
    GLOBAL_SEARCH = "global_search"
    QUICK_LAUNCHER = "quick_launcher"
    FILE_BROWSER = "file_browser"
    # 代码开发 (4)
    CODE_EDITOR = "code_editor"
    CODE_SNIPPET_MANAGER = "code_snippet_manager"
    GIT_DIFF = "git_diff"
    API_TESTER = "api_tester"
    # 设计 (3)
    CANVAS_WHITEBOARD = "canvas_whiteboard"
    COLOR_PALETTE = "color_palette"
    PROTOTYPE_PREVIEW = "prototype_preview"
    # 对话 (3)
    CHAT_VIEW = "chat_view"
    TREE_OUTLINE = "tree_outline"
    FORM_PANEL = "form_panel"


class LayoutType(str, Enum):
    """布局类型"""
    SINGLE_COLUMN = "single_column"
    SIDEBAR_LIST = "sidebar_list"
    TABBED = "tabbed"
    SPLIT_HORIZONTAL = "split_horizontal"
    SPLIT_VERTICAL = "split_vertical"


class DataSourceType(str, Enum):
    """数据源类型"""
    LOCAL_STORAGE = "local_storage"
    SESSION_CONTEXT = "session_context"
    AGENT_CONTEXT = "agent_context"


class FieldType(str, Enum):
    """字段类型"""
    STRING = "string"
    TEXT = "text"
    MARKDOWN = "markdown"
    NUMBER = "number"
    DATETIME = "datetime"
    ENUM = "enum"
    BOOLEAN = "boolean"
    IMAGE = "image"
    URL = "url"
    TAGS = "tags"
    CODE = "code"
    JSON = "json"


# ===== 模型定义 =====

class FieldDef(BaseModel):
    """字段定义"""
    name: str = Field(..., description="字段标识符 (英文)")
    type: FieldType = Field(..., description="字段类型")
    label: str = Field(..., description="显示名称")
    required: bool = Field(False, description="是否必填")
    default: Optional[str] = Field(None, description="默认值")
    options: Optional[list[str]] = Field(None, description="枚举选项 (type=enum 时使用)")
    placeholder: Optional[str] = Field(None, description="输入提示")


class ModuleConfig(BaseModel):
    """模块配置 — 完整的模块定义"""
    module_id: str = Field(..., description="唯一模块 ID")
    template: str = Field(..., description="模板类型")
    name: str = Field(..., description="模块名称")
    description: str = Field("", description="模块描述")
    fields: list[FieldDef] = Field(default_factory=list, description="字段定义列表")
    layout: str = Field("single_column", description="布局类型")
    data_source: str = Field("local_storage", description="数据源类型")
    default_size: dict = Field(
        default_factory=lambda: {"w": 6, "h": 8},
        description="默认网格大小",
    )
    created_by_agent: Optional[str] = Field(None, description="创建者 Agent ID")
    icon: Optional[str] = Field(None, description="模块图标名称")
    category: Optional[str] = Field(None, description="模块分类")

    @field_validator("template")
    @classmethod
    def validate_template(cls, v: str) -> str:
        """校验模板类型是否有效"""
        valid_templates = {t.value for t in TemplateType}
        if v not in valid_templates:
            raise ValueError(
                f"无效的模板类型: {v}。可用模板: {', '.join(sorted(valid_templates))}"
            )
        return v

    @field_validator("layout")
    @classmethod
    def validate_layout(cls, v: str) -> str:
        """校验布局类型是否有效"""
        valid_layouts = {l.value for l in LayoutType}
        if v not in valid_layouts:
            raise ValueError(
                f"无效的布局类型: {v}。可用布局: {', '.join(sorted(valid_layouts))}"
            )
        return v

    @field_validator("data_source")
    @classmethod
    def validate_data_source(cls, v: str) -> str:
        """校验数据源类型是否有效"""
        valid_sources = {d.value for d in DataSourceType}
        if v not in valid_sources:
            raise ValueError(
                f"无效的数据源: {v}。可用数据源: {', '.join(sorted(valid_sources))}"
            )
        return v

    @field_validator("default_size")
    @classmethod
    def validate_size(cls, v: dict) -> dict:
        """校验默认大小"""
        if "w" not in v or "h" not in v:
            return {"w": 6, "h": 8}
        v["w"] = max(1, min(12, int(v["w"])))
        v["h"] = max(1, min(20, int(v["h"])))
        return v


class ModuleSummary(BaseModel):
    """模块摘要 (列表展示用)"""
    module_id: str
    name: str
    template: str
    layout: str
    category: Optional[str] = None
    description: str = ""
