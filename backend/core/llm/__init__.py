"""
LLM 网关 — 统一推理接口

模块:
    gateway.py — LLMGateway: llama.cpp 多 GPU 路由 + 流式对话
"""
from core.llm.gateway import llm_gateway, LLMGateway