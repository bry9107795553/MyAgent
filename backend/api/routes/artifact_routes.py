"""
产物 (Artifact) API 路由 — 项目交付物浏览、预览、下载
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import os
import mimetypes

from config.settings import settings

router = APIRouter(prefix="/api/projects", tags=["artifacts"])

# 产物文件扩展名 → 类型映射
EXT_TYPE_MAP = {
    ".html": "代码", ".css": "代码", ".js": "代码", ".ts": "代码",
    ".py": "代码", ".json": "代码", ".yaml": "代码", ".yml": "代码",
    ".vue": "代码", ".jsx": "代码", ".tsx": "代码",
    ".png": "图片", ".jpg": "图片", ".jpeg": "图片", ".gif": "图片",
    ".webp": "图片", ".svg": "图片", ".ico": "图片",
    ".md": "文档", ".txt": "文档", ".pdf": "文档",
    ".docx": "文档", ".pptx": "文档",
}


def _get_outputs_dir(project_name: str) -> Path:
    """获取项目产物目录"""
    return Path(settings.data_dir) / "projects" / project_name / "outputs"


def _get_artifact_type(filename: str) -> str:
    """根据文件扩展名获取产物类型"""
    ext = Path(filename).suffix.lower()
    return EXT_TYPE_MAP.get(ext, "其他")


def _is_text_file(filename: str) -> bool:
    """判断是否为文本文件（可预览）"""
    ext = Path(filename).suffix.lower()
    return ext in {".html", ".css", ".js", ".ts", ".py", ".json", ".yaml",
                   ".yml", ".vue", ".jsx", ".tsx", ".md", ".txt", ".svg"}


@router.get("/{project_name}/artifacts")
async def list_artifacts(project_name: str):
    """列出项目的所有产物文件"""
    outputs_dir = _get_outputs_dir(project_name)
    if not outputs_dir.exists():
        return {"project": project_name, "artifacts": []}

    artifacts = []
    for root, dirs, files in os.walk(outputs_dir):
        for f in files:
            file_path = Path(root) / f
            rel_path = str(file_path.relative_to(outputs_dir))
            stat = file_path.stat()
            artifacts.append({
                "id": rel_path.replace("\\", "/"),
                "name": f,
                "path": rel_path.replace("\\", "/"),
                "type": _get_artifact_type(f),
                "size": stat.st_size,
                "previewable": _is_text_file(f),
                "modified": stat.st_mtime,
            })

    # 按修改时间降序
    artifacts.sort(key=lambda x: x["modified"], reverse=True)
    return {"project": project_name, "artifacts": artifacts}


@router.get("/{project_name}/artifacts/{artifact_id}/preview")
async def preview_artifact(project_name: str, artifact_id: str):
    """预览产物内容（文本文件）"""
    outputs_dir = _get_outputs_dir(project_name)
    file_path = outputs_dir / artifact_id

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="产物文件不存在")

    if not _is_text_file(file_path.name):
        raise HTTPException(status_code=400, detail="此文件类型不支持预览")

    try:
        content = file_path.read_text(encoding="utf-8")
        return {
            "project": project_name,
            "artifact": artifact_id,
            "name": file_path.name,
            "type": _get_artifact_type(file_path.name),
            "content": content,
        }
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="文件编码不支持预览")


@router.get("/{project_name}/artifacts/{artifact_id}/download")
async def download_artifact(project_name: str, artifact_id: str):
    """下载产物文件"""
    outputs_dir = _get_outputs_dir(project_name)
    file_path = outputs_dir / artifact_id

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="产物文件不存在")

    mime_type, _ = mimetypes.guess_type(str(file_path))
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type=mime_type or "application/octet-stream",
    )