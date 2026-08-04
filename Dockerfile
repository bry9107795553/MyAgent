# =============================================================================
# MyAgent Docker 镜像 — AMD ROCm 环境模拟
# 用于本地开发测试完整安装/运行流程，模拟评委的 AMD 环境
#
# 构建: docker build -t myagent:latest .
# 运行: docker compose up -d
# =============================================================================

FROM rocm/dev-ubuntu-22.04:7.2-complete

LABEL description="MyAgent - AMD ROCm 环境模拟 (LLM 走云端 API)"
LABEL version="1.0"

# 非交互式安装
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=Asia/Shanghai

# ===== 系统依赖 =====
RUN apt-get update -qq && apt-get install -y -qq --no-install-recommends \
    curl wget git nginx python3 python3-pip python3-venv python3-dev \
    build-essential ca-certificates gnupg \
    && rm -rf /var/lib/apt/lists/*

# ===== Node.js 20.x =====
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y -qq nodejs \
    && rm -rf /var/lib/apt/lists/*

# ===== 工作目录 =====
WORKDIR /app

# ===== 复制依赖文件 (利用 Docker 缓存) =====
COPY backend/requirements.txt backend/requirements.txt

# ===== Python 虚拟环境 + 后端依赖 =====
RUN cd backend \
    && python3 -m venv venv \
    && . venv/bin/activate \
    && pip install --upgrade pip -q \
    && pip install -r requirements.txt -q

# ===== 前端依赖 (package.json 先复制以利用缓存) =====
COPY frontend/package.json frontend/

# ===== 安装前端依赖 =====
RUN cd frontend && npm install --silent

# ===== 复制完整项目源码 =====
COPY . .

# ===== 构建前端 =====
RUN cd frontend && npm run build

# ===== 配置 Nginx =====
RUN rm -f /etc/nginx/sites-enabled/default \
    && sed "s|__FRONTEND_DIST__|/app/frontend/dist|g" /app/nginx.conf > /etc/nginx/nginx.conf

# ===== 创建数据目录 =====
RUN mkdir -p /app/data/agents /app/data/skins /app/data/templates /app/data/memory

# ===== 入口脚本 =====
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

EXPOSE 80 8080

ENTRYPOINT ["docker-entrypoint.sh"]