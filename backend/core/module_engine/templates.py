"""
模板注册表 — 31 种模块模板定义

每个模板定义包含:
- template: 模板 ID
- name: 模板名称
- category: 分类
- icon: 图标
- description: 描述
- default_layout: 默认布局
- default_size: 默认网格大小
- default_fields: 默认字段定义
"""
from typing import Any

TEMPLATE_REGISTRY: dict[str, dict[str, Any]] = {
    # ===== 内容记录 (4) =====
    "category_notes_crud": {
        "name": "分类笔记",
        "category": "内容记录",
        "icon": "note",
        "description": "带分类管理的笔记，支持增删改查",
        "default_layout": "sidebar_list",
        "default_size": {"w": 6, "h": 10},
        "default_fields": [
            {"name": "title", "type": "string", "label": "标题", "required": True},
            {"name": "category", "type": "enum", "label": "分类", "options": ["默认", "工作", "学习", "生活"]},
            {"name": "content", "type": "markdown", "label": "内容"},
            {"name": "tags", "type": "tags", "label": "标签"},
            {"name": "created_at", "type": "datetime", "label": "创建时间"},
        ],
    },
    "markdown_editor": {
        "name": "Markdown 编辑器",
        "category": "内容记录",
        "icon": "edit",
        "description": "所见即所得的 Markdown 编辑器，支持实时预览",
        "default_layout": "split_horizontal",
        "default_size": {"w": 12, "h": 10},
        "default_fields": [
            {"name": "title", "type": "string", "label": "标题", "required": True},
            {"name": "content", "type": "markdown", "label": "正文"},
            {"name": "tags", "type": "tags", "label": "标签"},
        ],
    },
    "chat_history_search": {
        "name": "对话历史搜索",
        "category": "内容记录",
        "icon": "search",
        "description": "搜索和浏览历史对话记录",
        "default_layout": "sidebar_list",
        "default_size": {"w": 6, "h": 10},
        "default_fields": [
            {"name": "keyword", "type": "string", "label": "搜索关键词"},
            {"name": "agent_id", "type": "enum", "label": "Agent", "options": ["全部"]},
            {"name": "date_range", "type": "datetime", "label": "时间范围"},
            {"name": "content", "type": "text", "label": "对话内容"},
        ],
    },
    "bookmark_collection": {
        "name": "书签收藏",
        "category": "内容记录",
        "icon": "bookmark",
        "description": "收藏和管理网页链接、资源地址",
        "default_layout": "sidebar_list",
        "default_size": {"w": 4, "h": 8},
        "default_fields": [
            {"name": "title", "type": "string", "label": "标题", "required": True},
            {"name": "url", "type": "url", "label": "链接", "required": True},
            {"name": "category", "type": "enum", "label": "分类", "options": ["工具", "文档", "灵感", "其他"]},
            {"name": "description", "type": "text", "label": "描述"},
        ],
    },

    # ===== 任务管理 (3) =====
    "kanban_task": {
        "name": "看板任务",
        "category": "任务管理",
        "icon": "kanban",
        "description": "看板式任务管理，支持拖拽切换状态",
        "default_layout": "split_horizontal",
        "default_size": {"w": 12, "h": 8},
        "default_fields": [
            {"name": "title", "type": "string", "label": "任务标题", "required": True},
            {"name": "status", "type": "enum", "label": "状态", "options": ["待办", "进行中", "已完成"], "default": "待办"},
            {"name": "priority", "type": "enum", "label": "优先级", "options": ["低", "中", "高"], "default": "中"},
            {"name": "assignee", "type": "string", "label": "负责人"},
            {"name": "due_date", "type": "datetime", "label": "截止日期"},
            {"name": "description", "type": "text", "label": "描述"},
        ],
    },
    "timer_pomodoro": {
        "name": "番茄钟",
        "category": "任务管理",
        "icon": "timer",
        "description": "番茄工作法计时器，专注与休息交替",
        "default_layout": "single_column",
        "default_size": {"w": 3, "h": 6},
        "default_fields": [
            {"name": "work_duration", "type": "number", "label": "工作时长(分钟)", "default": "25"},
            {"name": "break_duration", "type": "number", "label": "休息时长(分钟)", "default": "5"},
            {"name": "cycles", "type": "number", "label": "循环次数", "default": "4"},
            {"name": "task_label", "type": "string", "label": "当前任务"},
        ],
    },
    "calendar_schedule": {
        "name": "日历日程",
        "category": "任务管理",
        "icon": "calendar",
        "description": "日历视图管理日程安排",
        "default_layout": "single_column",
        "default_size": {"w": 8, "h": 10},
        "default_fields": [
            {"name": "title", "type": "string", "label": "日程标题", "required": True},
            {"name": "start_time", "type": "datetime", "label": "开始时间", "required": True},
            {"name": "end_time", "type": "datetime", "label": "结束时间"},
            {"name": "location", "type": "string", "label": "地点"},
            {"name": "reminder", "type": "boolean", "label": "提醒", "default": "true"},
            {"name": "description", "type": "text", "label": "备注"},
        ],
    },

    # ===== 数据展示 (3) =====
    "data_dashboard": {
        "name": "数据仪表盘",
        "category": "数据展示",
        "icon": "dashboard",
        "description": "可视化数据看板，支持图表展示",
        "default_layout": "tabbed",
        "default_size": {"w": 12, "h": 10},
        "default_fields": [
            {"name": "title", "type": "string", "label": "看板标题", "required": True},
            {"name": "chart_type", "type": "enum", "label": "图表类型", "options": ["折线图", "柱状图", "饼图", "表格"]},
            {"name": "data_source", "type": "string", "label": "数据源"},
            {"name": "refresh_interval", "type": "number", "label": "刷新间隔(秒)"},
        ],
    },
    "memory_dashboard": {
        "name": "记忆看板",
        "category": "数据展示",
        "icon": "brain",
        "description": "Agent 记忆系统可视化，查看对话记忆和偏好",
        "default_layout": "tabbed",
        "default_size": {"w": 8, "h": 10},
        "default_fields": [
            {"name": "memory_type", "type": "enum", "label": "记忆类型", "options": ["短期", "长期", "偏好"]},
            {"name": "content", "type": "text", "label": "记忆内容"},
            {"name": "created_at", "type": "datetime", "label": "记录时间"},
            {"name": "importance", "type": "number", "label": "重要程度"},
        ],
    },
    "timeline_browse": {
        "name": "时间线浏览",
        "category": "数据展示",
        "icon": "timeline",
        "description": "按时间线浏览历史活动和事件",
        "default_layout": "single_column",
        "default_size": {"w": 6, "h": 12},
        "default_fields": [
            {"name": "event", "type": "string", "label": "事件", "required": True},
            {"name": "timestamp", "type": "datetime", "label": "时间", "required": True},
            {"name": "category", "type": "enum", "label": "类型", "options": ["对话", "任务", "笔记", "系统"]},
            {"name": "details", "type": "text", "label": "详情"},
        ],
    },

    # ===== 内容消费 (4) =====
    "embedded_browser": {
        "name": "内嵌浏览器",
        "category": "内容消费",
        "icon": "globe",
        "description": "在面板内嵌入网页浏览，支持地址栏导航",
        "default_layout": "single_column",
        "default_size": {"w": 8, "h": 10},
        "default_fields": [
            {"name": "url", "type": "url", "label": "网址", "default": "https://www.google.com"},
            {"name": "title", "type": "string", "label": "页面标题"},
        ],
    },
    "image_viewer": {
        "name": "图片查看器",
        "category": "内容消费",
        "icon": "image",
        "description": "图片浏览和管理，支持缩略图网格",
        "default_layout": "sidebar_list",
        "default_size": {"w": 6, "h": 10},
        "default_fields": [
            {"name": "image_url", "type": "image", "label": "图片", "required": True},
            {"name": "title", "type": "string", "label": "标题"},
            {"name": "album", "type": "enum", "label": "相册", "options": ["默认", "收藏", "素材"]},
        ],
    },
    "translation_panel": {
        "name": "翻译面板",
        "category": "内容消费",
        "icon": "language",
        "description": "文本翻译工具，支持多语言",
        "default_layout": "single_column",
        "default_size": {"w": 5, "h": 8},
        "default_fields": [
            {"name": "source_text", "type": "text", "label": "原文", "required": True},
            {"name": "source_lang", "type": "enum", "label": "源语言", "options": ["自动检测", "中文", "英文", "日文"], "default": "自动检测"},
            {"name": "target_lang", "type": "enum", "label": "目标语言", "options": ["中文", "英文", "日文", "法文"], "default": "英文"},
            {"name": "translated_text", "type": "text", "label": "译文"},
        ],
    },
    "bilingual_compare": {
        "name": "对照翻译",
        "category": "内容消费",
        "icon": "compare",
        "description": "双栏对照阅读原文和译文",
        "default_layout": "split_horizontal",
        "default_size": {"w": 10, "h": 8},
        "default_fields": [
            {"name": "left_text", "type": "text", "label": "左栏文本", "required": True},
            {"name": "right_text", "type": "text", "label": "右栏文本"},
            {"name": "left_label", "type": "string", "label": "左栏标题", "default": "原文"},
            {"name": "right_label", "type": "string", "label": "右栏标题", "default": "译文"},
        ],
    },

    # ===== 创作辅助 (3) =====
    "dual_column_compare": {
        "name": "双栏对比",
        "category": "创作辅助",
        "icon": "columns",
        "description": "双栏内容对比，适合方案比较、文本差异",
        "default_layout": "split_horizontal",
        "default_size": {"w": 12, "h": 8},
        "default_fields": [
            {"name": "left_title", "type": "string", "label": "左栏标题"},
            {"name": "left_content", "type": "markdown", "label": "左栏内容"},
            {"name": "right_title", "type": "string", "label": "右栏标题"},
            {"name": "right_content", "type": "markdown", "label": "右栏内容"},
        ],
    },
    "material_collage": {
        "name": "素材拼贴板",
        "category": "创作辅助",
        "icon": "collage",
        "description": "可视化素材收集板，拖拽排列图片和文字",
        "default_layout": "single_column",
        "default_size": {"w": 10, "h": 10},
        "default_fields": [
            {"name": "title", "type": "string", "label": "画板标题", "required": True},
            {"name": "items", "type": "json", "label": "素材列表"},
        ],
    },
    "version_history": {
        "name": "版本历史",
        "category": "创作辅助",
        "icon": "history",
        "description": "文档版本管理，查看历史版本和差异",
        "default_layout": "sidebar_list",
        "default_size": {"w": 8, "h": 10},
        "default_fields": [
            {"name": "version", "type": "string", "label": "版本号", "required": True},
            {"name": "timestamp", "type": "datetime", "label": "时间"},
            {"name": "author", "type": "string", "label": "作者"},
            {"name": "change_summary", "type": "text", "label": "变更摘要"},
            {"name": "content", "type": "markdown", "label": "内容"},
        ],
    },

    # ===== 系统工具 (4) =====
    "terminal_panel": {
        "name": "终端面板",
        "category": "系统工具",
        "icon": "terminal",
        "description": "嵌入式命令行终端",
        "default_layout": "single_column",
        "default_size": {"w": 8, "h": 8},
        "default_fields": [
            {"name": "shell_type", "type": "enum", "label": "Shell", "options": ["bash", "python", "node"], "default": "bash"},
            {"name": "working_dir", "type": "string", "label": "工作目录", "default": "/app"},
        ],
    },
    "global_search": {
        "name": "全局搜索",
        "category": "系统工具",
        "icon": "search",
        "description": "跨模块、跨 Agent 的全局搜索",
        "default_layout": "single_column",
        "default_size": {"w": 6, "h": 6},
        "default_fields": [
            {"name": "query", "type": "string", "label": "搜索词", "required": True},
            {"name": "scope", "type": "enum", "label": "搜索范围", "options": ["全部", "笔记", "对话", "任务", "文件"], "default": "全部"},
        ],
    },
    "quick_launcher": {
        "name": "快捷启动器",
        "category": "系统工具",
        "icon": "rocket",
        "description": "快速访问常用功能和模块",
        "default_layout": "single_column",
        "default_size": {"w": 3, "h": 8},
        "default_fields": [
            {"name": "name", "type": "string", "label": "名称", "required": True},
            {"name": "action", "type": "string", "label": "动作"},
            {"name": "icon", "type": "string", "label": "图标"},
        ],
    },
    "file_browser": {
        "name": "文件浏览",
        "category": "系统工具",
        "icon": "folder",
        "description": "文件树浏览和管理",
        "default_layout": "sidebar_list",
        "default_size": {"w": 6, "h": 10},
        "default_fields": [
            {"name": "path", "type": "string", "label": "路径", "default": "/app"},
            {"name": "name", "type": "string", "label": "文件名", "required": True},
            {"name": "type", "type": "enum", "label": "类型", "options": ["文件", "目录"]},
            {"name": "size", "type": "number", "label": "大小(KB)"},
            {"name": "modified", "type": "datetime", "label": "修改时间"},
        ],
    },

    # ===== 代码开发 (4) =====
    "code_editor": {
        "name": "代码编辑器",
        "category": "代码开发",
        "icon": "code",
        "description": "语法高亮的代码编辑器",
        "default_layout": "single_column",
        "default_size": {"w": 10, "h": 12},
        "default_fields": [
            {"name": "filename", "type": "string", "label": "文件名", "required": True},
            {"name": "language", "type": "enum", "label": "语言", "options": ["python", "javascript", "typescript", "html", "css", "json", "yaml", "markdown"], "default": "python"},
            {"name": "content", "type": "code", "label": "代码内容"},
        ],
    },
    "code_snippet_manager": {
        "name": "代码片段管理",
        "category": "代码开发",
        "icon": "snippet",
        "description": "收集和管理代码片段，按语言分类",
        "default_layout": "sidebar_list",
        "default_size": {"w": 8, "h": 10},
        "default_fields": [
            {"name": "title", "type": "string", "label": "标题", "required": True},
            {"name": "language", "type": "enum", "label": "语言", "options": ["python", "javascript", "typescript", "go", "rust", "sql"]},
            {"name": "code", "type": "code", "label": "代码"},
            {"name": "tags", "type": "tags", "label": "标签"},
            {"name": "description", "type": "text", "label": "说明"},
        ],
    },
    "git_diff": {
        "name": "Git 差异对比",
        "category": "代码开发",
        "icon": "git",
        "description": "Git 文件差异对比查看器",
        "default_layout": "split_horizontal",
        "default_size": {"w": 12, "h": 10},
        "default_fields": [
            {"name": "file_path", "type": "string", "label": "文件路径", "required": True},
            {"name": "old_version", "type": "code", "label": "旧版本"},
            {"name": "new_version", "type": "code", "label": "新版本"},
            {"name": "diff_type", "type": "enum", "label": "对比方式", "options": ["unified", "split"], "default": "unified"},
        ],
    },
    "api_tester": {
        "name": "API 测试器",
        "category": "代码开发",
        "icon": "api",
        "description": "HTTP API 请求测试工具",
        "default_layout": "split_vertical",
        "default_size": {"w": 8, "h": 10},
        "default_fields": [
            {"name": "method", "type": "enum", "label": "方法", "options": ["GET", "POST", "PUT", "DELETE", "PATCH"], "default": "GET"},
            {"name": "url", "type": "url", "label": "URL", "required": True},
            {"name": "headers", "type": "json", "label": "请求头"},
            {"name": "body", "type": "json", "label": "请求体"},
            {"name": "response", "type": "json", "label": "响应"},
            {"name": "status_code", "type": "number", "label": "状态码"},
        ],
    },

    # ===== 设计 (3) =====
    "canvas_whiteboard": {
        "name": "画板白板",
        "category": "设计",
        "icon": "canvas",
        "description": "自由绘图画板，支持手绘、图形、文字",
        "default_layout": "single_column",
        "default_size": {"w": 12, "h": 12},
        "default_fields": [
            {"name": "title", "type": "string", "label": "画板标题", "required": True},
            {"name": "tool", "type": "enum", "label": "工具", "options": ["画笔", "矩形", "圆形", "文字", "橡皮擦"], "default": "画笔"},
            {"name": "color", "type": "string", "label": "颜色", "default": "#6c5ce7"},
        ],
    },
    "color_palette": {
        "name": "调色板",
        "category": "设计",
        "icon": "palette",
        "description": "颜色选择和调色板管理",
        "default_layout": "single_column",
        "default_size": {"w": 4, "h": 8},
        "default_fields": [
            {"name": "color", "type": "string", "label": "颜色值", "required": True},
            {"name": "name", "type": "string", "label": "颜色名称"},
            {"name": "palette", "type": "enum", "label": "调色板", "options": ["默认", "品牌色", "暖色", "冷色"]},
        ],
    },
    "prototype_preview": {
        "name": "原型预览",
        "category": "设计",
        "icon": "preview",
        "description": "HTML/CSS 原型实时预览",
        "default_layout": "split_horizontal",
        "default_size": {"w": 12, "h": 10},
        "default_fields": [
            {"name": "name", "type": "string", "label": "原型名称", "required": True},
            {"name": "html", "type": "code", "label": "HTML"},
            {"name": "css", "type": "code", "label": "CSS"},
            {"name": "viewport", "type": "enum", "label": "视口", "options": ["桌面", "平板", "手机"], "default": "桌面"},
        ],
    },

    # ===== 对话 (3) =====
    "chat_view": {
        "name": "对话界面",
        "category": "对话",
        "icon": "chat",
        "description": "Agent 对话界面，支持流式输出",
        "default_layout": "single_column",
        "default_size": {"w": 6, "h": 12},
        "default_fields": [
            {"name": "agent_id", "type": "string", "label": "Agent ID", "required": True},
            {"name": "message", "type": "text", "label": "消息内容"},
        ],
    },
    "tree_outline": {
        "name": "树形大纲",
        "category": "对话",
        "icon": "tree",
        "description": "可折叠的树形大纲视图",
        "default_layout": "single_column",
        "default_size": {"w": 5, "h": 10},
        "default_fields": [
            {"name": "title", "type": "string", "label": "节点标题", "required": True},
            {"name": "level", "type": "number", "label": "层级", "default": "0"},
            {"name": "content", "type": "text", "label": "内容"},
            {"name": "expanded", "type": "boolean", "label": "展开", "default": "true"},
        ],
    },
    "form_panel": {
        "name": "表单面板",
        "category": "对话",
        "icon": "form",
        "description": "通用表单输入面板",
        "default_layout": "single_column",
        "default_size": {"w": 4, "h": 8},
        "default_fields": [
            {"name": "title", "type": "string", "label": "表单标题", "required": True},
            {"name": "fields", "type": "json", "label": "表单字段定义"},
        ],
    },
}


def get_template(template_id: str) -> dict | None:
    """获取模板定义"""
    return TEMPLATE_REGISTRY.get(template_id)


def list_templates() -> list[dict]:
    """列出所有模板 (摘要信息)"""
    return [
        {
            "template": tid,
            "name": t["name"],
            "category": t["category"],
            "icon": t["icon"],
            "description": t["description"],
            "default_layout": t["default_layout"],
            "default_size": t["default_size"],
        }
        for tid, t in TEMPLATE_REGISTRY.items()
    ]


def list_categories() -> list[str]:
    """列出所有分类"""
    return sorted(set(t["category"] for t in TEMPLATE_REGISTRY.values()))
