"""
LLM 网关 — 统一推理接口（**纯本地**）

- 对接 llama.cpp (llama-server, OpenAI 兼容接口)，跑在 AMD Radeon GPU + ROCm 上
- 支持流式输出
- 支持工具调用 (function calling)
- 支持多 GPU 路由 (base_url_override)，各 GPU 均为本机端口
- 隐私标签: 全部 local_only

————————————————————————————————————————————————
合规说明（AMD AI DevMaster Hackathon · Track 2）
本网关**没有任何远程/云端推理通路**。所有客户端在创建前都必须通过
`assert_local_endpoint()` 校验，非本机地址直接抛 RemoteInferenceForbidden。
本地 llama.cpp 不可用时，网关进入 "none" 模式（推理不可用），
**不会、也无法**切换到任何托管模型服务。
历史上存在的智谱 GLM-4 降级通道已于 P0 合规清理中物理删除。
————————————————————————————————————————————————
"""
from openai import AsyncOpenAI
from typing import AsyncGenerator, Optional
import json
import httpx
import asyncio
import time

from config.settings import settings, assert_local_endpoint


class LLMGateway:
    """统一 LLM 网关 — 所有推理请求的入口（仅本机 llama.cpp）"""

    # 多 GPU 客户端池 (按 base_url 缓存，全部为本机端口)
    _clients: dict[str, AsyncOpenAI] = {}

    def __init__(self):
        self._client: Optional[AsyncOpenAI] = None
        self._available: bool = False
        self._mode: str = "local"         # "local" | "none" —— 没有 "cloud"
        self._last_probe: float = 0.0     # 上次惰性重探时间戳
        self._probe_interval: float = 10.0

    def _new_local_client(self, base_url: str) -> AsyncOpenAI:
        """创建一个本机推理客户端。非本机地址会在这里被拦截。"""
        assert_local_endpoint(base_url)
        return AsyncOpenAI(
            base_url=base_url,
            api_key=settings.llama_api_key,
            timeout=httpx.Timeout(settings.llama_timeout, connect=10.0),
        )

    async def init(self):
        """初始化本地 llama.cpp 客户端。连不上就是不可用，没有降级路径。"""
        self._client = self._new_local_client(settings.llama_base_url)

        max_retries = 3
        for attempt in range(1, max_retries + 1):
            try:
                models = await self._client.models.list()
                self._available = True
                self._mode = "local"
                print(f"[LLM Gateway] llama.cpp 已连接，可用模型: {[m.id for m in models.data]}")
                print("[LLM Gateway] 模式: 本地推理 (llama.cpp / ROCm)")
                return
            except Exception as e:
                print(f"[LLM Gateway] 本地连接尝试 {attempt}/{max_retries} 失败: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(3)

        # 本地不可用 —— 到此为止，本项目不存在云端降级
        self._available = False
        self._mode = "none"
        print("[LLM Gateway] ✗ 本地 llama.cpp 不可用，推理功能关闭。")
        print("[LLM Gateway]   本项目仅支持本地推理，不提供任何远程 API 降级通道。")
        print(f"[LLM Gateway]   请先启动 llama-server 并监听 {settings.llama_base_url}")

    def _get_client(self, base_url: str = "") -> AsyncOpenAI:
        """
        获取客户端实例 (支持多 GPU 路由，全部为本机端口)

        :param base_url: LLM 服务 URL，为空则使用默认本机客户端
        :return: AsyncOpenAI 客户端（指向本机 llama-server）
        """
        if base_url:
            if base_url not in self._clients:
                self._clients[base_url] = self._new_local_client(base_url)
                print(f"[LLM Gateway] 新建本机 GPU 客户端: {base_url}")
            return self._clients[base_url]

        return self._client

    def _get_model_name(self, base_url: str = "") -> str:
        """获取当前使用的模型名称（始终是本地 GGUF 模型）"""
        return settings.llama_model

    @property
    def available(self) -> bool:
        return self._available

    async def ensure_available(self) -> bool:
        """
        惰性重探本地推理端点。

        llama-server 加载 14B GGUF 到显存可能需要几十秒甚至数分钟，
        往往晚于后端启动完成。若只在 init() 里探测一次就固化为不可用，
        后续 /api/health 会一直报 llm_available=false、/chat 一直 503，
        必须重启后端才能恢复 —— 这在容器编排里是致命的启动顺序陷阱。
        因此对外暴露一次带节流的重探（默认最快 10 秒一次）。
        """
        if self._available:
            return True

        now = time.monotonic()
        if now - self._last_probe < self._probe_interval:
            return False
        self._last_probe = now

        if self._client is None:
            self._client = self._new_local_client(settings.llama_base_url)
        try:
            await self._client.models.list()
            self._available = True
            self._mode = "local"
            print("[LLM Gateway] ✓ 本地 llama.cpp 重探成功，推理功能已恢复")
            return True
        except Exception as e:
            print(f"[LLM Gateway] 重探失败，推理仍不可用: {e}")
            return False

    @property
    def mode(self) -> str:
        """返回当前模式: 'local' | 'none' —— 本项目不存在 'cloud' 模式"""
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
            "reasoning": getattr(choice.message, "reasoning_content", None) or "",
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