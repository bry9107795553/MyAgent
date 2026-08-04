#!/bin/bash
# =============================================================================
# MyAgent 启动脚本 — AMD Radeon Cloud 直接部署（无 Docker）
# 启动: llama.cpp (llama-server) → FastAPI → Nginx
# 使用方式: bash start.sh
# =============================================================================

set -e

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

# 目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
VENV_DIR="$BACKEND_DIR/venv"

# llama.cpp 路径
LLAMA_DIR="$HOME/llama.cpp"
LLAMA_SERVER="$LLAMA_DIR/build/bin/llama-server"
MODEL_FILE="$LLAMA_DIR/models/qwen2.5-14b-instruct-q4_k_m.gguf"

# 如果默认路径不存在，尝试查找
if [ ! -f "$LLAMA_SERVER" ]; then
    LLAMA_SERVER=$(find "$LLAMA_DIR" -name "llama-server" -type f 2>/dev/null | head -1)
fi
if [ ! -f "$MODEL_FILE" ]; then
    MODEL_FILE=$(find "$LLAMA_DIR/models" -name "*.gguf" -type f 2>/dev/null | head -1)
fi

# PID 文件
PID_DIR="/tmp/myagent"
mkdir -p "$PID_DIR"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  MyAgent 启动${NC}"
echo -e "${BLUE}========================================${NC}"

# ===== 0. GPU 路由预检 =====
# 本脚本只启动 1 个 llama-server (:8000)。若后端跑在多 GPU 路由下，
# gpu_affinity=gpu1/gpu2 的角色会去连 8001/8002 —— 那里没有服务，
# 部署阶段看不出问题，跑到多角色流水线中途才炸。这里提前拦。
ENV_FILE="$BACKEND_DIR/.env"
SINGLE_GPU_MODE="$(grep -s '^SINGLE_GPU_MODE=' "$ENV_FILE" | tail -1 | cut -d= -f2- | tr -d '[:space:]')"
# 未在 .env 中显式配置时，采用 settings.py 的默认值 true（默认即正确）
SINGLE_GPU_MODE="${SINGLE_GPU_MODE:-true}"

echo ""
if [ "$SINGLE_GPU_MODE" = "true" ]; then
    echo -e "${GREEN}[0/3]${NC} GPU 路由: 单卡模式 — 全部角色 → http://localhost:8000/v1"
else
    echo -e "${YELLOW}[0/3]${NC} GPU 路由: 多卡模式 (SINGLE_GPU_MODE=$SINGLE_GPU_MODE)"
    echo -e "  ${YELLOW}⚠${NC} 本脚本只会启动 :8000 这一个 llama-server。"
    echo -e "  ${YELLOW}⚠${NC} 请自行确保 :8001 / :8002 也已就绪，否则 gpu1/gpu2 角色必然连接失败。"
    echo -e "  ${YELLOW}⚠${NC} 单卡实例请改回: sed -i 's|^SINGLE_GPU_MODE=.*|SINGLE_GPU_MODE=true|' backend/.env"
fi

# ===== 1. 启动 llama.cpp 推理引擎 =====
echo ""
echo -e "${YELLOW}[1/3] 启动 llama.cpp (llama-server)...${NC}"

if [ -f "$PID_DIR/llama.pid" ] && kill -0 $(cat "$PID_DIR/llama.pid") 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} llama-server 已在运行 (PID: $(cat $PID_DIR/llama.pid))"
else
    # 检查二进制和模型
    if [ ! -f "$LLAMA_SERVER" ]; then
        echo -e "  ${RED}✗${NC} llama-server 未找到，请先运行 install.sh"
        exit 1
    fi
    if [ ! -f "$MODEL_FILE" ]; then
        echo -e "  ${RED}✗${NC} GGUF 模型未找到，请先运行 install.sh"
        exit 1
    fi

    echo -e "  二进制: $LLAMA_SERVER"
    echo -e "  模型: $MODEL_FILE"

    # 后台启动 llama-server (ROCm)
    nohup "$LLAMA_SERVER" \
        -m "$MODEL_FILE" \
        -a "Qwen2.5-14B-Instruct" \
        --port 8000 \
        -c 32768 \
        -ngl 99 \
        > /tmp/llama.log 2>&1 &

    LLAMA_PID=$!
    echo $LLAMA_PID > "$PID_DIR/llama.pid"
    echo -e "  llama-server 启动中 (PID: $LLAMA_PID)，等待模型加载..."

    # 等待 llama-server 就绪 (最多等 300 秒)
    for i in $(seq 1 300); do
        if curl -s http://localhost:8000/v1/models > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} llama-server 已就绪 (${i}s)"
            break
        fi

        # 检查进程是否还活着
        if ! kill -0 $LLAMA_PID 2>/dev/null; then
            echo -e "  ${RED}✗${NC} llama-server 进程异常退出"
            echo -e "  请查看日志: tail -f /tmp/llama.log"
            exit 1
        fi

        if [ $((i % 30)) -eq 0 ]; then
            echo -e "  仍在加载... (${i}s)"
        fi

        sleep 1

        if [ $i -eq 300 ]; then
            echo -e "  ${YELLOW}⚠${NC} llama-server 启动超时 (300s)，可能仍在加载大模型"
            echo -e "  请查看日志: tail -f /tmp/llama.log"
        fi
    done
fi

# ===== 2. 启动 FastAPI 后端 =====
echo ""
echo -e "${YELLOW}[2/3] 启动 FastAPI 后端...${NC}"

if [ -f "$PID_DIR/backend.pid" ] && kill -0 $(cat "$PID_DIR/backend.pid") 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} FastAPI 已在运行 (PID: $(cat $PID_DIR/backend.pid))"
else
    source "$VENV_DIR/bin/activate"
    cd "$BACKEND_DIR"

    nohup uvicorn main:app --host 0.0.0.0 --port 8080 > /tmp/backend.log 2>&1 &

    BACKEND_PID=$!
    echo $BACKEND_PID > "$PID_DIR/backend.pid"
    echo -e "  FastAPI 启动中 (PID: $BACKEND_PID)..."

    # 等待 FastAPI 就绪
    for i in $(seq 1 30); do
        if curl -s http://localhost:8080/api/health > /dev/null 2>&1; then
            echo -e "  ${GREEN}✓${NC} FastAPI 已就绪 (${i}s)"
            break
        fi
        sleep 1
        if [ $i -eq 30 ]; then
            echo -e "  ${YELLOW}⚠${NC} FastAPI 启动超时，请查看日志: tail -f /tmp/backend.log"
        fi
    done

    deactivate
fi

# ===== 3. 启动 Nginx =====
echo ""
echo -e "${YELLOW}[3/3] 启动 Nginx...${NC}"

if pgrep -x nginx > /dev/null; then
    echo -e "  Nginx 已在运行，重新加载配置..."
    sudo nginx -s reload
else
    sudo nginx -c /etc/nginx/nginx.conf
fi
echo -e "  ${GREEN}✓${NC} Nginx 已启动 (端口 80)"

# ===== 完成 =====
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✓ MyAgent 启动完成!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  访问地址:"
echo "    http://localhost            → 前端界面"
echo "    http://localhost/api/docs    → API 文档"
echo "    http://localhost/api/health  → 健康检查"
echo ""
echo "  日志:"
echo "    tail -f /tmp/llama.log   → llama-server 日志"
echo "    tail -f /tmp/backend.log → 后端日志"
echo ""
echo "  停止服务: bash stop.sh"
echo ""
