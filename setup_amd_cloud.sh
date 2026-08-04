#!/bin/bash
# ============================================================
#  MyAgent AMD 云环境一键部署脚本
#  目标环境: ModelScope AMD GPU 实例
#  OS: Ubuntu 22.04 | ROCm: 7.2.1 | GPU: 192GB VRAM
# ============================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
step() { echo -e "\n${GREEN}[Step $1]${NC} $2"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

PROJECT_DIR="$HOME/myagent"
MODEL_DIR="$HOME/models"
LLAMA_CPP_DIR="$HOME/llama.cpp"

echo "============================================"
echo "  MyAgent AMD 云环境部署"
echo "  目标: ROCm 7.2.1 | 192GB VRAM"
echo "============================================"

# ============================================================
# Step 1: 系统依赖检查
# ============================================================
step "1/8" "检查系统依赖"

# 检查 ROCm
if command -v rocminfo &> /dev/null; then
    echo "  ✓ ROCm: $(rocminfo 2>/dev/null | grep -m1 'Marketing Name' | awk '{print $NF}')"
    rocm_version=$(dpkg -l rocm-core 2>/dev/null | grep rocm-core | awk '{print $3}' | cut -d. -f1-2)
    echo "  ✓ ROCm 版本: $rocm_version"
else
    echo "  ⚠ rocminfo 未找到，但继续（可能在容器中）"
fi

# 检查 Python
python3 --version
echo "  ✓ Python: $(python3 --version)"

# 检查 GPU 显存
if command -v rocm-smi &> /dev/null; then
    echo "  ✓ GPU 信息:"
    rocm-smi --showmeminfo vram 2>/dev/null | head -5 || true
fi

# ============================================================
# Step 2: 安装编译工具
# ============================================================
step "2/8" "安装编译依赖"

sudo apt-get update -qq
sudo apt-get install -y -qq \
    build-essential cmake git curl wget \
    libssl-dev libffi-dev \
    rocm-dev hip-dev 2>/dev/null || true

echo "  ✓ 编译工具已安装"

# ============================================================
# Step 3: 编译 llama.cpp (ROCm 版)
# ============================================================
step "3/8" "编译 llama.cpp (ROCm 后端)"

if [ ! -d "$LLAMA_CPP_DIR" ]; then
    git clone --depth 1 https://github.com/ggerganov/llama.cpp.git "$LLAMA_CPP_DIR"
fi

cd "$LLAMA_CPP_DIR"

# 使用最新稳定版（兼容 ROCm 7.2）
git fetch --tags
latest_tag=$(git tag -l 'b*' --sort=-v:refname | head -1)
if [ -n "$latest_tag" ]; then
    git checkout "$latest_tag"
    echo "  ✓ 使用版本: $latest_tag"
fi

# 编译（ROCm 后端）
mkdir -p build && cd build
cmake .. -DGGML_HIP=ON -DCMAKE_C_COMPILER=gcc -DCMAKE_CXX_COMPILER=g++ \
    -DCMAKE_BUILD_TYPE=Release -DGGML_HIPBLAS=ON 2>&1 | tail -3
cmake --build . --config Release -j$(nproc) 2>&1 | tail -5

echo "  ✓ llama.cpp 编译完成"

# 验证
if [ -f "$LLAMA_CPP_DIR/build/bin/llama-server" ]; then
    echo "  ✓ llama-server 可用"
else
    echo "  ✗ llama-server 编译失败！"
    exit 1
fi

# ============================================================
# Step 4: 下载模型 (Qwen2.5-14B-Instruct GGUF)
# ============================================================
step "4/8" "下载模型"

mkdir -p "$MODEL_DIR"

MODEL_FILE="$MODEL_DIR/Qwen2.5-14B-Instruct-Q4_K_M.gguf"
MODEL_URL="https://huggingface.co/Qwen/Qwen2.5-14B-Instruct-GGUF/resolve/main/qwen2.5-14b-instruct-q4_k_m.gguf"

if [ -f "$MODEL_FILE" ]; then
    echo "  ✓ 模型已存在: $MODEL_FILE"
    ls -lh "$MODEL_FILE"
else
    echo "  下载中... (约 9GB，请耐心等待)"
    wget -q --show-progress -O "$MODEL_FILE" "$MODEL_URL" || {
        warn "HuggingFace 下载失败，尝试 ModelScope 镜像..."
        # ModelScope 镜像
        pip install modelscope -q
        python3 -c "
from modelscope import snapshot_download
snapshot_download('Qwen/Qwen2.5-14B-Instruct-GGUF', cache_dir='$MODEL_DIR')
"
    }
    echo "  ✓ 模型下载完成"
fi

# ============================================================
# Step 5: Python 后端环境
# ============================================================
step "5/8" "配置 Python 后端"

cd "$PROJECT_DIR/backend"

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo "  ✓ Python 依赖已安装"

# ============================================================
# Step 6: 安装 Node.js 并构建前端
# ============================================================
step "6/8" "构建前端"

# 安装 Node.js (使用 nvm)
if ! command -v node &> /dev/null; then
    export NVM_DIR="$HOME/.nvm"
    if [ ! -d "$NVM_DIR" ]; then
        curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
    fi
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
    nvm install 22
    nvm use 22
fi

echo "  ✓ Node.js: $(node --version)"
echo "  ✓ npm: $(npm --version)"

cd "$PROJECT_DIR/frontend"
npm install --silent 2>&1 | tail -3
npm run build 2>&1 | tail -5

echo "  ✓ 前端构建完成"

# ============================================================
# Step 7: 创建 .env 配置
# ============================================================
step "7/8" "创建配置文件"

cd "$PROJECT_DIR"
cat > .env << 'EOF'
# MyAgent 环境配置
#
# 本项目为纯本地推理，全部计算跑在本机 llama.cpp (ROCm / AMD Radeon GPU)。
# 这里没有、也不允许出现任何远程模型服务的 API Key。
# LLAMA_BASE_URL 必须是本机地址，否则后端启动时会被
# config/settings.py::assert_local_endpoint() 直接拒绝。

# llama.cpp 本地推理
LLAMA_BASE_URL=http://localhost:8000/v1
LLAMA_MODEL=Qwen2.5-14B-Instruct
LLAMA_API_KEY=EMPTY

# 单 GPU 模式（AMD 云实例只有一张 GPU）
SINGLE_GPU_MODE=true
EOF

echo "  ✓ .env 已创建"

# ============================================================
# Step 8: 创建启动脚本
# ============================================================
step "8/8" "创建启动脚本"

cd "$PROJECT_DIR"

# 启动 llama-server
cat > start_llama.sh << 'LLAMA_SCRIPT'
#!/bin/bash
# 启动 llama.cpp 推理服务
MODEL_DIR="$HOME/models"
LLAMA_CPP_DIR="$HOME/llama.cpp"
MODEL="$MODEL_DIR/Qwen2.5-14B-Instruct-Q4_K_M.gguf"

if [ ! -f "$MODEL" ]; then
    echo "模型文件不存在: $MODEL"
    exit 1
fi

echo "启动 llama-server (Qwen2.5-14B, ROCm)..."
$LLAMA_CPP_DIR/build/bin/llama-server \
    -m "$MODEL" \
    --host 0.0.0.0 \
    --port 8000 \
    -ngl 99 \
    --ctx-size 32768 \
    --batch-size 512 \
    --parallel 4 \
    --alias Qwen2.5-14B-Instruct \
    --no-webui
LLAMA_SCRIPT
chmod +x start_llama.sh

# 启动后端
cat > start_backend.sh << 'BACKEND_SCRIPT'
#!/bin/bash
# 启动 MyAgent 后端
cd "$HOME/myagent/backend"
source venv/bin/activate
export $(grep -v '^#' ../.env | xargs)
python main.py
BACKEND_SCRIPT
chmod +x start_backend.sh

# 一键启动
cat > start_all.sh << 'ALL_SCRIPT'
#!/bin/bash
# 一键启动 MyAgent 全部服务
echo "启动 llama.cpp 推理服务..."
nohup bash "$HOME/myagent/start_llama.sh" > /tmp/llama.log 2>&1 &
LLAMA_PID=$!

# 等待 llama-server 就绪
echo "等待 llama-server 就绪..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "llama-server 已就绪"
        break
    fi
    sleep 2
done

echo "启动 MyAgent 后端..."
cd "$HOME/myagent/backend"
source venv/bin/activate
export $(grep -v '^#' ../.env | xargs)
python main.py &
BACKEND_PID=$!

echo ""
echo "============================================"
echo "  MyAgent 启动完成!"
echo "  前端: http://localhost:8080"
echo "  API:  http://localhost:8080/api"
echo "  文档: http://localhost:8080/docs"
echo "============================================"
echo ""
echo "  进程 ID:"
echo "  llama-server: $LLAMA_PID"
echo "  backend:      $BACKEND_PID"
echo ""
echo "  停止服务: kill $LLAMA_PID $BACKEND_PID"

wait
ALL_SCRIPT
chmod +x start_all.sh

echo ""
echo "============================================"
echo "  🎉 部署完成！"
echo "============================================"
echo ""
echo "  启动方式:"
echo "    cd ~/myagent && bash start_all.sh"
echo ""
echo "  或分步启动:"
echo "    bash start_llama.sh      # 先启动 LLM 推理"
echo "    bash start_backend.sh     # 再启动后端"
echo "============================================"