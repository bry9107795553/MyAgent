"""
LLM 网关 — 统一推理接口
- 对接 llama.cpp (llama-server, OpenAI 兼容接口)
- 支持流式输出
- 支持工具调用 (function calling)
- 支持多 GPU 路由 (base_url_override)
- 支持模型切换 (本地/云端动态切换)
- 隐私标签路由 (local_only / cloud_allowed)
"""
from openai import AsyncOpenAI
from typing import AsyncGenerator, Optional
import json
import os
import httpx
import asyncio

from config.settings import settings, load_models_config


class LLMGateway:
    """统一 LLM 网关 — 所有推理请求的入口"""

    # 多 GPU 客户端池 (按 base_url 缓存)
    _clients: dict[str, AsyncOpenAI] = {}

    def __init__(self):
        self._client: Optional[AsyncOpenAI] = None
        self._available: bool = False
        self._profiles: dict[str, dict] = {}
        self._current_profile_id: str = ""

    # ------------------------------------------------------------------ #
    # 模型配置管理
    # ------------------------------------------------------------------ #

    def load_profiles(self):
        """从 models.yaml 加载模型配置"""
        config = load_models_config()
        profiles = config.get("profiles", [])
        self._profiles = {}
        for p in profiles:
            pid = p["id"]
            # 解析环境变量占位符 (如 ${ZHIPU_API_KEY})
            resolved = dict(p)
            api_key = p.get("api_key", "EMPTY")
            if api_key.startswith("${") and api_key.endswith("}"):
                env_var = api_key[2:-1]
                resolved["api_key"] = os.environ.get(env_var, "EMPTY")
            self._profiles[pid] = resolved

        # 默认选中第一个 profile
        if self._profiles and not self._current_profile_id:
            self._current_profile_id = list(self._profiles.keys())[0]

        print(f"[LLM Gateway] 已加载 {len(self._profiles)} 个模型配置: {list(self._profiles.keys())}")
        print(f"[LLM Gateway] 当前模型: {self._current_profile_id}")

    def switch_model(self, profile_id: str) -> bool:
        """
        切换当前使用的模型

        :param profile_id: 模型配置 ID (如 local-qwen2.5-14b, cloud-zhipu)
        :return: 是否切换成功
        """
        if profile_id not in self._profiles:
            return False
        self._current_profile_id = profile_id
        print(f"[LLM Gateway] 已切换模型 → {profile_id}")
        return True

    def get_current_model(self) -> dict:
        """获取当前模型信息"""
        if not self._current_profile_id or self._current_profile_id not in self._profiles:
            return {"id": "unknown", "name": "未知", "provider": "unknown", "privacy_tag": "unknown"}
        p = self._profiles[self._current_profile_id]
        return {
            "id": self._current_profile_id,
            "name": p.get("model_name", "unknown"),
            "provider": p.get("provider", "unknown"),
            "privacy_tag": p.get("privacy_tag", "unknown"),
        }

    def list_models(self) -> list[dict]:
        """列出所有可用模型"""
        result = []
        for pid, p in self._profiles.items():
            result.append({
                "id": pid,
                "name": p.get("model_name", "unknown"),
                "provider": p.get("provider", "unknown"),
                "capabilities": p.get("capabilities", []),
                "privacy_tag": p.get("privacy_tag", "unknown"),
                "is_active": pid == self._current_profile_id,
            })
        return result

    def _get_active_profile(self) -> dict:
        """获取当前激活的模型配置"""
        if self._current_profile_id and self._current_profile_id in self._profiles:
            return self._profiles[self._current_profile_id]
        # 回退到 settings 默认值
        return {
            "base_url": settings.llama_base_url,
            "model_name": settings.llama_model,
            "api_key": settings.llama_api_key,
            "default_temperature": settings.default_temperature,
            "default_max_tokens": settings.default_max_tokens,
        }

    # ------------------------------------------------------------------ #
    # 初始化
    # ------------------------------------------------------------------ #

    async def init(self):
        """初始化 llama.cpp 客户端，检测连接（带重试，应对模型加载延迟）"""
        # 先加载模型配置
        self.load_profiles()

        # 用当前 profile 的 base_url 初始化客户端
        profile = self._get_active_profile()
        base_url = profile.get("base_url", settings.llama_base_url)
        api_key = profile.get("api_key", settings.llama_api_key)

        self._client = AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            timeout=httpx.Timeout(settings.llama_timeout, connect=10.0),
        )
        # 重试连接（模型加载可能需要几秒到几十秒）
        max_retries = 6
        for attempt in range(1, max_retries + 1):
            try:
                models = await self._client.models.list()
                self._available = True
                print(f"[LLM Gateway] {base_url} 已连接，可用模型: {[m.id for m in models.data]}")
                return
            except Exception as e:
                print(f"[LLM Gateway] 连接尝试 {attempt}/{max_retries} 失败: {e}")
                if attempt < max_retries:
                    await asyncio.sleep(5)
        self._available = False
        print("[LLM Gateway] ⚠ llama.cpp 连接失败，推理功能暂不可用")
        print("[LLM Gateway]   服务将在模型就绪后自动恢复")

    def _get_client(self, base_url: str = "") -> AsyncOpenAI:
        """
        获取客户端实例 (支持多 GPU 路由和模型切换)

        :param base_url: LLM 服务 URL，为空则使用当前 profile 的 URL
        :return: AsyncOpenAI 客户端
        """
        if not base_url:
            # 使用当前 profile 的 base_url
            profile = self._get_active_profile()
            base_url = profile.get("base_url", settings.llama_base_url)
            api_key = profile.get("api_key", settings.llama_api_key)
        else:
            api_key = settings.llama_api_key

        # 缓存多客户端
        if base_url not in self._clients:
            self._clients[base_url] = AsyncOpenAI(
                base_url=base_url,
                api_key=api_key,
                timeout=httpx.Timeout(settings.llama_timeout, connect=10.0),
            )
            print(f"[LLM Gateway] 新建客户端: {base_url}")
        return self._clients[base_url]

    @property
    def available(self) -> bool:
        return self._available

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
        :param agent_config: Agent 配置 (可覆盖默认参数)
        :param temperature: 采样温度
        :param max_tokens: 最大生成 token 数
        :param tools: 工具定义 (function calling)
        :param base_url: 多 GPU 路由: 指定 LLM 服务 URL
        :return: {"content": str, "tool_calls": list}
        """
        profile = self._get_active_profile()
        client = self._get_client(base_url)
        if not client:
            raise RuntimeError("LLM Gateway 未初始化，请先调用 init()")

        temp = temperature or profile.get("default_temperature", settings.default_temperature)
        max_tok = max_tokens or profile.get("default_max_tokens", settings.default_max_tokens)
        model_name = profile.get("model_name", settings.llama_model)

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
        :param agent_config: Agent 配置
        :param temperature: 采样温度
        :param max_tokens: 最大生成 token 数
        :param base_url: 多 GPU 路由: 指定 LLM 服务 URL
        :yield: 每次返回一个 token (str)
        """
        profile = self._get_active_profile()
        client = self._get_client(base_url)
        if not client:
            raise RuntimeError("LLM Gateway 未初始化，请先调用 init()")

        temp = temperature or profile.get("default_temperature", settings.default_temperature)
        max_tok = max_tokens or profile.get("default_max_tokens", settings.default_max_tokens)
        model_name = profile.get("model_name", settings.llama_model)

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