#!/bin/bash
# =============================================================================
# MyAgent 一键启动 — AMD Radeon Cloud / 本地 通用
# 用法: bash start.sh
# 自愈: 不管之前挂了什么僵尸进程/PID文件，都能干净启动
# =============================================================================

set +e  # 不能 set -e，任何一个 kill 失败不能阻止启动

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$SCRIPT_DIR/backend"
FRONTEND_DIR="$SCRIPT_DIR/frontend"
ENV_FILE="$BACKEND_DIR/.env"
LLAMA_DIR="$HOME/llama.cpp"
LLAMA_SERVER="$LLAMA_DIR/build/bin/llama-server"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  MyAgent 一键启动${NC}"
echo -e "${BLUE}========================================${NC}"

# ===== 0. 自愈清理 =====
echo -e "\n${YELLOW}[0/4] 清理残留进程...${NC}"
pkill -9 -f llama-server 2>/dev/null
pkill -9 -f uvicorn 2>/dev/null
rm -f /tmp/myagent/*.pid 2>/dev/null
sleep 2
echo -e "  ${GREEN}✓${NC} 已清理"

# ===== 0.5 模型路径：.env → 自动扫描 → 兜底 =====
if [ -f "$ENV_FILE" ]; then
    MODEL_FILE=$(grep "^LLAMA_MODEL=" "$ENV_FILE" | head -1 | cut -d= -f2-)
    CTX_SIZE=$(grep "^CTX_SIZE=" "$ENV_FILE" | head -1 | cut -d= -f2-)
    NGL=$(grep "^NGL=" "$ENV_FILE" | head -1 | cut -d= -f2-)
    LLAMA_PORT=$(grep "^LLAMA_PORT=" "$ENV_FILE" | head -1 | cut -d= -f2-)
fi
MODEL_FILE="${MODEL_FILE:-$(find "$LLAMA_DIR/models" -name "*.gguf" -type f 2>/dev/null | head -1)}"
MODEL_FILE="${MODEL_FILE:-$LLAMA_DIR/models/qwen2.5-14b-instruct-q4_k_m.gguf}"
CTX_SIZE="${CTX_SIZE:-8192}"; NGL="${NGL:-99}"; LLAMA_PORT="${LLAMA_PORT:-8000}"

echo -e "  ${GREEN}✓${NC} 模型: $(basename "$MODEL_FILE")"

# ===== 1. llama-server =====
echo -e "\n${YELLOW}[1/4] 启动 llama.cpp...${NC}"
if [ ! -f "$LLAMA_SERVER" ]; then
    LLAMA_SERVER=$(find "$LLAMA_DIR" -name "llama-server" -type f 2>/dev/null | head -1)
fi
if [ ! -f "$LLAMA_SERVER" ]; then
    echo -e "  ${RED}✗${NC} llama-server 未找到"
    exit 1
fi

MODEL_ALIAS=$(basename "$MODEL_FILE" .gguf | sed 's/-Q[0-9]_K_[ML]$//')
nohup "$LLAMA_SERVER" -m "$MODEL_FILE" -a "$MODEL_ALIAS" --port "$LLAMA_PORT" -c "$CTX_SIZE" -ngl "$NGL" > /tmp/llama.log 2>&1 &
echo -e "  llama-server PID: $!"

# 等待就绪
for i in $(seq 1 120); do
    if curl -s --max-time 3 "http://localhost:$LLAMA_PORT/v1/models" > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} llama-server 就绪 (${i}s)"
        break
    fi
    sleep 1
done

# ===== 2. FastAPI =====
echo -e "\n${YELLOW}[2/4] 启动 FastAPI 后端...${NC}"
cd "$BACKEND_DIR"
source venv/bin/activate 2>/dev/null || true
nohup uvicorn main:app --host 0.0.0.0 --port 8080 > /tmp/backend.log 2>&1 &
BACKEND_PID=$!
echo -e "  FastAPI PID: $BACKEND_PID"

for i in $(seq 1 30); do
    if curl -s --max-time 3 http://localhost:8080/api/health > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} FastAPI 就绪 (${i}s)"
        break
    fi
    sleep 1
done

# ===== 3. Nginx =====
echo -e "\n${YELLOW}[3/4] 启动 Nginx...${NC}"
WEB_ROOT="/var/www/myagent"
if [ -f "$FRONTEND_DIR/dist/index.html" ]; then
    mkdir -p "$WEB_ROOT" 2>/dev/null
    cp -r "$FRONTEND_DIR/dist/." "$WEB_ROOT/" 2>/dev/null || true
    chmod -R a+rX "$WEB_ROOT" 2>/dev/null || true
fi

if command -v nginx >/dev/null 2>&1; then
    # 确保 8088 端口监听
    grep -q "listen 8088" /etc/nginx/nginx.conf 2>/dev/null || \
        sed -i 's/listen 80;/listen 80;\n        listen 8088;/' /etc/nginx/nginx.conf
    absolute_redirect_off=$(grep -c "absolute_redirect off" /etc/nginx/nginx.conf)
    [ "$absolute_redirect_off" -eq 0 ] && sed -i 's/server_name localhost;/server_name localhost;\n        absolute_redirect off;/' /etc/nginx/nginx.conf
    nginx -s reload 2>/dev/null || nginx -c /etc/nginx/nginx.conf 2>/dev/null || true
    echo -e "  ${GREEN}✓${NC} Nginx 就绪"
fi

# ===== 4. 外部隧道 =====
echo -e "\n${YELLOW}[4/4] 外部访问隧道...${NC}"
export PATH="$HOME/.local/bin:$PATH"

# 自动安装 rc-tunnel（如果缺失）
if ! command -v rc-tunnel >/dev/null 2>&1; then
    if [ -f /var/run/secrets/frp-self-service/install ]; then
        bash /var/run/secrets/frp-self-service/install 2>/dev/null && \
            export PATH="$HOME/.local/bin:$PATH"
    elif command -v pip3 >/dev/null 2>&1 || command -v pip >/dev/null 2>&1; then
        pip3 install rc-tunnel 2>/dev/null || pip install rc-tunnel 2>/dev/null
    fi
fi

PUBLIC_URL=""
if command -v rc-tunnel >/dev/null 2>&1; then
    rc-tunnel stop 2>/dev/null; sleep 2
    nohup rc-tunnel expose --port 8088 > /tmp/rc-tunnel.log 2>&1 &
    for i in $(seq 1 10); do
        PUBLIC_URL=$(grep -oE 'https?://rc-[^ ]+' /tmp/rc-tunnel.log 2>/dev/null | head -1)
        [ -n "$PUBLIC_URL" ] && break
        sleep 2
    done
    if [ -n "$PUBLIC_URL" ]; then
        echo -e "  ${GREEN}✓${NC} 公网: $PUBLIC_URL"
    else
        echo -e "  ${YELLOW}⚠${NC} 隧道启动中，手动获取: rc-tunnel expose --port 8088"
    fi
else
    echo -e "  ${YELLOW}⚠${NC} 无隧道工具，仅本机访问 (localhost:8088)"
fi

# ===== 完成 =====
echo -e "\n${GREEN}========================================${NC}"
echo -e "${GREEN}  ✓ MyAgent 启动完成!${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "  后端: http://localhost:8080/api/health"
echo -e "  前端: http://localhost"
[ -n "$PUBLIC_URL" ] && echo -e "  ${BLUE}公网: $PUBLIC_URL${NC}"
echo -e "  ${GREEN}一键启动，干净利落。${NC}"
