"""
MyAgent — 主入口
FastAPI 应用，注册所有路由，初始化核心组件

启动方式:
    cd backend
    uvicorn main:app --host 0.0.0.0 --port 8080 --reload
"""
from contextlib import asynccontextmanager
from pathlib import Path
import asyncio

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from core.llm.gateway import llm_gateway
from core.agent.registry import agent_registry
from core.role.loader import role_loader
from core.bus import message_bus

from api.routes import (
    agent_routes, skin_routes, module_routes, layout_routes,
    workgroup_routes, project_routes, model_routes, artifact_routes,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期 — 启动时初始化，关闭时清理"""
    print("=" * 60)
    print(f"  {settings.app_name} 启动中...")
    print("=" * 60)

    # 1. 初始化 LLM 网关 (连接 llama.cpp + 加载模型配置)
    print("\n[1/4] 初始化 LLM 网关...")
    await llm_gateway.init()

    # 2. 初始化 Agent 注册表 (扫描目录 + 启动 watchdog)
    print("\n[2/4] 初始化 Agent 注册表...")
    loop = asyncio.get_event_loop()
    await agent_registry.init(loop)

    # 3. 初始化角色系统 (加载 role_pool.json → 创建角色实例)
    print("\n[3/4] 初始化角色系统...")
    try:
        master = role_loader.load_all()
        # 将主控绑定到已注册的 Agent
        for agent_id, agent in agent_registry._agents.items():
            agent.bind_master(master)
        print(f"  ✓ 角色系统就绪: {role_loader.role_count} 个角色")
        print(f"  ✓ 主控已绑定到 {len(agent_registry._agents)} 个 Agent")
    except Exception as e:
        print(f"  ⚠ 角色系统加载失败 (将使用过渡模式): {e}")
        master = None

    # 4. 确保数据目录存在
    print("\n[4/4] 检查数据目录...")
    Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.agents_dir).mkdir(parents=True, exist_ok=True)
    Path(settings.skins_dir).mkdir(parents=True, exist_ok=True)
    print("  ✓ 数据目录就绪")

    print("\n" + "=" * 60)
    print(f"  {settings.app_name} 启动完成!")
    print(f"  API:    http://localhost:{settings.port}/api")
    print(f"  前端:   http://localhost:{settings.port}/")
    print(f"  文档:   http://localhost:{settings.port}/docs")
    if master:
        print(f"  角色系统: {role_loader.role_count} 个角色已就绪")
    print("=" * 60)

    yield

    # 关闭时清理
    print("\n正在关闭...")
    agent_registry.shutdown()
    role_loader.shutdown()
    print("已安全关闭。")


# 创建 FastAPI 应用
app = FastAPI(
    title=settings.app_name,
    description="基于 AMD Radeon GPU 的私有 AI Agent 平台",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS (开发环境允许跨域)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册 API 路由
app.include_router(agent_routes.router)
app.include_router(skin_routes.router)
app.include_router(module_routes.router)
app.include_router(layout_routes.router)
app.include_router(workgroup_routes.router)
app.include_router(project_routes.router)
app.include_router(model_routes.router)
app.include_router(artifact_routes.router)


# 健康检查
@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "llm_available": llm_gateway.available,
        "current_model": llm_gateway.get_current_model(),
        "agents": agent_registry.list_agents(),
    }


# 静态文件服务 (前端构建产物)
frontend_dist = Path(settings.frontend_dist)
if frontend_dist.exists():
    app.mount("/assets", StaticFiles(directory=str(frontend_dist / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """前端 SPA — 所有非 API 路由返回 index.html"""
        if full_path.startswith("api"):
            return {"detail": "Not Found"}
        file_path = frontend_dist / full_path
        if file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(frontend_dist / "index.html"))
else:
    @app.get("/")
    async def root():
        return {
            "message": "MyAgent API 正在运行",
            "note": "前端未构建，请先在 frontend/ 目录执行 npm run build",
            "api_docs": "/docs",
            "health": "/api/health",
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )