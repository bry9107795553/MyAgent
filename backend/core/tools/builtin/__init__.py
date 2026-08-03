"""
内置工具集 — 文件操作、搜索、代码执行
导入本模块即自动将所有内置工具注册到全局 tool_registry

内置工具清单:
    - file_read:   FileReadTool   读取文件内容
    - file_write:  FileWriteTool  写入文件内容
    - file_list:   FileListTool   列出目录文件
    - web_search:  WebSearchTool  网页搜索 (占位)
    - code_exec:   CodeExecTool   执行 Python 代码
"""
from core.tools.base import tool_registry
from core.tools.builtin.file_tools import FileReadTool, FileWriteTool, FileListTool
from core.tools.builtin.search_tools import WebSearchTool
from core.tools.builtin.code_tools import CodeExecTool

# 将所有内置工具注册到全局注册表
tool_registry.register(FileReadTool())
tool_registry.register(FileWriteTool())
tool_registry.register(FileListTool())
tool_registry.register(WebSearchTool())
tool_registry.register(CodeExecTool())

__all__ = [
    "FileReadTool",
    "FileWriteTool",
    "FileListTool",
    "WebSearchTool",
    "CodeExecTool",
]
