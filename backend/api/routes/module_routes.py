"""
模块生成引擎 API — 用户用自然语言描述需求，系统生成模块 JSON 配置

路由:
    POST /api/modules/generate  — 生成模块
    GET  /api/modules           — 列出所有模块
    GET  /api/modules/{id}      — 获取模块详情
    DELETE /api/modules/{id}    — 删除模块
    GET  /api/modules/templates — 列出所有可用模板
    GET  /api/modules/categories — 列出所有分类
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.module_engine import module_generator
from core.module_engine.templates import list_templates, list_categories, get_template

router = APIRouter(prefix="/api/modules", tags=["modules"])


class GenerateModuleRequest(BaseModel):
    description: str           # 用户的自然语言描述
    agent_id: str = "default"  # 关联的 Agent


@router.post("/generate")
async def generate_module(req: GenerateModuleRequest):
    """用自然语言生成模块配置"""
    result = await module_generator.generate(req.description, req.agent_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "生成失败"))
    return result


@router.get("")
async def list_modules():
    """列出所有已生成的模块"""
    return {"modules": module_generator.list_modules()}


@router.post("")
async def create_module(req: dict):
    """
    直接从模板创建模块 (不走 LLM 生成)，用于工作台一键添加默认模块
    :param req: {name, description, template, config, x?, y?, w?, h?}
    """
    template = req.get("template")
    if not template:
        raise HTTPException(status_code=400, detail="缺少 template 字段")
    # 从模板生成基础配置
    from core.module_engine.templates import get_template
    tpl = get_template(template)
    if not tpl:
        raise HTTPException(status_code=404, detail=f"模板不存在: {template}")

    module = module_generator.create_from_template(
        template_id=template,
        name=req.get("name", tpl.get("name", template)),
        description=req.get("description", tpl.get("description", "")),
        config=req.get("config", {}),
        position=req.get("position"),  # {x, y, w, h}
    )
    return {"module": module}


@router.get("/templates")
async def get_templates():
    """列出所有可用模板"""
    return {"templates": list_templates(), "categories": list_categories()}


@router.get("/categories")
async def get_categories():
    """列出所有分类"""
    return {"categories": list_categories()}


@router.get("/{module_id}")
async def get_module(module_id: str):
    """获取模块完整配置"""
    module = module_generator.get_module(module_id)
    if not module:
        raise HTTPException(status_code=404, detail=f"模块不存在: {module_id}")
    return module


@router.delete("/{module_id}")
async def delete_module(module_id: str):
    """删除模块"""
    if module_generator.delete_module(module_id):
        return {"deleted": module_id}
    raise HTTPException(status_code=404, detail=f"模块不存在: {module_id}")
