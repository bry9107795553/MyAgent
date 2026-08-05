#!/bin/bash
# MyAgent 停止 — 不管有没有 PID 文件，一定停干净
set +e
GREEN='\033[0;32m'; NC='\033[0m'

echo "MyAgent 停止中..."

# 全杀，不纠结 PID
pkill -9 -f uvicorn 2>/dev/null
pkill -9 -f llama-server 2>/dev/null
pkill -9 -x nginx 2>/dev/null
rm -f /tmp/myagent/*.pid /run/nginx.pid 2>/dev/null
sleep 2

echo -e "  ${GREEN}✓${NC} 全部已停"
