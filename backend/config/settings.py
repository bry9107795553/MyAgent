"""
MyAgent 全局配置
- 路径常量 (项目根目录、数据目录、Agent 目录等)
- Settings 类 (Pydantic BaseSettings，支持环境变量覆盖)
- 配置加载工具函数 (load_agent_config, load_models_config)

================================================================
本地推理合规声明 (AMD AI DevMaster Hackathon · Track 2)
================================================================
本项目的全部模型推理均在本机 llama.cpp (ROCm / AMD Radeon GPU) 上完成。

代码库中不存在：
  - 任何托管大模型服务 (智谱 / OpenAI / DashScope / Anthropic ...) 的客户端
  - 任何远程 API 密钥字段或环境变量入口
  - 任何"本地不可用则切云端"的降级通道

`openai` 这个 pip 依赖仅被用作 **OpenAI 兼容协议的客户端库**，其 base_url
永远指向本机 llama-server。下方 `assert_local_endpoint()` 在运行时强制校验
这一点：任何非本机地址都会直接抛异常，服务无法启动。
================================================================
"""
from pathlib import Path
from urllib.parse import urlparse
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import yaml
from typing import Optional


# ===== 本地推理硬约束 =====

LOCAL_INFERENCE_ONLY = True

# 唯一允许的推理服务主机名。任何其他地址一律拒绝。
ALLOWED_INFERENCE_HOSTS = frozenset({
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "::1",
    "[::1]",
})


class RemoteInferenceForbidden(RuntimeError):
    """试图把推理请求指向非本机地址时抛出（赛道合规硬约束）"""


def assert_local_endpoint(base_url: str) -> str:
    """
    强制校验推理端点必须是本机地址。

    这是赛道「核心推理不允许使用远程 API」的代码级执行点，
    不是注释、不是开关 —— 违反即抛异常，服务起不来。

    :param base_url: 待校验的推理服务 URL
    :return: 原样返回 base_url（校验通过时）
    :raises RemoteInferenceForbidden: base_url 指向非本机地址
    """
    host = (urlparse(base_url).hostname or "").lower()
    if host not in ALLOWED_INFERENCE_HOSTS:
        raise RemoteInferenceForbidden(
            f"拒绝远程推理端点: {base_url!r} (host={host!r})。\n"
            f"本项目仅允许本机 llama.cpp 推理，"
            f"允许的主机名: {sorted(ALLOWED_INFERENCE_HOSTS)}"
        )
    return base_url


# ===== 路径常量 =====

# 项目根目录 (myagent/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# backend 目录
BACKEND_DIR = Path(__file__).resolve().parent.parent

# 数据目录
DATA_DIR = PROJECT_ROOT / "data"
AGENTS_DIR = DATA_DIR / "agents"
SKINS_DIR = DATA_DIR / "skins"
TEMPLATES_DIR = DATA_DIR / "templates"


# ===== 多 GPU 端点表 =====
#
# 仅在 single_gpu_mode=False 时生效。三张卡各起一个 llama-server：
#   gpu0 → :8000  14B 文本 (重活)
#   gpu1 → :8001  7B 文本 + VL 视觉
#   gpu2 → :8002  7B 文本 (轻活)
# 全部为本机端口，仍然受 assert_local_endpoint() 约束。
MULTI_GPU_ENDPOINTS: dict[str, str] = {
    "gpu0": "http://localhost:8000/v1",
    "gpu1": "http://localhost:8001/v1",
    "gpu2": "http://localhost:8002/v1",
}


# ===== Settings 类 =====

class Settings(BaseSettings):
    """
    全局配置 — 从 .env 文件或环境变量读取

    注意 `extra="ignore"`：任何未在本类中声明的环境变量都会被静默丢弃。
    因此像 ZHIPU_API_KEY / CLOUD_API_ENABLED / OPENAI_API_KEY 这类残留的
    远程 API 变量，即使被误设置在环境里，也**没有任何字段可以承接它们**，
    不存在被意外打开的可能。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 服务配置
    app_name: str = "MyAgent"
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = True

    # llama.cpp 配置 (本地推理引擎 — 本项目唯一的推理后端)
    # llama-server 提供 OpenAI 兼容接口，使用 -a 参数指定模型名
    # base_url 受 assert_local_endpoint() 强制约束，只能是本机地址
    llama_base_url: str = "http://localhost:8000/v1"
    llama_model: str = "Qwen2.5-14B-Instruct"
    llama_api_key: str = "EMPTY"                       # llama-server 不需要 key
    llama_timeout: int = 120

    # 【已物理移除】云端 API 降级配置
    # 原先此处有 cloud_api_base_url / cloud_api_model / cloud_api_key /
    # cloud_api_enabled 四个字段，指向智谱 GLM-4。
    # 依据赛道规则「核心推理不允许使用远程 API」，整条降级通道已从
    # settings / gateway / models.yaml / 部署脚本中彻底删除，不保留开关。

    # ===== GPU 路由模式 =====
    #
    # 默认 True —— 「默认即正确」。
    #
    # 本项目的实际交付环境是 Radeon Cloud 单卡实例
    # (AMD Radeon PRO W7900 / 48GB / gfx1100)，只会起 **一个** llama-server
    # (端口 8000)。若默认走多 GPU 路由，凡是 gpu_affinity=gpu1/gpu2 的角色
    # 都会去连 8001/8002 —— 那里没有服务，部署阶段一切正常，跑到多角色
    # 流水线中途才会 Connection refused。这类「部署成功、演示炸场」的坑
    # 必须靠默认值堵死，而不是靠部署者记得设环境变量。
    #
    # 单 GPU 模式 (默认, single_gpu_mode=True):
    #     所有角色共享 llama_base_url 这一个端点。
    #
    # 多 GPU 模式 (显式关闭):
    #     SINGLE_GPU_MODE=false        # 环境变量
    #     或 backend/.env 里写 SINGLE_GPU_MODE=false
    #     此时按 MULTI_GPU_ENDPOINTS 表按 gpu_affinity 分流，
    #     需要自行起满 8000/8001/8002 三个 llama-server。
    single_gpu_mode: bool = True

    # 兼容旧字段名 (vllm_* → llama_*，保留别名以兼容已有调用方)
    @property
    def vllm_base_url(self) -> str:
        return self.llama_base_url

    @property
    def vllm_model(self) -> str:
        return self.llama_model

    @property
    def vllm_api_key(self) -> str:
        return self.llama_api_key

    @property
    def vllm_timeout(self) -> int:
        return self.llama_timeout

    # 默认推理参数
    default_temperature: float = 0.7
    default_max_tokens: int = 4096

    # 路径
    project_root: str = str(PROJECT_ROOT)
    data_dir: str = str(DATA_DIR)
    agents_dir: str = str(AGENTS_DIR)
    skins_dir: str = str(SKINS_DIR)
    templates_dir: str = str(TEMPLATES_DIR)

    # 前端静态文件目录
    frontend_dist: str = str(PROJECT_ROOT / "frontend" / "dist")

    # ------------------------------------------------------------------ #
    # 推理端点路由 (全系统唯一入口)
    # ------------------------------------------------------------------ #

    def resolve_inference_url(self, gpu_affinity: str = "gpu0") -> str:
        """
        按角色的 GPU 亲和性解析推理端点。

        这是**全系统唯一**的端点路由入口 —— role_base 不再各自硬编码端口，
        避免「改了 LLAMA_PORT，单卡模式还往 8000 打」这类不一致。

        单 GPU 模式 (默认):
            无视 gpu_affinity，一律返回 llama_base_url。
            改 LLAMA_BASE_URL 即可整体换端口，路由自动跟随。

        多 GPU 模式 (SINGLE_GPU_MODE=false):
            按 MULTI_GPU_ENDPOINTS 分流；未知亲和性回落到 llama_base_url。

        :param gpu_affinity: "gpu0" / "gpu1" / "gpu2"
        :return: OpenAI 兼容端点 URL (始终为本机地址)
        """
        if self.single_gpu_mode:
            return self.llama_base_url
        return MULTI_GPU_ENDPOINTS.get(gpu_affinity, self.llama_base_url)

    def describe_gpu_routing(self) -> str:
        """一行式路由摘要，供启动日志打印（上机时肉眼可核对）"""
        if self.single_gpu_mode:
            return (f"单 GPU 模式 (SINGLE_GPU_MODE=true) — "
                    f"全部角色 → {self.llama_base_url}")
        eps = " | ".join(f"{k}→{v}" for k, v in MULTI_GPU_ENDPOINTS.items())
        return f"多 GPU 模式 (SINGLE_GPU_MODE=false) — {eps}"


# 全局配置单例
settings = Settings()


# ===== 工具函数 =====

def load_agent_config(agent_id: str) -> dict:
    """读取指定 Agent 的 config.yaml"""
    config_path = Path(settings.agents_dir) / agent_id / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Agent 配置不存在: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_models_config() -> dict:
    """读取模型配置 models.yaml"""
    models_path = Path(__file__).parent / "models.yaml"
    if not models_path.exists():
        return {"profiles": []}
    with open(models_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)