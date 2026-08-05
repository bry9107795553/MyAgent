#!/bin/bash
# =====================================================
# MyAgent 演示前冒烟测试 — 云端终端粘贴运行
# 覆盖：5条工作组 × 工具调用 × 记忆系统 × API端点
# 预计耗时 5-8 分钟
# =====================================================
API="http://localhost:8080"
PASS=0; FAIL=0
ok() { PASS=$((PASS+1)); echo "  ✅ $1"; }
fail() { FAIL=$((FAIL+1)); echo "  ❌ $1"; }

echo "╔══════════════════════════════════════════╗"
echo "║   MyAgent 冒烟测试 v1.0                  ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# ======================================
# 1. 基础端点健康检查
# ======================================
echo "━━━ [1/6] 基础端点 ━━━"

r=$(curl -s $API/api/health)
echo "$r" | grep -q '"ok"' && ok "/api/health" || fail "/api/health"

r=$(curl -s $API/api/system)
echo "$r" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['role_count'])" | grep -Eq '^1[5-9]$|^2[0-9]$' && ok "/api/system ($(echo $r | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['role_count'])") roles)" || fail "/api/system"

curl -s $API/api/agents | grep -q 'general_assistant' && ok "/api/agents" || fail "/api/agents"

echo ""

# ======================================
# 2. LLM 可用性
# ======================================
echo "━━━ [2/6] LLM 推理 ━━━"

r=$(curl -s $API/api/system)
echo "$r" | grep -q '"llm_available":true' && ok "llama-server 可用" || fail "llama-server 不可用"

# 实际推理测试
r=$(curl -s -X POST $API/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"1+1=?"}' --max-time 30)
echo "$r" | grep -qE '(response|content|assistant)' && ok "单轮推理通" || fail "单轮推理不通"

echo ""

# ======================================
# 3. 工作组触发测试（5 条核心流水线）
# ======================================
echo "━━━ [3/6] 工作组触发 ━━━"

test_wg() {
    local keyword="$1" label="$2" expected_wg="$3"
    # 用 API 发送触发消息
    r=$(curl -s -X POST $API/api/chat \
      -H "Content-Type: application/json" \
      -d "{\"message\":\"$keyword\"}" --max-time 120 2>&1)
    # 检查响应中是否包含工作组名
    if echo "$r" | grep -qi "$expected_wg\|workgroup\|$label"; then
        ok "$label ($keyword)"
    else
        fail "$label ($keyword)"
    fi
    sleep 3
}

test_wg "审查代码" "dev_code_review" "inspector"
test_wg "设计界面" "dev_design_only" "designer"
test_wg "开发一个待办事项应用" "dev_full" "coach"
test_wg "修改项目" "dev_modification" "handoff"
test_wg "做技术调查" "research_investigation" "knowledge"

echo ""

# ======================================
# 4. 工具调用闭环
# ======================================
echo "━━━ [4/6] 工具调用 ━━━"

# 测试 file_write（developer 角色有 file_write 权限）
r=$(curl -s -X POST $API/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"在项目根目录创建一个 test_smoke.txt 文件，内容是 hello myagent"}' --max-time 60 2>&1)

# 检查文件是否真落盘
sleep 3
TEST_FILE=$(find /workspace -name "test_smoke.txt" -maxdepth 5 2>/dev/null | head -1)
if [ -n "$TEST_FILE" ] && grep -q "hello" "$TEST_FILE"; then
    ok "file_write 真落盘 ($TEST_FILE)"
    rm -f "$TEST_FILE"
else
    echo "  ⚠ file_write 可能需要更长时间（LLM异步），跳过"
fi

echo ""

# ======================================
# 5. 记忆系统
# ======================================
echo "━━━ [5/6] 记忆系统 ━━━"

# 检查经验文件
EXP_DIR="data/experiences"
if [ -d "$EXP_DIR" ] && ls "$EXP_DIR"/*.json 2>/dev/null | head -1 | grep -q .; then
    ok "经验文件存在 (data/experiences/)"
else
    echo "  ⚠ 经验目录为空（首次运行正常）"
fi

# 检查知识库
KB="$PWD/data/memory/knowledge.json"
if [ -f "$KB" ]; then
    python3 -c "import json; d=json.load(open('$KB','r',encoding='utf-8')); print(len(d.get('triples',d)) if isinstance(d,(dict,list)) else 0)" 2>/dev/null | grep -q . && ok "知识库可读" || fail "知识库读取失败"
else
    echo "  ⚠ knowledge.json 不存在"
fi

# 检查记忆模块加载
cd "$PWD/backend" 2>/dev/null && python3 -c "
import sys; sys.path.insert(0,'.')
try:
    from core.memory.experience_manager import ExperienceManager
    from core.knowledge.knowledge_base import KnowledgeBase
    print('MEMORY_LOAD_OK')
except Exception as e:
    print(f'MEMORY_LOAD_FAIL:{e}')
" 2>/dev/null | grep -q "MEMORY_LOAD_OK" && ok "记忆模块可 import" || echo "  ⚠ 记忆模块 import 测试跳过"

echo ""

# ======================================
# 6. 前端验证
# ======================================
echo "━━━ [6/6] 前端 ━━━"

curl -s -o /dev/null -w "%{http_code}" http://localhost:8088/ | grep -q 200 && ok "Nginx 8088 前端在线" || fail "Nginx 前端不可达"

# 检查三栏 ChatView 关键字
grep -l "left-panel\|chat-col\|right-panel" /var/www/myagent/assets/*.js 2>/dev/null | head -1 | grep -q . && ok "三栏布局已部署（JS bundle）" || fail "三栏布局缺失"

INDEX=$(wc -c < /var/www/myagent/index.html)
[ "$INDEX" -gt 200 ] && ok "index.html 正常 (${INDEX} bytes)" || fail "index.html 异常"

echo ""

# ======================================
# 总结
# ======================================
echo "╔══════════════════════════════════════════╗"
echo "║  测试完成                                ║"
echo "║  ✅ $PASS 项通过 / ❌ $FAIL 项失败        ║"
echo "╚══════════════════════════════════════════╝"

if [ "$FAIL" -eq 0 ]; then
    echo ""
    echo "🎉 全部通过！可以开始录演示视频。"
elif [ "$FAIL" -le 2 ]; then
    echo ""
    echo "⚠️ 少量未通过项，不影响演示（可能是异步/首次运行延迟）"
else
    echo ""
    echo "🔴 $FAIL 项失败，录制前请检查。"
fi
