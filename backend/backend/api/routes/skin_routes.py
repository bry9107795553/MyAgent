"""
皮肤系统 API 路由 — 列表、应用、生成、取色

路由:
    GET  /api/skins              — 列出所有皮肤 (预置 + 用户自定义)
    GET  /api/skins/current      — 获取当前生效皮肤
    GET  /api/skins/{skin_id}    — 获取皮肤完整 JSON
    POST /api/skins/apply        — 应用皮肤 (写入当前偏好)
    POST /api/skins/generate     — AI 生成皮肤 (调用 LLM)
    POST /api/skins/extract-colors — 从图片提取主色调方案
"""
import os
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File
from pydantic import BaseModel

from core.skin import skin_manager

router = APIRouter(prefix="/api/skins", tags=["skins"])


class ApplySkinRequest(BaseModel):
    skin_id: str


class GenerateSkinRequest(BaseModel):
    prompt: str


@router.get("")
async def list_skins():
    """获取所有皮肤 (预置 + 用户自定义)"""
    return {"skins": skin_manager.list_skins()}


@router.get("/current")
async def get_current_skin():
    """获取当前生效皮肤 (偏好 ID + 完整配置)"""
    return skin_manager.get_current_skin()


@router.get("/{skin_id}")
async def get_skin(skin_id: str):
    """获取皮肤完整 JSON"""
    skin = skin_manager.get_skin(skin_id)
    if skin is None:
        raise HTTPException(status_code=404, detail=f"皮肤不存在: {skin_id}")
    return skin


@router.post("/apply")
async def apply_skin(req: ApplySkinRequest):
    """应用皮肤 — 写入当前偏好 (前端读取后注入 CSS 变量)"""
    if not skin_manager.apply_skin(req.skin_id):
        raise HTTPException(status_code=404, detail=f"皮肤不存在: {req.skin_id}")
    return {"applied": req.skin_id}


@router.post("/generate")
async def generate_skin(req: GenerateSkinRequest):
    """AI 生成皮肤 — 调用 LLM 生成 CSS 变量方案"""
    result = await skin_manager.generate_skin(req.prompt)
    if not result["success"]:
        raise HTTPException(
            status_code=400,
            detail=result.get("error", "皮肤生成失败"),
        )
    return result


@router.post("/extract-colors")
async def extract_colors(file: UploadFile = File(...)):
    """从上传图片提取主色调方案 (Pillow + sklearn KMeans)"""
    # 校验是否为图片
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"}:
        raise HTTPException(
            status_code=400,
            detail="仅支持 png/jpg/jpeg/webp/gif/bmp 格式图片",
        )

    # 写入临时文件后交给管理器处理
    tmp_path = None
    try:
        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="上传文件为空")

        fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(content)

        result = skin_manager.extract_colors_from_image(tmp_path)
        if not result["success"]:
            raise HTTPException(
                status_code=400,
                detail=result.get("error", "色彩提取失败"),
            )
        return {"colors": result["colors"]}
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.remove(tmp_path)
