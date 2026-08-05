"""
System overview API — comprehensive system status for frontend dashboard.
"""
from fastapi import APIRouter

from core.role.loader import role_loader
from core.llm.gateway import llm_gateway
from config.settings import settings

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("")
async def system_overview():
    """Returns comprehensive system status: roles, workgroups, GPU, model."""
    master = role_loader.master

    # Role pool data
    role_pool_data = role_loader._role_pool_data
    roles = role_pool_data.get("roles", [])

    # Role categories for grouping
    categories = {}
    for r in roles:
        group = r.get("group", "general")
        categories.setdefault(group, []).append({
            "id": r["id"],
            "name": r.get("name", r["id"]),
            "gpu_affinity": r.get("gpu_affinity", ""),
            "model": r.get("model", "text"),
            "capabilities": r.get("capabilities", []),
            "description": r.get("description", ""),
        })

    # Workgroup summary
    workgroups = []
    if master and hasattr(master, "_workgroups"):
        for wg_id, wg in master._workgroups.items():
            workgroups.append({
                "id": wg_id,
                "name": wg.get("name", wg_id),
                "description": wg.get("description", ""),
                "trigger_keywords": wg.get("trigger_keywords", []),
                "members": wg.get("members", []),
                "pipeline_steps": len(wg.get("pipeline", [])),
            })

    # GPU / Model status
    gpu_info = {
        "mode": "single_gpu" if settings.single_gpu_mode else "multi_gpu",
        "model": settings.llama_model,
        "endpoint": str(settings.resolve_inference_url("gpu0")),
        "llm_available": llm_gateway.available,
        "routing": settings.describe_gpu_routing(),
    }

    return {
        "status": "ok",
        "roles": roles,
        "categories": categories,
        "workgroups": workgroups,
        "role_count": len(roles),
        "workgroup_count": len(workgroups),
        "gpu": gpu_info,
    }
