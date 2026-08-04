"""
MyAgent 全局配置
- 路径常量 (项目根目录、数据目录、Agent 目录等)
- Settings 类 (Pydantic BaseSettings，支持环境变量覆盖)
- 配置加载工具函数 (load_agent_config, load_models_config)
"""
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field
import yaml
from typing import Optional


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


# ===== Settings 类 =====

class Settings(BaseSettings):
    """全局配置 — 从环境变量或默认值读取"""

    # 服务配置
    app_name: str = "MyAgent"
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = True

    # llama.cpp 配置 (本地推理引擎)
    # llama-server 提供 OpenAI 兼容接口，使用 -a 参数指定模型名
    llama_base_url: str = "http://localhost:8000/v1"
    llama_model: str = "Qwen2.5-14B-Instruct"
    llama_api_key: str = "EMPTY"                       # llama-server 不需要 key
    llama_timeout: int = 120

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