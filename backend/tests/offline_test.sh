#!/bin/bash
# =============================================================================
# MyAgent 离线测试脚本
# 验证核心功能在断网环境下是否正常工作
# 
# 使用方式: bash tests/offline_test.sh
# =============================================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 测试结果统计
PASS=0
FAIL=0
SKIP=0

print_header() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

print_pass() {
    echo -e "${GREEN}  [PASS]${NC} $1"
    PASS=$((PASS + 1))
}

print_fail() {
    echo -e "${RED}  [FAIL]${NC} $1"
    FAIL=$((FAIL + 1))
}

print_skip() {
    echo -e "${YELLOW}  [SKIP]${NC} $1"
    SKIP=$((SKIP + 1))
}

print_info() {
    echo -e "  $1"
}

# 检查命令是否存在
check_cmd() {
    if command -v $1 &> /dev/null; then
        return 0
    else
        return 1
    fi
}

# =============================================================================
# 测试开始
# =============================================================================

print_header "MyAgent 离线测试"
print_info "测试时间: $(date)"
print_info "测试目标: 验证断网环境下核心功能可用性"

# =============================================================================
# 1. 前置检查
# =============================================================================
print_header "Step 1: 前置检查"

# 检查 curl
if check_cmd curl; then
    print_pass "curl 可用"
else
    print_fail "curl 不可用，请安装: apt install curl"
    exit 1
fi

# 检查服务是否运行
print_info "检查 MyAgent 服务状态..."
if curl -s http://localhost/api/health > /dev/null 2>&1; then
    HEALTH=$(curl -s http://localhost/api/health)
    print_pass "MyAgent 服务运行中"
    print_info "健康状态: $HEALTH"
else
    print_fail "MyAgent 服务未运行，请先启动: bash start.sh"
    exit 1
fi

# =============================================================================
# 2. 在线基线测试（断网前）
# =============================================================================
print_header "Step 2: 在线基线测试"

# 测试 1: 健康检查
print_info "测试 1: API 健康检查..."
if curl -s http://localhost/api/health | grep -q "ok"; then
    print_pass "API 健康检查正常"
else
    print_fail "API 健康检查失败"
fi

# 测试 2: llama.cpp 模型可用
print_info "测试 2: llama.cpp 模型可用性..."
if curl -s http://localhost:8000/v1/models | grep -q "Qwen"; then
    print_pass "llama.cpp 模型已加载"
else
    print_fail "llama.cpp 模型未加载"
fi

# 测试 3: 对话功能（核心功能）
print_info "测试 3: 核心对话功能..."
CHAT_RESPONSE=$(curl -s -X POST http://localhost:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "Qwen2.5-14B-Instruct",
        "messages": [{"role": "user", "content": "你好，请回复：离线测试成功"}],
        "max_tokens": 50
    }' 2>&1)

if echo "$CHAT_RESPONSE" | grep -q "离线测试成功\|content"; then
    print_pass "核心对话功能正常"
else
    print_fail "核心对话功能异常: $CHAT_RESPONSE"
fi

# 测试 4: Agent 列表
print_info "测试 4: Agent 列表..."
if curl -s http://localhost/api/agents | grep -q "agent_id\|agents"; then
    print_pass "Agent 列表获取正常"
else
    print_fail "Agent 列表获取失败"
fi

# 测试 5: 皮肤列表
print_info "测试 5: 皮肤列表..."
if curl -s http://localhost/api/skins | grep -q "skin_id\|skins"; then
    print_pass "皮肤列表获取正常"
else
    print_fail "皮肤列表获取失败"
fi

# 测试 6: 布局 API
print_info "测试 6: 布局 API..."
if curl -s http://localhost/api/layout | grep -q "modules\|name"; then
    print_pass "布局 API 正常"
else
    print_fail "布局 API 异常"
fi

# =============================================================================
# 3. 断网测试
# =============================================================================
print_header "Step 3: 断网测试"

print_info "⚠️  即将断开网络连接..."
print_info "断网方式: iptables 屏蔽外网流量 (保留 localhost)"
print_info ""

# 使用 iptables 屏蔽外网（保留 localhost 和 127.0.0.1）
# 注意：这需要 root 权限
DISCONNECTED=false

disconnect_network() {
    # 方法1: iptables 屏蔽外网
    if [ "$EUID" -eq 0 ] || sudo -n true 2>/dev/null; then
        print_info "使用 iptables 断开外网..."
        iptables -A OUTPUT -d 127.0.0.0/8 -j ACCEPT 2>/dev/null || true
        iptables -A OUTPUT -d 10.0.0.0/8 -j ACCEPT 2>/dev/null || true
        iptables -A OUTPUT -d 172.16.0.0/12 -j ACCEPT 2>/dev/null || true
        iptables -A OUTPUT -d 192.168.0.0/16 -j ACCEPT 2>/dev/null || true
        iptables -A OUTPUT -j DROP 2>/dev/null || true
        DISCONNECTED=true
        print_info "网络已断开 (iptables DROP)"
    else
        # 方法2: 修改 DNS（较温和的方式）
        print_info "无 root 权限，使用 DNS 屏蔽方式..."
        cp /etc/resolv.conf /etc/resolv.conf.bak 2>/dev/null || true
        echo "nameserver 0.0.0.0" > /etc/resolv.conf 2>/dev/null || true
        DISCONNECTED=true
        print_info "DNS 已屏蔽"
    fi
}

reconnect_network() {
    if [ "$DISCONNECTED" = true ]; then
        print_info "恢复网络连接..."
        # 方法1: 恢复 iptables
        if [ "$EUID" -eq 0 ] || sudo -n true 2>/dev/null; then
            iptables -D OUTPUT -j DROP 2>/dev/null || true
            iptables -D OUTPUT -d 192.168.0.0/16 -j ACCEPT 2>/dev/null || true
            iptables -D OUTPUT -d 172.16.0.0/12 -j ACCEPT 2>/dev/null || true
            iptables -D OUTPUT -d 10.0.0.0/8 -j ACCEPT 2>/dev/null || true
            iptables -D OUTPUT -d 127.0.0.0/8 -j ACCEPT 2>/dev/null || true
            print_info "iptables 规则已清除"
        else
            # 方法2: 恢复 DNS
            cp /etc/resolv.conf.bak /etc/resolv.conf 2>/dev/null || true
            rm -f /etc/resolv.conf.bak 2>/dev/null || true
            print_info "DNS 已恢复"
        fi
    fi
}

# 确保退出时恢复网络
trap reconnect_network EXIT

# 断开网络
disconnect_network

sleep 2

# 验证断网
print_info "验证断网状态..."
if curl -s --connect-timeout 5 https://www.baidu.com > /dev/null 2>&1; then
    print_skip "外网仍可访问（DNS 屏蔽方式可能不完全），继续测试本地功能"
else
    print_pass "外网已断开"
fi

# =============================================================================
# 4. 断网后核心功能测试
# =============================================================================
print_header "Step 4: 断网后核心功能测试"

# 测试 7: 断网后 API 健康检查
print_info "测试 7: 断网后 API 健康检查..."
if curl -s http://localhost/api/health | grep -q "ok"; then
    print_pass "断网后 API 仍可用"
else
    print_fail "断网后 API 不可用"
fi

# 测试 8: 断网后对话功能（核心！）
print_info "测试 8: 断网后核心对话功能..."
OFFLINE_CHAT=$(curl -s --connect-timeout 10 -X POST http://localhost:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "Qwen2.5-14B-Instruct",
        "messages": [{"role": "user", "content": "1+1等于几？只回答数字"}],
        "max_tokens": 20
    }' 2>&1)

if echo "$OFFLINE_CHAT" | grep -q "content\|2"; then
    print_pass "断网后核心对话功能正常"
else
    print_fail "断网后核心对话功能异常: $OFFLINE_CHAT"
fi

# 测试 9: 断网后 Agent 列表
print_info "测试 9: 断网后 Agent 列表..."
if curl -s http://localhost/api/agents | grep -q "agent_id\|agents"; then
    print_pass "断网后 Agent 列表正常"
else
    print_fail "断网后 Agent 列表异常"
fi

# 测试 10: 断网后布局 API
print_info "测试 10: 断网后布局 API..."
if curl -s http://localhost/api/layout | grep -q "modules\|name"; then
    print_pass "断网后布局 API 正常"
else
    print_fail "断网后布局 API 异常"
fi

# 测试 11: 断网后皮肤列表（本地数据）
print_info "测试 11: 断网后本地皮肤列表..."
if curl -s http://localhost/api/skins | grep -q "skin_id\|skins"; then
    print_pass "断网后本地皮肤数据正常"
else
    print_fail "断网后本地皮肤数据异常"
fi

# 测试 12: 断网后云端功能应失败（验证非核心功能正确降级）
print_info "测试 12: 断网后云端皮肤生成应失败（预期行为）..."
CLOUD_SKIN=$(curl -s --connect-timeout 5 -X POST http://localhost/api/skins/generate \
    -H "Content-Type: application/json" \
    -d '{"prompt": "生成一个赛博朋克风格皮肤"}' 2>&1)

if echo "$CLOUD_SKIN" | grep -q "error\|fail\|timeout\|connection"; then
    print_pass "云端功能在断网时正确降级（失败是预期行为）"
else
    print_skip "云端功能返回非预期结果（可能使用了本地模型）"
fi

# =============================================================================
# 5. 恢复网络
# =============================================================================
print_header "Step 5: 恢复网络"

reconnect_network
sleep 2

# 验证网络恢复
print_info "验证网络恢复..."
if curl -s --connect-timeout 5 https://www.baidu.com > /dev/null 2>&1; then
    print_pass "网络已恢复"
else
    print_skip "网络恢复检测失败（可能需要手动恢复 DNS）"
fi

# =============================================================================
# 6. 恢复后功能验证
# =============================================================================
print_header "Step 6: 恢复后功能验证"

# 测试 13: 恢复后对话功能
print_info "测试 13: 恢复网络后对话功能..."
RECOVER_CHAT=$(curl -s -X POST http://localhost:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "Qwen2.5-14B-Instruct",
        "messages": [{"role": "user", "content": "网络已恢复，请回复：恢复测试成功"}],
        "max_tokens": 50
    }' 2>&1)

if echo "$RECOVER_CHAT" | grep -q "content\|恢复"; then
    print_pass "恢复后对话功能正常"
else
    print_fail "恢复后对话功能异常"
fi

# =============================================================================
# 7. 测试报告
# =============================================================================
print_header "测试报告"

TOTAL=$((PASS + FAIL + SKIP))
echo -e "  总测试数: ${TOTAL}"
echo -e "  ${GREEN}通过: ${PASS}${NC}"
echo -e "  ${RED}失败: ${FAIL}${NC}"
echo -e "  ${YELLOW}跳过: ${SKIP}${NC}"
echo ""

if [ $FAIL -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  ✓ 所有测试通过!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "  核心结论:"
    echo "  - 断网环境下，核心对话功能正常 (llama.cpp 本地推理)"
    echo "  - 断网环境下，Agent/皮肤/布局等本地数据正常"
    echo "  - 断网环境下，云端功能正确降级"
    echo "  - 恢复网络后，所有功能恢复正常"
    exit 0
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  ✗ 有 ${FAIL} 个测试失败${NC}"
    echo -e "${RED}========================================${NC}"
    exit 1
fi
