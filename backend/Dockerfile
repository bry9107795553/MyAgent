# MyAgent 后端 — FastAPI + uvicorn
#
# 仅打包 API / 角色调度 / 工具层，**不含推理引擎**。
# 推理由独立容器提供（本地模拟 = mock-llm，真实部署 = ROCm llama.cpp），
# 且必须与本容器共享网络命名空间 —— 详见 docker-compose.yml 说明。
#
# 构建上下文是仓库根目录：
#   docker build -f backend/Dockerfile -t myagent-backend .

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# 依赖层单独缓存，改代码不会触发重装
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# 业务代码
COPY backend/ /app/backend/

# settings.py 用 PROJECT_ROOT = <backend 的上两级> 定位 data/，
# 这里保持 /app 为项目根，data/ 由 compose 以 volume 挂进来
RUN mkdir -p /app/data/agents /app/data/projects

WORKDIR /app/backend

ENV HOST=0.0.0.0 \
    PORT=8080 \
    LLAMA_BASE_URL=http://localhost:8000/v1

EXPOSE 8080

# 只探活 HTTP 层：llm_available 可能因推理引擎仍在加载模型而为 false，
# 这不代表后端本身不健康（后端已支持推理端点后到时自动恢复）
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=6 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/api/health',timeout=4).status==200 else 1)"

CMD ["python", "main.py"]
