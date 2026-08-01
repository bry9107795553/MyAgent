#!/bin/bash
# =============================================================================
# MyAgent 一键安装脚本 — AMD Radeon Cloud 直接部署（无 Docker）
# 在 Radeon Cloud 实例上运行此脚本完成全部安装
#
# 使用方式:
#   git clone https://github.com/bry9107795553/MyAgent.git
#   cd MyAgent/myagent
#   bash install.sh
# =============================================================================

set -e

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  MyAgent 一键安装${NC}"
echo -e "${BLUE}  AMD Radeon Cloud (无 Docker)${NC}"
echo -e "${BLUE}========================================${NC}"

# 获取脚本所在目录的绝对路径
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo -e "  安装目录: ${SCRIPT_DIR}"

# ===== 1. 检查 GPU 和 ROCm =====
echo ""
echo -e "${YELLOW}[1/7] 检查 GPU 和 ROCm 环境...${NC}"

if command -v rocminfo &> /dev/null; then
    GPU_COUNT=$(rocminfo | grep -c "Device Type")
    echo -e "  ${GREEN}✓${NC} ROCm 已安装，检测到 $GPU_COUNT 个 GPU 设备"
    ROCM_VERSION=$(cat /opt/rocm/.info/version 2>/dev/null || echo "unknown")
    echo -e "  ROCm 版本: $ROCM_VERSION"
else
    echo -e "  ${RED}✗${NC} 未检测到 ROCm，请确认 Radeon Cloud 实例已预装 ROCm 驱动"
    echo -e "  ${YELLOW}提示:${NC} Radeon Cloud 实例通常已预装 ROCm，如果未安装请联系平台"
    read -p "  是否继续安装? (y/N): " CONTINUE
    if [ "$CONTINUE" != "y" ] && [ "$CONTINUE" != "Y" ]; then
        echo "安装已取消"
        exit 1
    fi
fi

# ===== 2. 安装系统依赖 =====
echo ""
echo -e "${YELLOW}[2/7] 安装系统依赖...${NC}"

# 更新包管理器
sudo apt-get update -qq

# 安装基础工具
sudo apt-get install -y -qq curl wget git nginx

# 检查 Node.js
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    echo -e "  ${GREEN}✓${NC} Node.js 已安装: $NODE_VERSION"
else
    echo -e "  安装 Node.js 20.x ..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt-get install -y -qq nodejs
    echo -e "  ${GREEN}✓${NC} Node.js 安装完成: $(node --version)"
fi

# 检查 Python
if command -v python3 &> /dev/null; then
    PY_VERSION=$(python3 --version 2>&1)
    echo -e "  ${GREEN}✓${NC} Python 已安装: $PY_VERSION"
else
    echo -e "  ${RED}✗${NC} Python 3 未安装"
    sudo apt-get install -y -qq python3 python3-pip python3-venv
fi

echo -e "  ${GREEN}✓${NC} 系统依赖安装完成"

# ===== 3. 创建 Python 虚拟环境 =====
echo ""
echo -e "${YELLOW}[3/7] 创建 Python 虚拟环境...${NC}"

cd "$SCRIPT_DIR/backend"

if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo -e "  ${GREEN}✓${NC} 虚拟环境已创建"
else
    echo -e "  虚拟环境已存在，跳过"
fi

source venv/bin/activate

# 升级 pip
pip install --upgrade pip -q

# ===== 4. 安装 Python 依赖 =====
echo ""
echo -e "${YELLOW}[4/7] 安装 Python 依赖...${NC}"

pip install -r requirements.txt -q
echo -e "  ${GREEN}✓${NC} 后端依赖安装完成"

# ===== 5. 安装 llama.cpp (ROCm 预编译版，零编译!) =====
echo ""
echo -e "${YELLOW}[5/7] 安装 llama.cpp (ROCm 预编译)...${NC}"

LLAMA_DIR="$HOME/llama.cpp"
LLAMA_MODEL_DIR="$LLAMA_DIR/models"
mkdir -p "$LLAMA_MODEL_DIR"

LLAMA_VERSION="b9859"
LLAMA_URL="https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_VERSION}/llama-${LLAMA_VERSION}-bin-ubuntu-rocm-7.2-x64.tar.gz"
MODEL_FILE="$LLAMA_MODEL_DIR/qwen2.5-14b-instruct-q4_k_m.gguf"

# 模型下载源（按优先级排列，ModelScope 国内最快）
MODEL_URLS=(
    "https://www.modelscope.cn/models/Qwen/Qwen2.5-14B-Instruct-GGUF/resolve/master/qwen2.5-14b-instruct-q4_k_m.gguf"
    "https://hf-mirror.com/Qwen/Qwen2.5-14B-Instruct-GGUF/resolve/main/qwen2.5-14b-instruct-q4_k_m.gguf"
    "https://huggingface.co/Qwen/Qwen2.5-14B-Instruct-GGUF/resolve/main/qwen2.5-14b-instruct-q4_k_m.gguf"
)

# --- 辅助函数: 验证 gzip magic bytes ---
check_gzip_magic() {
    local f="$1"
    if [ -f "$f" ]; then
        local magic=$(xxd -l 2 -p "$f" 2>/dev/null || od -A x -t x1 -N 2 "$f" 2>/dev/null | head -1 | awk '{print $2$3}')
        [ "$magic" = "1f8b" ] && return 0
    fi
    return 1
}

# --- 辅助函数: 验证 GGUF magic bytes ---
check_gguf_magic() {
    local f="$1"
    if [ -f "$f" ]; then
        local magic=$(head -c 4 "$f" 2>/dev/null)
        [ "$magic" = "GGUF" ] && return 0
    fi
    return 1
}

# --- 辅助函数: 多方法下载 ---
robust_download() {
    local url="$1"
    local dest="$2"
    local min_size_mb="$3"

    # 方法1: curl (忽略SSL, 跟随重定向, 断点续传)
    echo -e "  尝试 curl 下载..."
    curl -L -k --connect-timeout 30 --max-time 1800 -C - -o "$dest" "$url" 2>/dev/null
    local actual_mb=$(($(stat -c%s "$dest" 2>/dev/null || echo 0) / 1048576))
    if [ "$actual_mb" -ge "$min_size_mb" ]; then
        echo -e "  ${GREEN}✓${NC} curl 下载成功 (${actual_mb} MB)"
        return 0
    fi

    # 方法2: wget
    echo -e "  尝试 wget 下载..."
    wget --no-check-certificate --timeout=30 --tries=3 -c -O "$dest" "$url" 2>/dev/null
    actual_mb=$(($(stat -c%s "$dest" 2>/dev/null || echo 0) / 1048576))
    if [ "$actual_mb" -ge "$min_size_mb" ]; then
        echo -e "  ${GREEN}✓${NC} wget 下载成功 (${actual_mb} MB)"
        return 0
    fi

    echo -e "  ${RED}✗${NC} 所有下载方法失败"
    return 1
}

# --- 5.1 下载 llama.cpp 预编译二进制 ---
LLAMA_SERVER=$(find "$LLAMA_DIR" -name "llama-server" -type f 2>/dev/null | head -1)
if [ -n "$LLAMA_SERVER" ] && [ -x "$LLAMA_SERVER" ]; then
    echo -e "  ${GREEN}✓${NC} llama.cpp 已安装: $LLAMA_SERVER"
else
    echo -e "  下载 llama.cpp ROCm 7.2 预编译二进制 (${LLAMA_VERSION}, ~127MB)..."
    TAR_FILE="/tmp/llama-rocm.tar.gz"

    # 清理旧文件
    rm -f "$TAR_FILE"

    if robust_download "$LLAMA_URL" "$TAR_FILE" 100; then
        # 验证 gzip magic bytes
        if ! check_gzip_magic "$TAR_FILE"; then
            echo -e "  ${RED}✗${NC} 下载文件不是有效 gzip (可能是 HTML 错误页)"
            rm -f "$TAR_FILE"
            echo -e "  请手动下载: $LLAMA_URL"
            exit 1
        fi
        echo -e "  ${GREEN}✓${NC} gzip 验证通过"

        # 解压
        tar xzf "$TAR_FILE" -C "$LLAMA_DIR" 2>/dev/null
        rm -f "$TAR_FILE"
        chmod -R +x "$LLAMA_DIR" 2>/dev/null

        # 查找 llama-server
        LLAMA_SERVER=$(find "$LLAMA_DIR" -name "llama-server" -type f 2>/dev/null | head -1)
        if [ -n "$LLAMA_SERVER" ]; then
            chmod +x "$LLAMA_SERVER"
            echo -e "  ${GREEN}✓${NC} llama.cpp 安装完成: $LLAMA_SERVER"
        else
            echo -e "  ${RED}✗${NC} llama-server 未找到! 请检查解压结果"
            find "$LLAMA_DIR" -type f -name "llama-*" 2>/dev/null | head -5
            exit 1
        fi
    else
        echo -e "  ${RED}✗${NC} llama.cpp 下载失败!"
        echo -e "  请手动下载: $LLAMA_URL"
        echo -e "  保存到: $TAR_FILE"
        exit 1
    fi
fi

# --- 5.2 下载 GGUF 模型 ---
if [ -f "$MODEL_FILE" ]; then
    actual_gb=$(($(stat -c%s "$MODEL_FILE" 2>/dev/null || echo 0) / 1073741824))
    if [ "$actual_gb" -ge 8 ] && check_gguf_magic "$MODEL_FILE"; then
        echo -e "  ${GREEN}✓${NC} 模型已存在且有效 (${actual_gb} GB)"
    else
        echo -e "  ${YELLOW}⚠${NC} 模型文件损坏或不完整，重新下载..."
        rm -f "$MODEL_FILE"
    fi
fi

if [ ! -f "$MODEL_FILE" ]; then
    echo -e "  下载 Qwen2.5-14B-Instruct GGUF (q4_k_m, ~9GB)..."
    echo -e "  ${YELLOW}  这可能需要 5-30 分钟，取决于网速...${NC}"

    MODEL_DOWNLOADED=false
    for url in "${MODEL_URLS[@]}"; do
        echo -e "  尝试下载源: ${url%%/resolve*} ..."
        if robust_download "$url" "$MODEL_FILE" 8500; then
            if check_gguf_magic "$MODEL_FILE"; then
                actual_gb=$(($(stat -c%s "$MODEL_FILE" 2>/dev/null || echo 0) / 1073741824))
                echo -e "  ${GREEN}✓${NC} 模型下载完成 (${actual_gb} GB)"
                MODEL_DOWNLOADED=true
                break
            else
                echo -e "  ${YELLOW}⚠${NC} GGUF magic 无效，尝试下一个下载源..."
                rm -f "$MODEL_FILE"
            fi
        else
            echo -e "  ${YELLOW}⚠${NC} 此下载源失败，尝试下一个..."
            rm -f "$MODEL_FILE"
        fi
    done

    if [ "$MODEL_DOWNLOADED" = false ]; then
        echo -e "  ${RED}✗${NC} 所有下载源都失败!"
        echo -e "  请手动下载模型文件:"
        echo -e "    优先: https://www.modelscope.cn/models/Qwen/Qwen2.5-14B-Instruct-GGUF"
        echo -e "    备用: https://huggingface.co/Qwen/Qwen2.5-14B-Instruct-GGUF"
        echo -e "  保存到: $MODEL_FILE"
        exit 1
    fi
fi

echo -e "  llama.cpp 路径: $LLAMA_SERVER"
echo -e "  模型路径: $MODEL_FILE"

deactivate

# ===== 6. 构建前端 =====
echo ""
echo -e "${YELLOW}[6/7] 构建前端...${NC}"

cd "$SCRIPT_DIR/frontend"

if [ ! -d "node_modules" ]; then
    echo -e "  安装前端依赖..."
    npm install --silent
fi

if [ ! -d "dist" ]; then
    echo -e "  构建前端..."
    npm run build
    echo -e "  ${GREEN}✓${NC} 前端构建完成"
else
    echo -e "  前端已构建，跳过 (如需重新构建请删除 dist/ 目录)"
fi

# ===== 7. 配置 Nginx =====
echo ""
echo -e "${YELLOW}[7/7] 配置 Nginx...${NC}"

# 复制 Nginx 配置 (替换前端路径占位符为实际路径)
FRONTEND_DIST="$SCRIPT_DIR/frontend/dist"
sed "s|__FRONTEND_DIST__|${FRONTEND_DIST}|g" "$SCRIPT_DIR/nginx.conf" > /tmp/nginx_myagent.conf
sudo cp /tmp/nginx_myagent.conf /etc/nginx/nginx.conf
rm -f /tmp/nginx_myagent.conf
sudo rm -f /etc/nginx/sites-enabled/default

# 创建数据目录
mkdir -p "$SCRIPT_DIR/data/agents"
mkdir -p "$SCRIPT_DIR/data/skins"
mkdir -p "$SCRIPT_DIR/data/templates"

echo -e "  ${GREEN}✓${NC} Nginx 配置完成"

# ===== 安装完成 =====
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  ✓ 安装完成!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  下一步: 启动服务"
echo -e "  ${BLUE}cd $SCRIPT_DIR${NC}"
echo -e "  ${BLUE}bash start.sh${NC}"
echo ""
echo "  启动后访问:"
echo "    http://localhost          → 前端界面"
echo "    http://localhost/api/docs  → API 文档"
echo "    http://localhost/api/health → 健康检查"
echo ""
