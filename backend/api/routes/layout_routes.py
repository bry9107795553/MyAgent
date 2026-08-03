"""
工作台布局 API — 保存/加载用户的面板编排

路由:
    GET  /api/layout              — 获取当前布局
    POST /api/layout              — 保存布局 (覆盖)
    GET  /api/layout/list         — 列出所有已保存布局
    POST /api/layout/{name}       — 另存为指定名称
    DELETE /api/layout/{name}     — 删除指定布局
"""
import json
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from config.settings import settings

router = APIRouter(prefix="/api/layout", tags=["layout"])

# 布局存储目录
LAYOUTS_DIR = Path(settings.data_dir) / "layouts"


def _ensure_dir():
    """确保布局目录存在"""
    LAYOUTS_DIR.mkdir(parents=True, exist_ok=True)


class SaveLayoutRequest(BaseModel):
    """保存布局请求"""
    modules: list[dict]          # 模块列表 (含 module_id, x, y, w, h)
    name: str = "default"        # 布局名称


@router.get("")
async def get_current_layout():
    """获取当前 (default) 布局"""
    _ensure_dir()
    layout_file = LAYOUTS_DIR / "default.json"
    if layout_file.exists():
        with open(layout_file, "r", encoding="utf-8") as f:
            return json.load(f)
    # 返回空布局
    return {"name": "default", "modules": []}


@router.post("")
async def save_layout(req: SaveLayoutRequest):
    """保存布局 (覆盖 default)"""
    _ensure_dir()
    layout_data = {
        "name": req.name,
        "modules": req.modules,
    }
    layout_file = LAYOUTS_DIR / f"{req.name}.json"
    with open(layout_file, "w", encoding="utf-8") as f:
        json.dump(layout_data, f, ensure_ascii=False, indent=2)
    return {"saved": True, "name": req.name, "module_count": len(req.modules)}


@router.get("/list")
async def list_layouts():
    """列出所有已保存布局"""
    _ensure_dir()
    layouts = []
    for f in LAYOUTS_DIR.glob("*.json"):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            layouts.append({
                "name": data.get("name", f.stem),
                "module_count": len(data.get("modules", [])),
            })
        except (json.JSONDecodeError, KeyError):
            continue
    return {"layouts": layouts}


@router.post("/{name}")
async def save_layout_as(name: str, req: SaveLayoutRequest):
    """另存为指定名称的布局"""
    _ensure_dir()
    layout_data = {
        "name": name,
        "modules": req.modules,
    }
    layout_file = LAYOUTS_DIR / f"{name}.json"
    with open(layout_file, "w", encoding="utf-8") as f:
        json.dump(layout_data, f, ensure_ascii=False, indent=2)
    return {"saved": True, "name": name, "module_count": len(req.modules)}


@router.delete("/{name}")
async def delete_layout(name: str):
    """删除指定布局"""
    layout_file = LAYOUTS_DIR / f"{name}.json"
    if not layout_file.exists():
        raise HTTPException(status_code=404, detail=f"布局不存在: {name}")
    layout_file.unlink()
    return {"deleted": name}
