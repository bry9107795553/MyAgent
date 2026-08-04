#!/bin/bash
# =============================================================================
# MyAgent 停止脚本
# 停止: Nginx → FastAPI → llama-server
# 使用方式: bash stop.sh
# =============================================================================

set -e

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PID_DIR="/tmp/myagent"

echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}  MyAgent 停止服务${NC}"
echo -e "${YELLOW}========================================${NC}"

# ===== 1. 停止 Nginx =====
echo ""
echo -e "  [1/3] 停止 Nginx..."
if pgrep -x nginx > /dev/null; then
    if [ "$(id -u)" -eq 0 ] || ! command -v sudo >/dev/null 2>&1; then SUDO=""; else SUDO="sudo"; fi
    $SUDO nginx -s stop 2>/dev/null || true
    sleep 1
    # 优雅停止常留下 worker 残渣，导致下次 start 的 pgrep 误判为"仍在运行"
    # 而去 reload（此时 /run/nginx.pid 已消失，必然失败）。这里强杀到干净为止。
    if pgrep -x nginx > /dev/null; then
        $SUDO pkill -9 -x nginx 2>/dev/null || true
        sleep 1
    fi
    $SUDO rm -f /run/nginx.pid 2>/dev/null || true
    echo -e "  ${GREEN}✓${NC} Nginx 已停止"
else
    echo -e "  Nginx 未运行"
fi

# ===== 2. 停止 FastAPI =====
echo ""
echo -e "  [2/3] 停止 FastAPI..."
if [ -f "$PID_DIR/backend.pid" ]; then
    PID=$(cat "$PID_DIR/backend.pid")
    if kill -0 $PID 2>/dev/null; then
        kill $PID
        sleep 2
        kill -9 $PID 2>/dev/null || true
        echo -e "  ${GREEN}✓${NC} FastAPI 已停止 (PID: $PID)"
    else
        echo -e "  FastAPI 进程不存在"
    fi
    rm -f "$PID_DIR/backend.pid"
else
    # 尝试通过进程名停止
    if pgrep -f "uvicorn main:app" > /dev/null; then
        pkill -f "uvicorn main:app"
        echo -e "  ${GREEN}✓${NC} FastAPI 已停止"
    else
        echo -e "  FastAPI 未运行"
    fi
fi

# ===== 3. 停止 llama-server =====
echo ""
echo -e "  [3/3] 停止 llama-server..."
if [ -f "$PID_DIR/llama.pid" ]; then
    PID=$(cat "$PID_DIR/llama.pid")
    if kill -0 $PID 2>/dev/null; then
        kill $PID
        sleep 3
        kill -9 $PID 2>/dev/null || true
        echo -e "  ${GREEN}✓${NC} llama-server 已停止 (PID: $PID)"
    else
        echo -e "  llama-server 进程不存在"
    fi
    rm -f "$PID_DIR/llama.pid"
else
    # 兼容旧版 PID 文件
    if [ -f "$PID_DIR/vllm.pid" ]; then
        PID=$(cat "$PID_DIR/vllm.pid")
        kill $PID 2>/dev/null || true
        rm -f "$PID_DIR/vllm.pid"
    fi
    if pgrep -f "llama-server" > /dev/null; then
        pkill -f "llama-server"
        echo -e "  ${GREEN}✓${NC} llama-server 已停止"
    elif pgrep -f "vllm" > /dev/null; then
        pkill -f "vllm"
        echo -e "  ${GREEN}✓${NC} 残留 vLLM 进程已停止"
    else
        echo -e "  llama-server 未运行"
    fi
fi

# ===== 完成 =====
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✓ 所有服务已停止${NC}"
echo -e "${GREEN}========================================${NC}"
