"""
System overview API — comprehensive system status for frontend dashboard.
"""
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query

from core.role.loader import role_loader
from core.llm.gateway import llm_gateway
from config.settings import settings

router = APIRouter(prefix="/api/system", tags=["system"])

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
SAFE_ROOTS = [PROJECT_ROOT, PROJECT_ROOT / "data" / "projects", PROJECT_ROOT / "data"]


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


# ── 产物文件 API ──
import os
from pathlib import Path
from fastapi.responses import PlainTextResponse

OUTPUTS_DIR = Path("data/outputs")

@router.get("/outputs")
async def list_outputs():
    """列出 data/outputs/ 下的所有产物文件"""
    outputs = []
    if OUTPUTS_DIR.exists():
        for f in sorted(OUTPUTS_DIR.iterdir(), key=lambda f: f.stat().st_mtime, reverse=True):
            if f.is_file():
                size = f.stat().st_size
                size_str = f"{size / 1024:.1f}KB" if size > 1024 else f"{size}B"
                outputs.append({
                    "name": f.name,
                    "ext": f.suffix,
                    "size": size_str,
                    "mtime": f.stat().st_mtime,
                })
    return outputs

@router.get("/outputs/{filename:path}", response_class=PlainTextResponse)
async def read_output(filename: str):
    """读取单个产物文件的内容"""
    target = OUTPUTS_DIR / filename
    if not target.exists():
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="文件不存在")
    return target.read_text(encoding="utf-8", errors="replace")


# ---- 文件阅览 API ----
READABLE_EXTS = {".md",".txt",".json",".yaml",".yml",".xml",".html",".css",
                 ".js",".ts",".vue",".py",".sh",".csv",".toml",".cfg",".ini",
                 ".env",".svg",".rst",".sql",".Dockerfile",""}

@router.get("/read")
async def read_file(path: str = Query("")):
    """浏览项目文件：目录列表或文件内容"""
    target = (PROJECT_ROOT / path).resolve()
    # 安全检查
    safe = any(str(target).startswith(str(r.resolve())) for r in SAFE_ROOTS)
    if not safe:
        raise HTTPException(status_code=403, detail="路径不允许")
    if not target.exists():
        return {"files": [], "error": "不存在"}

    if target.is_dir():
        files = []
        for child in sorted(target.iterdir()):
            if child.name.startswith('.') and child.name not in ['.gitignore','.env']:
                continue
            try:
                st = child.stat()
                files.append({"name": child.name, "is_dir": child.is_dir(),
                              "size": st.st_size if child.is_file() else 0})
            except:
                pass
        return {"files": files}
    else:
        ext = target.suffix.lower()
        if ext not in READABLE_EXTS and target.stat().st_size < 1024*1024:
            pass  # try anyway if small
        elif target.stat().st_size > 2*1024*1024:
            return {"content": f"[{target.stat().st_size/1024/1024:.1f}MB — 文件太大，无法预览]", "error": "too_large"}
        try:
            content = target.read_text(encoding='utf-8', errors='replace')
            return {"content": content}
        except:
            return {"content": "[不可读取的二进制文件]", "error": "binary"}
