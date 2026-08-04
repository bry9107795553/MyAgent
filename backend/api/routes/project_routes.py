"""
项目状态 API 路由 — 跨会话项目进度追踪

路由:
    GET  /api/projects                  — 列出所有活跃项目
    GET  /api/projects/{project_name}   — 获取项目状态详情
    POST /api/projects/{project_name}/phase — 更新项目阶段
    POST /api/projects/{project_name}/module — 新增模块
    POST /api/projects/{project_name}/module/complete — 模块标记完成
    POST /api/projects/{project_name}/module/start — 模块标记开始
    POST /api/projects/{project_name}/tech-debt — 新增技术债
    POST /api/projects/{project_name}/blockers — 设置阻塞项
    POST /api/projects/{project_name}/touch — 刷新活跃时间
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.project.project_status import project_status
from core.role.loader import role_loader

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ===== 请求模型 =====

class UpdatePhaseRequest(BaseModel):
    phase: str
    active_agent: str = ""


class ModuleRequest(BaseModel):
    module_name: str
    note: str = ""
    active_agent: str = ""


class TechDebtRequest(BaseModel):
    debt_item: str
    active_agent: str = ""


class BlockersRequest(BaseModel):
    blockers: list[str]
    active_agent: str = ""


class TouchRequest(BaseModel):
    active_agent: str = ""


# ===== 辅助函数 =====

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
async def list_projects():
    """列出所有有 PROJECT_STATUS.md 的活跃项目"""
    return {"projects": project_status.list_projects()}


@router.get("/{project_name}")
async def get_project(project_name: str):
    """获取项目完整状态快照"""
    master = _get_master()
    status = master.get_project_status(project_name)
    if not status:
        raise HTTPException(status_code=404, detail=f"项目不存在或状态文件缺失: {project_name}")
    return status


@router.post("/{project_name}/phase")
async def update_phase(project_name: str, req: UpdatePhaseRequest):
    """更新项目当前阶段"""
    ok = project_status.update_phase(project_name, req.phase, req.active_agent)
    if not ok:
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_name}")
    return {"updated": project_name, "phase": req.phase}


@router.post("/{project_name}/module")
async def add_module(project_name: str, req: ModuleRequest):
    """新增模块到待完成列表"""
    ok = project_status.add_module(
        project_name, req.module_name,
        status="pending", note=req.note, active_agent=req.active_agent,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_name}")
    return {"added": project_name, "module": req.module_name}


@router.post("/{project_name}/module/complete")
async def complete_module(project_name: str, req: ModuleRequest):
    """将模块标记为已完成 (进行中 → 已完成)"""
    ok = project_status.mark_module_complete(
        project_name, req.module_name, req.active_agent,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_name}")
    return {"completed": project_name, "module": req.module_name}


@router.post("/{project_name}/module/start")
async def start_module(project_name: str, req: ModuleRequest):
    """将模块标记为进行中 (待完成 → 进行中)"""
    ok = project_status.mark_module_in_progress(
        project_name, req.module_name,
        note=req.note, active_agent=req.active_agent,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_name}")
    return {"started": project_name, "module": req.module_name}


@router.post("/{project_name}/tech-debt")
async def add_tech_debt(project_name: str, req: TechDebtRequest):
    """新增技术债条目"""
    ok = project_status.add_tech_debt(
        project_name, req.debt_item, req.active_agent,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_name}")
    return {"added": project_name, "debt": req.debt_item}


@router.post("/{project_name}/blockers")
async def set_blockers(project_name: str, req: BlockersRequest):
    """设置阻塞项 (替换全部)"""
    ok = project_status.set_blockers(
        project_name, req.blockers, req.active_agent,
    )
    if not ok:
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_name}")
    return {"updated": project_name, "blockers": req.blockers}


@router.post("/{project_name}/touch")
async def touch_project(project_name: str, req: TouchRequest = None):
    """刷新项目活跃时间 (会话结束时调用)"""
    active_agent = req.active_agent if req else ""
    ok = project_status.touch(project_name, active_agent)
    if not ok:
        raise HTTPException(status_code=404, detail=f"项目不存在: {project_name}")
    return {"touched": project_name}