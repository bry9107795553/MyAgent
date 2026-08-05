"""
Agent API 路由 — 对话、列表、创建、删除、AI 生成
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException
from pydantic import BaseModel
from typing import Optional

from core.agent.registry import agent_registry
from core.agent.lifecycle import agent_lifecycle
from core.agent.agent_generator import agent_generator
from core.agent.agent_schemas import AgentGenerateRequest
from core.llm.gateway import llm_gateway
from core.bus import message_bus

router = APIRouter(prefix="/api/agents", tags=["agents"])


# ===== 请求模型 =====

class ChatRequest(BaseModel):
    message: str
    stream: bool = False


class CreateAgentRequest(BaseModel):
    agent_id: str
    name: str
    description: str = ""
    template: str = "default"
    system_prompt: str = ""


# ===== 路由 =====

@router.get("")
async def list_agents():
    """列出所有已注册 Agent"""
    return {"agents": agent_registry.list_agents()}


@router.get("/{agent_id}")
async def get_agent(agent_id: str):
    """获取 Agent 详情"""
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent 不存在: {agent_id}")
    return {
        "agent_id": agent.agent_id,
        "name": agent.name,
        "description": agent.description,
        "config": agent.config,
    }


@router.post("")
async def create_agent(req: CreateAgentRequest):
    """创建新 Agent (从模板)"""
    try:
        result = agent_lifecycle.create_agent(
            agent_id=req.agent_id,
            name=req.name,
            description=req.description,
            template=req.template,
            system_prompt=req.system_prompt,
        )
        # 显式注册：watchdog 的目录事件早于 config.yaml 落盘，
        # 且容器环境常禁用 inotify，只依赖热加载会让新 Agent 立即对话时 WS 403
        if not agent_registry.get(req.agent_id):
            await agent_registry.register(req.agent_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/generate")
async def generate_agent(req: AgentGenerateRequest):
    """AI 生成 Agent — 用自然语言描述自动创建 Agent 配置"""
    if not await llm_gateway.ensure_available():
        raise HTTPException(status_code=503, detail="LLM 推理引擎未就绪，请检查 llama-server 是否已启动")

    result = await agent_generator.generate(req)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.error)

    return result.model_dump()


@router.delete("/{agent_id}")
async def delete_agent(agent_id: str):
    """删除 Agent"""
    try:
        # 先注销再删目录：注销会 save_memory()，目录删掉后写盘会失败
        await agent_registry.unregister(agent_id)
        result = agent_lifecycle.delete_agent(agent_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{agent_id}/chat")
async def chat(agent_id: str, req: ChatRequest):
    """非流式对话"""
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent 不存在: {agent_id}")

    if not await llm_gateway.ensure_available():
        raise HTTPException(status_code=503, detail="LLM 推理引擎未就绪，请检查 llama-server 是否已启动")

    result = await agent.chat(req.message)
    return {
        "agent_id": agent_id,
        "reply": result["reply"],
        "type": result.get("type", "direct"),
        "workgroup": result.get("workgroup"),
        "roles_used": result.get("roles_used", []),
    }


@router.get("/{agent_id}/history")
async def get_history(agent_id: str):
    """获取对话历史"""
    agent = agent_registry.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent 不存在: {agent_id}")
    return {"agent_id": agent_id, "history": agent._chat_history}


# ===== WebSocket 流式对话 =====

@router.websocket("/{agent_id}/ws")
async def agent_websocket(websocket: WebSocket, agent_id: str):
    """WebSocket 流式对话 — 实时推送 token + 调度元数据"""
    agent = agent_registry.get(agent_id)
    if not agent:
        await websocket.close(code=4004, reason=f"Agent 不存在: {agent_id}")
        return

    await message_bus.connect(websocket, agent_id)
    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message", "")

            # 流式推理 → 通过消息总线推送
            # 调度元数据 (type, workgroup, roles_used) 在 stream_end 之前下发，
            # 否则客户端已在 stream_end 时关闭连接，元数据会丢失
            await message_bus.stream_to_agent(
                agent_id,
                agent.chat_stream(user_message),
                meta_provider=lambda: agent.last_dispatch_info,
            )

            # 保存记忆
            agent.save_memory()

    except WebSocketDisconnect:
        await message_bus.disconnect(websocket, agent_id)
