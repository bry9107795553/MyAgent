#!/bin/bash
# ============================================================
# MyAgent 云端部署 + B1/B2 验证 + S7 测速 一键脚本
# 用法: 在 AMD 云端终端粘贴执行
#   bash deploy_and_test.sh
# ============================================================
set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'

PROJECT_DIR="${PROJECT_DIR:-/workspace/template-repos/template-2603/repo}"

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}  MyAgent 部署 + 验证 + 测速${NC}"
echo -e "${BLUE}============================================${NC}"

# ===== Step 1: 拉取最新代码 =====
echo -e "\n${YELLOW}[1/5] 拉取最新代码 (含 B3 记忆修复)...${NC}"
cd "$PROJECT_DIR"
git config --global http.sslVerify false 2>/dev/null || true
export GIT_SSL_NO_VERIFY=true
git pull origin main
echo -e "  ${GREEN}✓${NC} 代码已更新"
git log --oneline -3

# ===== Step 2: 重启服务 =====
echo -e "\n${YELLOW}[2/5] 重启服务...${NC}"
bash stop.sh 2>/dev/null || true
sleep 2
bash start.sh
echo -e "  ${GREEN}✓${NC} 服务已重启"

# ===== Step 3: 冒烟测试 =====
echo -e "\n${YELLOW}[3/5] 冒烟测试...${NC}"
sleep 5

API="http://localhost:8080"

# Health check
if curl -s --max-time 5 "$API/api/health" | grep -q '"ok"'; then
    echo -e "  ${GREEN}✓${NC} 后端健康检查通过"
else
    echo -e "  ${RED}✗${NC} 后端未就绪，等待..."
    sleep 30
    curl -s --max-time 5 "$API/api/health" | grep -q '"ok"' && echo -e "  ${GREEN}✓${NC} 后端已就绪" || echo -e "  ${RED}✗${NC} 后端仍未就绪"
fi

# B3 记忆测试
echo -e "\n${YELLOW}[3a] B3 多轮记忆验证...${NC}"
SESSION1=$(curl -s -X POST "$API/api/agents/general_assistant/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"我叫张三，我喜欢Python","stream":false}')
echo "  Q: 我叫张三，我喜欢Python"
echo "  A: $(echo "$SESSION1" | python3 -c "import sys,json; print(json.load(sys.stdin).get('reply','N/A')[:200])" 2>/dev/null || echo 'parse error')"

sleep 2
SESSION2=$(curl -s -X POST "$API/api/agents/general_assistant/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"我叫什么名字？","stream":false}')
echo "  Q: 我叫什么名字？"
echo "  A: $(echo "$SESSION2" | python3 -c "import sys,json; print(json.load(sys.stdin).get('reply','N/A')[:200])" 2>/dev/null || echo 'parse error')"

if echo "$SESSION2" | grep -qi "张三"; then
    echo -e "  ${GREEN}✓${NC} B3 记忆测试通过！(记住'张三')"
else
    echo -e "  ${RED}✗${NC} B3 记忆测试失败 (未记住'张三')"
fi

# B1+B2 流水线测试
echo -e "\n${YELLOW}[3b] B1/B2 流水线+HTML预览验证...${NC}"
echo "  发送: 开发一个网页版计算器"
START=$(date +%s)
PIPE_RESULT=$(curl -s --max-time 300 -X POST "$API/api/agents/general_assistant/chat" \
  -H "Content-Type: application/json" \
  -d '{"message":"开发一个网页版计算器","stream":false}')
END=$(date +%s)
ELAPSED=$((END - START))
echo "  耗时: ${ELAPSED}s"

# 检查 __PIPE__ 标记
PIPE_COUNT=$(echo "$PIPE_RESULT" | grep -o '__PIPE__' | wc -l)
echo "  __PIPE__ 标记数: $PIPE_COUNT (期望 ≥ 4)"

# 检查 HTML 输出
if echo "$PIPE_RESULT" | grep -qi '```html\|<!DOCTYPE\|<html'; then
    echo -e "  ${GREEN}✓${NC} B2 HTML 预览: 检测到 HTML 代码"
else
    echo -e "  ${YELLOW}⚠${NC} B2 HTML: 未检测到 HTML (可能被严格过滤)"
fi

# ===== Step 4: S7 A/B 测速 =====
echo -e "\n${YELLOW}[4/5] S7 A/B 测速...${NC}"
BENCH_DIR="$PROJECT_DIR"
source "$BENCH_DIR/bench_helpers.sh" 2>/dev/null || {
    echo "  创建 bench_helpers.sh..."
    cat > "$BENCH_DIR/bench_helpers.sh" << 'BENCH_SCRIPT'
#!/bin/bash
# === A/B Benchmark Helper ===
MYAGENT_DIR="${MYAGENT_DIR:-$HOME/myagent}"
PROJECT_DIR="${PROJECT_DIR:-/workspace/template-repos/template-2603/repo}"
BENCH_PORT="${BENCH_PORT:-8080}"
AGENT_ID="${AGENT_ID:-general_assistant}"

_restart_backend() {
    echo "  重启后端以加载新的 PROMPT_VARIANT..."
    bash "$PROJECT_DIR/stop.sh" > /dev/null 2>&1 || true
    sleep 2
    bash "$PROJECT_DIR/start.sh" > /dev/null 2>&1 || true
    sleep 5
}

benchmark_slim() {
    export PROMPT_VARIANT=slim
    echo "=== BENCHMARK: SLIM (optimized) prompts ==="
    echo "PROMPT_VARIANT=$PROMPT_VARIANT"
    _restart_backend
}

benchmark_orig() {
    unset PROMPT_VARIANT
    echo "=== BENCHMARK: ORIGINAL (baseline) prompts ==="
    echo "PROMPT_VARIANT=${PROMPT_VARIANT:-default}"
    _restart_backend
}

bench_one() {
    local msg="${1:-开发一个带增删改查的待办事项 Web 应用}"
    local variant="${PROMPT_VARIANT:-original}"
    local url="http://localhost:${BENCH_PORT}/api/agents/${AGENT_ID}/chat"
    local payload start end elapsed tokens

    payload=$(MSG="$msg" python3 -c 'import json,os;print(json.dumps({"message":os.environ["MSG"],"stream":False}))')

    start=$(date +%s%3N)
    curl -s --max-time 300 -X POST "$url" -H "Content-Type: application/json" -d "$payload" \
        > "/tmp/bench_out_${variant}.json"
    end=$(date +%s%3N)
    elapsed=$(( end - start ))

    tokens=$(grep -o '"prompt_tokens":[0-9]*' /tmp/llama.log 2>/dev/null | tail -1 | cut -d: -f2)

    echo "variant=$variant  elapsed=${elapsed}ms  prompt_tokens=${tokens:-N/A}"
    echo "$variant,$elapsed,${tokens:-},$(date -Iseconds)" >> "/tmp/bench_${variant}.csv"
}

bench_report() {
    local v
    for v in original slim; do
        [ -f "/tmp/bench_${v}.csv" ] || continue
        echo "--- $v ---"
        echo "variant,elapsed_ms,prompt_tokens,timestamp"
        cat "/tmp/bench_${v}.csv"
        awk -F, '{s+=$2; n++} END{if(n)printf "  平均耗时: %.0f ms  (n=%d)\n", s/n, n}' "/tmp/bench_${v}.csv"
    done
}
BENCH_SCRIPT
    chmod +x "$BENCH_DIR/bench_helpers.sh"
    source "$BENCH_DIR/bench_helpers.sh"
}

# A 组: 原版 prompt
benchmark_orig
echo "  跑 A 组 (origin) 2 次..."
bench_one "开发一个带增删改查的待办事项 Web 应用"
sleep 3
bench_one "开发一个带增删改查的待办事项 Web 应用"

# B 组: 精简 prompt
benchmark_slim
echo "  跑 B 组 (slim) 2 次..."
bench_one "开发一个带增删改查的待办事项 Web 应用"
sleep 3
bench_one "开发一个带增删改查的待办事项 Web 应用"

echo -e "\n${BLUE}=== S7 测速报告 ===${NC}"
bench_report

# ===== Step 5: 完成 =====
echo -e "\n${GREEN}============================================${NC}"
echo -e "${GREEN}  部署 + 验证 + 测速 完成！${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo "  公网 URL (查看 rc-tunnel 日志):"
echo "    grep -oE 'https?://rc-[^ ]+' /tmp/rc-tunnel.log | head -1"
echo ""
echo "  下一步:"
echo "    - 验证 B1: 观察流水线面板逐角色亮起 (__PIPE__ 标记数)"
echo "    - 验证 B2: 检查预览 Tab 是否有 HTML 页面"
echo "    - 验证 B3: 记忆测试 '我叫张三'/'我叫什么'"
echo "    - S7 数据: 查看上方 bench_report 输出"
echo "    - 录视频: 按 docs/演示解说词.md 7 镜头录制"
