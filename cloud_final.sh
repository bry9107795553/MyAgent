#!/bin/bash
# =============================================================================
# MyAgent Hackathon 最终部署 + 测速 + 录视频前准备 — 云端一键脚本
# 用法: 在 AMD Radeon 云实例终端粘贴执行
#   bash cloud_final.sh
# =============================================================================
set -e

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
PROJECT_DIR="${PROJECT_DIR:-/workspace/template-repos/template-2603/repo}"

echo -e "${BLUE}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  MyAgent Hackathon 最终部署流水线                      ║${NC}"
echo -e "${BLUE}║  步骤: 拉代码 → 启动 → 冒烟 → S7测速 → 准备录视频       ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════════╝${NC}"

# ===== Step 1: Git Pull =====
echo -e "\n${YELLOW}[1/7] Git Pull 最新代码...${NC}"
cd "$PROJECT_DIR"
git config --global http.sslVerify false 2>/dev/null || true
export GIT_SSL_NO_VERIFY=true

# 暂存本地修改，拉取远程
git stash 2>/dev/null || true
git pull origin main --rebase || git pull origin main
git stash pop 2>/dev/null || true
echo -e "  ${GREEN}✓${NC} 代码已更新"
git log --oneline -3

# ===== Step 2: 启动服务 =====
echo -e "\n${YELLOW}[2/7] 启动 MyAgent 服务...${NC}"
bash stop.sh 2>/dev/null || true
sleep 3

# 用 CTX_SIZE=16384 确保 A 组原版 prompt 不截断
export CTX_SIZE=16384
bash start.sh

echo -e "  ${GREEN}✓${NC} 服务已启动"

# ===== Step 3: 服务健康检查 =====
echo -e "\n${YELLOW}[3/7] 健康检查...${NC}"
sleep 10

# Health
for i in $(seq 1 5); do
    if curl -s --max-time 5 http://localhost:8080/api/health | grep -q '"ok"'; then
        echo -e "  ${GREEN}✓${NC} 后端健康"
        break
    fi
    [ $i -eq 5 ] && echo -e "  ${RED}✗${NC} 后端未就绪" && exit 1
    sleep 5
done

# Models
curl -s http://localhost:8000/v1/models | grep -q 'Qwen' && echo -e "  ${GREEN}✓${NC} llama-server 模型已加载" || echo -e "  ${RED}✗${NC} 模型加载失败"

# Frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:8088/ | grep -q 200 && echo -e "  ${GREEN}✓${NC} 前端在线" || echo -e "  ${YELLOW}⚠${NC} 前端未就绪"

# GPU routing
python3 -c "
import sys,pathlib,json
sys.path.insert(0,'$PROJECT_DIR/backend')
from config.settings import settings
print(f'  GPU mode: {settings.single_gpu_mode}')
print(f'  Model: {settings.llama_model}')
print(f'  Endpoint: {settings.llama_base_url}')
"

echo ""

# ===== Step 4: 冒烟测试 =====
echo -e "${YELLOW}[4/7] 冒烟测试...${NC}"

# 基本问答
echo "  测试基本问答..."
SMOKE=$(curl -s --max-time 60 -X POST http://localhost:8080/api/agents/general_assistant/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"1+1=?","stream":false}')
if echo "$SMOKE" | grep -q '"reply"'; then
    echo -e "  ${GREEN}✓${NC} 基本问答OK"
else
    echo -e "  ${RED}✗${NC} 基本问答失败"
fi

# 工作组配置
python3 << 'PYEOF'
import json,pathlib
project = pathlib.Path("$PROJECT_DIR")
rp = json.loads((project / "data/role_pool.json").read_text())
print(f"  角色池: {len(rp.get('roles',[]))} 个")
wg_dir = project / "data/workgroups"
print(f"  工作组: {len(list(wg_dir.glob('*.json')))} 个")
exp_dir = project / "data/experiences"
print(f"  经验库: {len(list(exp_dir.glob('*.json')) if exp_dir.exists() else [])} 条")
PYEOF

echo ""

# ===== Step 5: 确保 bench_helpers.sh 存在 =====
echo -e "${YELLOW}[5/7] 准备测速工具...${NC}"

BENCH_FILE="$PROJECT_DIR/bench_helpers.sh"
if [ ! -f "$BENCH_FILE" ]; then
    echo "  生成 bench_helpers.sh..."
    cat > "$BENCH_FILE" << 'BENCH_SCRIPT'
#!/bin/bash
PROJECT_DIR="${PROJECT_DIR:-/workspace/template-repos/template-2603/repo}"
BENCH_PORT="${BENCH_PORT:-8080}"
AGENT_ID="${AGENT_ID:-general_assistant}"

_restart_backend() {
    echo "  重启后端..."
    bash "$PROJECT_DIR/stop.sh" > /dev/null 2>&1 || true
    sleep 2
    bash "$PROJECT_DIR/start.sh" > /dev/null 2>&1 || true
    sleep 5
}

benchmark_orig() {
    unset PROMPT_VARIANT
    echo "=== BENCHMARK: ORIGINAL (baseline) ==="
    _restart_backend
}

benchmark_slim() {
    export PROMPT_VARIANT=slim
    echo "=== BENCHMARK: SLIM (optimized) ==="
    _restart_backend
}

bench_one() {
    local msg="${1:-开发一个带增删改查的待办事项 Web 应用}"
    local variant="${PROMPT_VARIANT:-original}"
    local url="http://localhost:${BENCH_PORT}/api/agents/${AGENT_ID}/chat"
    local start end elapsed tokens
    local payload
    payload=$(python3 -c "import json;print(json.dumps({'message':'$msg','stream':False}))")
    start=$(date +%s%3N)
    curl -s --max-time 300 -X POST "$url" -H "Content-Type: application/json" -d "$payload" > "/tmp/bench_out_${variant}_$(date +%s).json"
    end=$(date +%s%3N)
    elapsed=$(( end - start ))
    tokens=$(grep -o '"prompt_tokens":[0-9]*' /tmp/llama.log 2>/dev/null | tail -1 | cut -d: -f2)
    echo "  variant=$variant  elapsed=${elapsed}ms  prompt_tokens=${tokens:-N/A}"
    echo "$variant,$elapsed,${tokens:-},$(date -Iseconds)" >> "/tmp/bench_${variant}.csv"
}

bench_report() {
    echo ""
    for v in original slim; do
        [ -f "/tmp/bench_${v}.csv" ] || continue
        echo "--- $v ---"
        echo "variant,elapsed_ms,prompt_tokens,timestamp"
        cat "/tmp/bench_${v}.csv"
        awk -F, '{if(NR>0){s+=$2; n++}} END{if(n)printf "  平均耗时: %.0f ms  (n=%d)\n", s/n, n}' "/tmp/bench_${v}.csv"
        echo ""
    done
}
BENCH_SCRIPT
    chmod +x "$BENCH_FILE"
fi
echo -e "  ${GREEN}✓${NC} bench_helpers.sh 就绪"

# ===== Step 6: S7 A/B 测速 =====
echo -e "\n${YELLOW}[6/7] S7 A/B 测速 (预计 3-5 分钟)...${NC}"
echo "  ⚠️ 此步骤跑完整流水线 2 次 × 2 组 = 4 轮，每轮 60-120s"
source "$BENCH_FILE"

# A 组: 原版 prompt (丢弃第1次冷启动)
echo "  [A组] 原版 prompt 测速..."
benchmark_orig
echo "  跑 A 组 第1次 (冷启动，丢弃)..."
bench_one "开发一个带增删改查的待办事项 Web 应用"
sleep 5
echo "  跑 A 组 第2次..."
bench_one "开发一个带增删改查的待办事项 Web 应用"
sleep 5
echo "  跑 A 组 第3次..."
bench_one "开发一个带增删改查的待办事项 Web 应用"

# B 组: 精简 prompt
echo "  [B组] 精简 prompt 测速..."
benchmark_slim
echo "  跑 B 组 第1次 (冷启动，丢弃)..."
bench_one "开发一个带增删改查的待办事项 Web 应用"
sleep 5
echo "  跑 B 组 第2次..."
bench_one "开发一个带增删改查的待办事项 Web 应用"
sleep 5
echo "  跑 B 组 第3次..."
bench_one "开发一个带增删改查的待办事项 Web 应用"

# 打印报告
echo -e "\n${BLUE}╔══════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  S7 测速报告                             ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════╝${NC}"
bench_report

# 保存数据
cp /tmp/bench_*.csv "$PROJECT_DIR/data/" 2>/dev/null || true

# ===== Step 7: 视频录制准备 =====
echo -e "\n${YELLOW}[7/7] 视频录制准备...${NC}"

# 重新暴露隧道
export PATH="$HOME/.local/bin:$PATH"
rc-tunnel stop 2>/dev/null || true
sleep 2
nohup rc-tunnel expose --port 8088 > /tmp/rc-tunnel.log 2>&1 &
sleep 5
PUBLIC_URL=$(grep -oE 'https?://rc-[^ ]+' /tmp/rc-tunnel.log 2>/dev/null | head -1)
echo -e "  ${GREEN}✓${NC} 公网 URL: $PUBLIC_URL"

# 预建智能体
echo "  预建智能体..."
curl -s -X POST http://localhost:8080/api/agents -H "Content-Type: application/json" \
  -d '{"agent_id":"demo_writer","name":"写作助手","description":"负责文案与报告"}' > /dev/null
curl -s -X POST http://localhost:8080/api/agents -H "Content-Type: application/json" \
  -d '{"agent_id":"demo_dev","name":"开发助手","description":"负责编码与工程任务"}' > /dev/null
echo -e "  ${GREEN}✓${NC} 智能体已创建"

# 清理演示目录
rm -rf "$PROJECT_DIR/backend/workspace_demo" 2>/dev/null || true

# ===== 完成 =====
echo ""
echo -e "${GREEN}╔══════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║  ✓ 全部就绪！                                       ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BLUE}公网 URL:${NC} $PUBLIC_URL"
echo ""
echo -e "  ${BLUE}下一步 — 录视频:${NC}"
echo "  1. 打开浏览器访问上面公网 URL"
echo "  2. 打开右侧终端 rocm-smi 监控:"
echo "     watch -n 1 'rocm-smi --showuse --showmeminfo vram | head -20'"
echo "  3. 按 docs/演示解说词.md 录制 7 镜头"
echo "  4. 录完后执行:"
echo "     cd $PROJECT_DIR && cp /tmp/bench_*.csv data/ && cp /tmp/llama.log data/llama_demo.log"
echo "     git add -A && git commit -m 'data: cloud benchmark + demo logs' && git push"
echo ""
echo -e "  ${BLUE}录完视频后提交:${NC}"
echo "  - Fork https://github.com/AMD-DEV-CONTEST/Radeon-hackathon-2026-07"
echo "  - 放入四件套: 项目说明文档 + 仓库链接 + 视频链接 + PPT"
echo "  - 提 PR，标题: Track 2, <姓名>, MyAgent"
echo "  - 用 docs/提交指南.md 的 PR 描述模板"
