"""
文件操作工具 — 读取、写入、列目录
- FileReadTool: 读取文件内容 (支持指定编码与大小限制)
- FileWriteTool: 写入文件内容 (限制在项目根目录内，防止越权写入)
- FileListTool: 列出目录下的文件与子目录

所有相对路径基于项目根目录 (settings.project_root) 解析。
FileListTool 复用 file_read 配置开关 (同为只读操作)。
"""
from pathlib import Path
from typing import Optional
import os

from config.settings import settings
from core.tools.base import BaseTool


# ===== 路径安全工具函数 =====

def _resolve_path(path: str) -> Path:
    """将路径解析为绝对路径 (相对路径基于项目根目录)

    使用 os.path.normpath 进行语法规范化 (处理 . 和 .. 组件)，
    不调用 Path.resolve() 以避免在含符号链接/联接的路径上产生异常行为。
    """
    p = Path(path)
    if not p.is_absolute():
        p = Path(settings.project_root) / p
    return Path(os.path.normpath(str(p)))


def _is_within_project(path: Path) -> bool:
    """检查路径是否在项目根目录内 (防止目录穿越攻击)"""
    try:
        project_root = _resolve_path(".")
        norm_path = Path(os.path.normpath(str(path)))
        norm_path.relative_to(project_root)
        return True
    except ValueError:
        return False


# ===== 文件读取工具 =====

class FileReadTool(BaseTool):
    """读取文件内容工具"""

    # 默认最大读取大小 (1 MB)
    DEFAULT_MAX_BYTES = 1024 * 1024

    @property
    def name(self) -> str:
        return "file_read"

    @property
    def description(self) -> str:
        return (
            "读取指定文件的内容。支持文本文件，可指定编码和最大读取字节数。"
            "相对路径基于项目根目录解析。"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径 (相对路径基于项目根目录，也可使用绝对路径)",
                },
                "encoding": {
                    "type": "string",
                    "description": "文件编码，默认 utf-8",
                    "default": "utf-8",
                },
                "max_bytes": {
                    "type": "integer",
                    "description": f"最大读取字节数，默认 {self.DEFAULT_MAX_BYTES}",
                    "default": self.DEFAULT_MAX_BYTES,
                },
            },
            "required": ["path"],
        }

    async def execute(
        self,
        path: str,
        encoding: str = "utf-8",
        max_bytes: Optional[int] = None,
    ) -> dict:
        """读取文件内容"""
        limit = max_bytes or self.DEFAULT_MAX_BYTES
        file_path = _resolve_path(path)

        try:
            # 获取文件信息 (stat 可能在含符号链接的路径上失败，需容错)
            try:
                file_size = file_path.stat().st_size
            except OSError:
                file_size = 0  # stat 失败时跳过大小说检查，直接尝试读取

            # 检查文件大小
            if file_size > limit:
                return {
                    "success": False,
                    "error": f"文件过大: {file_size} 字节，超过限制 {limit} 字节",
                    "file_size": file_size,
                    "limit": limit,
                }

            content = file_path.read_text(encoding=encoding)
            return {
                "success": True,
                "path": str(file_path),
                "content": content,
                "size": file_size if file_size else len(content.encode(encoding)),
                "encoding": encoding,
            }
        except FileNotFoundError:
            return {"success": False, "error": f"文件不存在: {path}"}
        except IsADirectoryError:
            return {"success": False, "error": f"路径是目录而非文件: {path}"}
        except UnicodeDecodeError:
            return {
                "success": False,
                "error": f"编码错误，无法以 {encoding} 解码文件: {path}",
                "hint": "该文件可能是二进制文件，请确认编码后重试",
            }
        except Exception as e:
            return {"success": False, "error": f"读取文件失败: {e}"}


# ===== 文件写入工具 =====

class FileWriteTool(BaseTool):
    """写入文件内容工具"""

    @property
    def name(self) -> str:
        return "file_write"

    @property
    def description(self) -> str:
        return (
            "将内容写入指定文件。如果文件所在目录不存在会自动创建。"
            "出于安全考虑，仅允许写入项目根目录内的文件。"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "文件路径 (相对路径基于项目根目录)",
                },
                "content": {
                    "type": "string",
                    "description": "要写入的文件内容",
                },
                "encoding": {
                    "type": "string",
                    "description": "文件编码，默认 utf-8",
                    "default": "utf-8",
                },
                "append": {
                    "type": "boolean",
                    "description": "是否追加写入 (False 为覆盖，默认 False)",
                    "default": False,
                },
            },
            "required": ["path", "content"],
        }

    async def execute(
        self,
        path: str,
        content: str,
        encoding: str = "utf-8",
        append: bool = False,
    ) -> dict:
        """写入文件内容"""
        file_path = _resolve_path(path)

        # 安全检查：仅允许写入项目根目录内的文件
        if not _is_within_project(file_path):
            return {
                "success": False,
                "error": f"安全限制：仅允许写入项目根目录内的文件: {path}",
            }

        try:
            # 自动创建父目录
            file_path.parent.mkdir(parents=True, exist_ok=True)

            mode = "a" if append else "w"
            with open(file_path, mode, encoding=encoding) as f:
                f.write(content)

            written_bytes = len(content.encode(encoding))
            return {
                "success": True,
                "path": str(file_path),
                "bytes_written": written_bytes,
                "mode": "append" if append else "overwrite",
            }
        except Exception as e:
            return {"success": False, "error": f"写入文件失败: {e}"}


# ===== 目录列举工具 =====

class FileListTool(BaseTool):
    """列出目录下的文件与子目录"""

    @property
    def name(self) -> str:
        return "file_list"

    @property
    def config_key(self) -> str:
        # 列目录属于只读操作，复用 file_read 配置开关
        return "file_read"

    @property
    def description(self) -> str:
        return (
            "列出指定目录下的文件和子目录。返回每个条目的名称、类型和大小。"
            "相对路径基于项目根目录解析。"
        )

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "目录路径 (相对路径基于项目根目录，默认为项目根目录)",
                    "default": ".",
                },
                "pattern": {
                    "type": "string",
                    "description": "文件名匹配模式 (Unix shell 风格通配符，如 *.py)，默认匹配所有",
                    "default": "*",
                },
            },
            "required": [],
        }

    async def execute(
        self,
        path: str = ".",
        pattern: str = "*",
    ) -> dict:
        """列出目录内容"""
        dir_path = _resolve_path(path)

        try:
            entries = []
            for entry in sorted(dir_path.iterdir(), key=lambda e: e.name):
                # 应用通配符过滤
                if not entry.match(pattern) and pattern != "*":
                    continue

                # 获取条目大小 (stat 可能在含符号链接的路径上失败，需容错)
                try:
                    size = entry.stat().st_size
                except OSError:
                    size = 0

                # 判断条目类型 (is_dir 同样可能失败，需容错)
                try:
                    is_dir = entry.is_dir()
                except OSError:
                    is_dir = False

                entries.append({
                    "name": entry.name,
                    "type": "directory" if is_dir else "file",
                    "size": size,
                })

            return {
                "success": True,
                "path": str(dir_path),
                "entries": entries,
                "count": len(entries),
            }
        except FileNotFoundError:
            return {"success": False, "error": f"目录不存在: {path}"}
        except NotADirectoryError:
            return {"success": False, "error": f"路径不是目录: {path}"}
        except Exception as e:
            return {"success": False, "error": f"列目录失败: {e}"}
