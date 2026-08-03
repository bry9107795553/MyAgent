"""
模型管理 API 路由 — 模型列表、切换、当前状态
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.llm.gateway import llm_gateway

router = APIRouter(prefix="/api/models", tags=["models"])


class SwitchModelRequest(BaseModel):
    profile_id: str


@router.get("")
async def list_models():
    """列出所有可用模型"""
    return {
        "models": llm_gateway.list_models(),
        "current": llm_gateway.get_current_model(),
    }


@router.get("/current")
async def get_current_model():
    """获取当前使用的模型"""
    return llm_gateway.get_current_model()


@router.post("/switch")
async def switch_model(req: SwitchModelRequest):
    """切换模型"""
    success = llm_gateway.switch_model(req.profile_id)
    if not success:
        raise HTTPException(
            status_code=404,
            detail=f"模型配置不存在: {req.profile_id}",
        )
    return {
        "success": True,
        "current": llm_gateway.get_current_model(),
    }