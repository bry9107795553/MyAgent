"""
LLM 网关 — 统一推理接口
- 对接 llama.cpp (llama-server, OpenAI 兼容接口)
- 支持流式输出
- 支持工具调用 (function calling)
- 支持多 GPU 路由 (base_url_override)
- 隐私标签路由 (local_only / cloud_allowed)
- 云端 API 降级: 本地 llama.cpp 不可用时自动切换智谱云 API
"""
from openai import AsyncOpenAI
from typing import AsyncGenerator, Optional
import json
import httpx
import asyncio
import os

from config.settings import settings


class LLMGateway:
    """统一 LLM 网关 — 所有推理请求的入口"""

    # 多 GPU 客户端池 (按 base_url 缓存)
    _clients: dict[str, AsyncOpenAI] = {}

    def __init__(self):
        self._client: Optional[AsyncOpenAI] = None
        self._cloud_client: Optional[AsyncOpenAI] = None
        self._available: bool = False
        self._mode: str = "local"         # "local" | "cloud" | "none"
        self._cloud_available: bool = False

    async def init(self):
        """初始化 LLM 客户端，优先本地 llama.cpp，不可用时降级到云端 API"""
        # 1. 尝试连接本地 llama.cpp
        self._client = AsyncOpenAI(
            base_url=settings.llama_base_url,
            api_key=settings.llama_api_key,
            timeout=httpx.Timeout(settings.llama_timeout, connect=10.0),
        )

        max_retries = 3  # 减少重试次数，加快降级
        local_ok = False
        for attempt in range(1, max_retries + 1):
            try:
                models = await self._client.models.list()
                self._available = True
                self._mode = "local"
                local_ok = True
                print(f"[LLM Gateway] llama.cpp 已连接，可用模型: {[m.id for m in models.data]}")
                break
            except Exception as e:
                print(f"[LLM Gateway] 本地连接尝试 {attempt}/{max_retries} 失败: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(3)

        if local_ok:
            return

        # 2. 本地不可用，尝试云端 API 降级
        self._available = False
        print("[LLM Gateway] ⚠ 本地 llama.cpp 不可用，尝试云端 API 降级...")

        if not settings.cloud_api_enabled:
            print("[LLM Gateway] ⚠ 云端 API 降级未启用，推理功能暂不可用")
            self._mode = "none"
            return

        cloud_key = settings.cloud_api_key or os.environ.get("ZHIPU_API_KEY", "")
        if not cloud_key:
            print("[LLM Gateway] ⚠ 未配置 ZHIPU_API_KEY 环境变量，云端 API 不可用")
            print("[LLM Gateway]   请设置环境变量: set ZHIPU_API_KEY=你的密钥")
            self._mode = "none"
            return

        self._cloud_client = AsyncOpenAI(
            base_url=settings.cloud_api_base_url,
            api_key=cloud_key,
            timeout=httpx.Timeout(settings.llama_timeout, connect=10.0),
        )

        try:
            # 测试云端连接
            test_response = await self._cloud_client.chat.completions.create(
                model=settings.cloud_api_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=5,
            )
            self._cloud_available = True
            self._available = True
            self._mode = "cloud"
            print(f"[LLM Gateway] ✓ 云端 API 降级成功，使用模型: {settings.cloud_api_model}")
            print(f"[LLM Gateway]   模式: 云端 API (智谱)")
        except Exception as e:
            print(f"[LLM Gateway] ✗ 云端 API 连接失败: {e}")
            self._mode = "none"
            print("[LLM Gateway]   推理功能暂不可用，请检查网络或 API Key")

    def _get_client(self, base_url: str = "") -> AsyncOpenAI:
        """
        获取客户端实例 (支持多 GPU 路由 + 云端降级)

        :param base_url: LLM 服务 URL，为空则使用当前模式对应的客户端
        :return: AsyncOpenAI 客户端
        """
        if base_url:
            # 缓存多 GPU 客户端
            if base_url not in self._clients:
                self._clients[base_url] = AsyncOpenAI(
                    base_url=base_url,
                    api_key=settings.llama_api_key,
                    timeout=httpx.Timeout(settings.llama_timeout, connect=10.0),
                )
                print(f"[LLM Gateway] 新建 GPU 客户端: {base_url}")
            return self._clients[base_url]

        # 无指定 base_url，使用当前模式
        if self._mode == "cloud":
            return self._cloud_client
        return self._client

    def _get_model_name(self, base_url: str = "") -> str:
        """获取当前使用的模型名称"""
        if base_url:
            return settings.llama_model
        if self._mode == "cloud":
            return settings.cloud_api_model
        return settings.llama_model

    @property
    def available(self) -> bool:
        return self._available

    @property
    def mode(self) -> str:
        """返回当前模式: 'local' | 'cloud' | 'none'"""
        return self._mode

    async def chat(
        self,
        messages: list[dict],
        agent_config: dict | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        tools: list[dict] | None = None,
        base_url: str = "",
    ) -> dict:
        """
        非流式对话

        :param messages: OpenAI 消息格式 [{"role": "system", "content": "..."}, ...]
        :param agent_config: Agent 配置 (可覆盖默认参数，已废弃 model 字段)
        :param temperature: 采样温度
        :param max_tokens: 最大生成 token 数
        :param tools: 工具定义 (function calling)
        :param base_url: 多 GPU 路由: 指定 LLM 服务 URL
        :return: {"content": str, "tool_calls": list}
        """
        client = self._get_client(base_url)
        if not client:
            raise RuntimeError("LLM Gateway 未初始化，请先调用 init()")

        temp = temperature or settings.default_temperature
        max_tok = max_tokens or settings.default_max_tokens
        model_name = self._get_model_name(base_url)

        response = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temp,
            max_tokens=max_tok,
            tools=tools,
        )

        choice = response.choices[0]
        result = {
            "content": choice.message.content or "",
            "tool_calls": [],
        }

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                result["tool_calls"].append({
                    "id": tc.id,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                })

        return result

    async def chat_stream(
        self,
        messages: list[dict],
        agent_config: dict | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        base_url: str = "",
    ) -> AsyncGenerator[str, None]:
        """
        流式对话 — 逐 token 生成

        :param messages: OpenAI 消息格式
        :param agent_config: Agent 配置 (已废弃 model 字段)
        :param temperature: 采样温度
        :param max_tokens: 最大生成 token 数
        :param base_url: 多 GPU 路由: 指定 LLM 服务 URL
        :yield: 每次返回一个 token (str)
        """
        client = self._get_client(base_url)
        if not client:
            raise RuntimeError("LLM Gateway 未初始化，请先调用 init()")

        temp = temperature or settings.default_temperature
        max_tok = max_tokens or settings.default_max_tokens
        model_name = self._get_model_name(base_url)

        stream = await client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=temp,
            max_tokens=max_tok,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content


# 全局网关单例
llm_gateway = LLMGateway()