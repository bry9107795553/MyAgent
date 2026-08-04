"""
Workgroup 管理 API — 预设工作组的 CRUD 和手动触发

路由:
    GET    /api/workgroups            — 列出所有工作组
    GET    /api/workgroups/{wg_id}    — 获取工作组详情
    POST   /api/workgroups            — 创建新工作组
    PUT    /api/workgroups/{wg_id}    — 更新工作组
    DELETE /api/workgroups/{wg_id}    — 删除工作组
    POST   /api/workgroups/{wg_id}/trigger — 手动触发工作组执行
"""
import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.role.loader import role_loader

router = APIRouter(prefix="/api/workgroups", tags=["workgroups"])

# ===== 工作组目录 =====

WORKGROUPS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "data" / "workgroups"
)


# ===== 请求/响应模型 =====

class PipelineStep(BaseModel):
    step: int
    role: str
    action: str
    input_from: str = "user"
    output_to: str = ""
    parallel_with: list[str] = []
    condition: str = ""


class WorkgroupConditions(BaseModel):
    max_revisions: int = 3
    user_confirmation_points: list[str] = []
    exit_criteria: str = ""


class GpuPlan(BaseModel):
    parallel_capable: bool = False
    note: str = ""


class CreateWorkgroupRequest(BaseModel):
    id: str
    name: str
    description: str = ""
    trigger_keywords: list[str] = []
    trigger_examples: list[str] = []
    members: list[str] = []
    pipeline: list[PipelineStep] = []
    conditions: Optional[WorkgroupConditions] = None
    gpu_plan: Optional[GpuPlan] = None


class TriggerRequest(BaseModel):
    message: str
    agent_id: str = "default"


# ===== 辅助函数 =====

def _ensure_dir():
    """确保工作组目录存在"""
    WORKGROUPS_DIR.mkdir(parents=True, exist_ok=True)


def _load_workgroup(wg_id: str) -> Optional[dict]:
    """从文件加载单个工作组配置"""
    wg_file = WORKGROUPS_DIR / f"{wg_id}.json"
    if not wg_file.exists():
        return None
    with open(wg_file, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_workgroup(wg: dict):
    """保存工作组配置到文件"""
    _ensure_dir()
    wg_id = wg["id"]
    wg_file = WORKGROUPS_DIR / f"{wg_id}.json"
    with open(wg_file, "w", encoding="utf-8") as f:
        json.dump(wg, f, ensure_ascii=False, indent=2)


def _list_workgroups() -> list[dict]:
    """列出所有工作组（摘要信息）"""
    _ensure_dir()
    results = []
    for wg_file in sorted(WORKGROUPS_DIR.glob("*.json")):
        try:
            with open(wg_file, "r", encoding="utf-8") as f:
                wg = json.load(f)
            results.append({
                "id": wg.get("id", wg_file.stem),
                "name": wg.get("name", ""),
                "description": wg.get("description", ""),
                "trigger_keywords": wg.get("trigger_keywords", []),
                "members": wg.get("members", []),
                "pipeline_steps": len(wg.get("pipeline", [])),
            })
        except Exception as e:
            print(f"[WorkgroupRoutes] 读取失败 {wg_file.name}: {e}")
    return results


def _get_master():
    """获取主控角色实例"""
    master = role_loader.master
    if not master:
        raise HTTPException(
            status_code=503,
            detail="角色系统未就绪，主控角色未加载",
        )
    return master


# ===== 路由 =====

@router.get("")
async def list_workgroups():
    """列出所有预设工作组（摘要）"""
    return {"workgroups": _list_workgroups()}


@router.get("/{wg_id}")
async def get_workgroup(wg_id: str):
    """获取工作组完整配置"""
    wg = _load_workgroup(wg_id)
    if not wg:
        raise HTTPException(status_code=404, detail=f"工作组不存在: {wg_id}")
    return wg


@router.post("")
async def create_workgroup(req: CreateWorkgroupRequest):
    """创建新工作组"""
    wg_id = req.id

    # 检查是否已存在
    if _load_workgroup(wg_id):
        raise HTTPException(status_code=409, detail=f"工作组已存在: {wg_id}")

    # 验证 pipeline 中的角色是否在角色池中
    master = _get_master()
    for step in req.pipeline:
        if step.role not in master._role_pool:
            raise HTTPException(
                status_code=400,
                detail=f"角色 '{step.role}' 不在角色池中，请先注册该角色",
            )

    # 构建工作组配置
    wg = {
        "id": req.id,
        "name": req.name,
        "description": req.description,
        "trigger_keywords": req.trigger_keywords,
        "trigger_examples": req.trigger_examples,
        "members": req.members,
        "pipeline": [s.model_dump() for s in req.pipeline],
        "conditions": req.conditions.model_dump() if req.conditions else {
            "max_revisions": 3,
            "user_confirmation_points": [],
            "exit_criteria": "",
        },
        "gpu_plan": req.gpu_plan.model_dump() if req.gpu_plan else {
            "parallel_capable": False,
            "note": "",
        },
    }

    _save_workgroup(wg)

    # 重新加载到主控
    master._load_workgroups()

    return {"created": wg_id, "workgroup": wg}


@router.put("/{wg_id}")
async def update_workgroup(wg_id: str, req: CreateWorkgroupRequest):
    """更新工作组配置"""
    existing = _load_workgroup(wg_id)
    if not existing:
        raise HTTPException(status_code=404, detail=f"工作组不存在: {wg_id}")

    master = _get_master()
    for step in req.pipeline:
        if step.role not in master._role_pool:
            raise HTTPException(
                status_code=400,
                detail=f"角色 '{step.role}' 不在角色池中，请先注册该角色",
            )

    wg = {
        "id": req.id if req.id else wg_id,
        "name": req.name,
        "description": req.description,
        "trigger_keywords": req.trigger_keywords,
        "trigger_examples": req.trigger_examples,
        "members": req.members,
        "pipeline": [s.model_dump() for s in req.pipeline],
        "conditions": req.conditions.model_dump() if req.conditions else existing.get("conditions", {}),
        "gpu_plan": req.gpu_plan.model_dump() if req.gpu_plan else existing.get("gpu_plan", {}),
    }

    _save_workgroup(wg)

    # 重新加载到主控
    master._load_workgroups()

    return {"updated": wg_id, "workgroup": wg}


@router.delete("/{wg_id}")
async def delete_workgroup(wg_id: str):
    """删除工作组"""
    wg_file = WORKGROUPS_DIR / f"{wg_id}.json"
    if not wg_file.exists():
        raise HTTPException(status_code=404, detail=f"工作组不存在: {wg_id}")

    wg_file.unlink()

    # 重新加载到主控
    master = _get_master()
    master._load_workgroups()

    return {"deleted": wg_id}


@router.post("/{wg_id}/trigger")
async def trigger_workgroup(wg_id: str, req: TriggerRequest):
    """
    手动触发工作组执行

    通过主控调度指定工作组，按 pipeline 顺序执行各步骤。
    返回完整的执行结果，包括各步骤产出和最终交付。
    """
    master = _get_master()

    # 加载工作组配置
    wg = _load_workgroup(wg_id)
    if not wg:
        raise HTTPException(status_code=404, detail=f"工作组不存在: {wg_id}")

    # 验证 Agent
    from core.agent.registry import agent_registry
    agent = agent_registry.get(req.agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent 不存在: {req.agent_id}")

    # 通过主控执行流水线
    result = await master.execute_workgroup(wg_id, req.message)

    return {
        "workgroup_id": wg_id,
        "workgroup_name": wg.get("name", wg_id),
        "message": req.message,
        **result,
    }