#!/bin/bash
# ============================================================
#  MyAgent AMD 云环境一键部署脚本
#
#  目标环境: Radeon Cloud 实例
#    GPU    : AMD Radeon PRO W7900 (RDNA3 / gfx1100)
#    VRAM   : 48 GB GDDR6
#    ROCm   : 7.2  (Ubuntu 22.04)
#    vLLM   : 已预装 v0.16.1.dev0 (ROCm 7.2.1 构建) —— 本项目不使用，走 llama.cpp
#
#  数据来源: 用户于 Radeon Cloud 控制台实机确认的实例规格
#  验证日期: 2025-08-04
#  修订说明: 原头部写的 "MI300X / 192GB VRAM" 为错误假设，已按实机参数修正。
#
#  向后兼容: 本脚本所有关键参数均支持环境变量覆盖，换卡不用改脚本。
#    例) 拿到 192GB MI300X 实例:
#        QUANT=q8_0 CTX_SIZE=65536 PARALLEL=4 bash setup_amd_cloud.sh
#    例) 只想把上下文调大:
#        CTX_SIZE=16384 bash setup_amd_cloud.sh
# ============================================================
set -e

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
step() { echo -e "\n${GREEN}[Step $1]${NC} $2"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; }

# ============================================================
#  可调参数（全部支持环境变量覆盖）
# ============================================================
#
# ---- 显存预算：Qwen2.5-14B-Instruct on 48GB W7900 ----
#
# 模型结构（决定 KV cache 大小）:
#   层数 n_layer      = 48
#   KV 头数 n_kv_head = 8      (GQA，比 MHA 省 5 倍 KV)
#   head_dim          = 128
#
# KV cache 显存估算公式:
#   bytes/token = 2(K和V) × n_layer × n_kv_head × head_dim × 2(fp16)
#               = 2 × 48 × 8 × 128 × 2
#               = 196,608 B = 0.1875 MiB / token
#
#   KV(GiB) = CTX_SIZE × 0.1875 / 1024
#
# 权重占用（GGUF 实测文件大小）:
#   q4_k_m ≈  8.99 GiB      q5_k_m ≈ 10.5 GiB      q8_0 ≈ 15.7 GiB
#
# 另需 compute / graph buffer ≈ 1–2 GiB
#
# 各组合总占用（权重 + KV + 1.5GiB buffer）:
#   ┌──────────┬────────┬────────┬────────┬────────┐
#   │  CTX     │  8192  │ 16384  │ 32768  │ 65536  │
#   │  KV(GiB) │  1.5   │  3.0   │  6.0   │  12.0  │
#   ├──────────┼────────┼────────┼────────┼────────┤
#   │ q4_k_m   │ ~12.0  │ ~13.5  │ ~16.5  │ ~22.5  │
#   │ q5_k_m   │ ~13.5  │ ~15.0  │ ~18.0  │ ~24.0  │
#   └──────────┴────────┴────────┴────────┴────────┘
#
# ⚠ 重要结论（与最初"48GB 会 OOM"的判断不同）:
#   Qwen2.5-14B 用的是 GQA（只有 8 个 KV 头），KV cache 比想象中便宜得多。
#   即使 q5_k_m + 32K 上下文，总占用也只有 ~18GB / 48GB —— 完全不会 OOM。
#   下面默认值 CTX_SIZE=8192 是**保守起步基线**，不是显存上限所迫。
#   上机跑通基线后，建议直接抬到 16384（见「高性能模式」）。
#
# ⚠ A/B 测速特别提醒:
#   原版（baseline）角色提示词最长的是 coach，7201 字符 ≈ 4300–5000 tokens。
#   叠加对话历史 + default_max_tokens=4096（backend/config/models.yaml），
#   8192 的上下文对 **A 组（原版 prompt）** 偏紧，可能截断或报 context overflow。
#   → 跑 A/B 对比时请用 CTX_SIZE=16384，A、B 两组保持一致。
#   → 8192 仅适合 slim 版（600–900 字 ≈ 600 tokens）单轮问答冒烟测试。

# 量化版本：q4_k_m（默认，给 KV cache 留足空间） / q5_k_m / q8_0
QUANT="${QUANT:-q4_k_m}"

# 上下文长度。注意：这是 llama-server 的**总**上下文，
# 会被 --parallel 平分！每个槽位实得 = CTX_SIZE / PARALLEL。
CTX_SIZE="${CTX_SIZE:-8192}"

# 并发槽位数。默认 1 —— 保证 CTX_SIZE 全部给到单个会话。
# ⚠ 原脚本写 --parallel 4 且 ctx 32768，实际每槽只有 8192；
#   若沿用 parallel=4 再把 ctx 降到 8192，每槽只剩 2048，必炸。
PARALLEL="${PARALLEL:-1}"

# 卸载到 GPU 的层数。99 = 全部（W7900 48GB 完全放得下 14B）
NGL="${NGL:-99}"

# 批大小
BATCH_SIZE="${BATCH_SIZE:-512}"

# GPU 架构。W7900 = gfx1100 (RDNA3)。
# 指定它可以只编译单架构，编译时间从 ~40min 降到 ~10min。
AMDGPU_TARGET="${AMDGPU_TARGET:-gfx1100}"

# 端口（与 nginx.conf / backend/config/settings.py 对齐，勿随意改）
#   8000 = llama-server (OpenAI 兼容接口)
#   8080 = FastAPI 后端
#   80   = nginx 统一入口
LLAMA_PORT="${LLAMA_PORT:-8000}"
BACKEND_PORT="${BACKEND_PORT:-8080}"

# ---- GPU 路由模式 ----
# 本脚本只起 **一个** llama-server (端口 $LLAMA_PORT)，因此必须是单 GPU 路由。
# 若默认走多 GPU 路由，gpu_affinity=gpu1/gpu2 的角色会去连 8001/8002 ——
# 那里没有服务，部署阶段一切正常，跑到多角色流水线中途才会 Connection refused。
#
# 注意：这里**不能**用 `export SINGLE_GPU_MODE=true` 解决。
# 后端是稍后由 start.sh 在另一个 shell 里拉起的，export 不会传递过去。
# 正确做法是落盘到 backend/.env（Settings 的 env_file），见 Step 9。
SINGLE_GPU_MODE="${SINGLE_GPU_MODE:-true}"

# 模型别名（必须与 backend/config/models.yaml 的 model_name 一致）
MODEL_ALIAS="Qwen2.5-14B-Instruct"

# === 可选：高性能模式（如果 8K 测速通过且显存有余量，取消注释切换）===
# QUANT=q5_k_m          # 更高精度，多占 ~1.5GB
# CTX_SIZE=16384        # 更长上下文，KV cache 多占 ~1.5GB
# 注意：此组合预估总占用 ~15GB/48GB，远未触顶，建议先跑 8K 基线后再试。
#      （原注释估的 35-40GB 是按 MHA 算的，Qwen2.5 用 GQA，实际低得多）
#
# 更激进（仍安全）:
# QUANT=q5_k_m CTX_SIZE=32768 PARALLEL=1    → ~18GB/48GB

# ============================================================
#  路径（与 install.sh / start.sh 严格对齐）
# ============================================================
# ⚠ 修订：原脚本把模型下到 $HOME/models/Qwen2.5-14B-Instruct-Q4_K_M.gguf，
#   而 start.sh 只在 $HOME/llama.cpp/models/ 下找 *.gguf —— 路径对不上，
#   导致 setup 跑完后 start.sh 报「GGUF 模型未找到」。现统一到 install.sh 的路径。
PROJECT_DIR="${PROJECT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
LLAMA_CPP_DIR="${LLAMA_CPP_DIR:-$HOME/llama.cpp}"
MODEL_DIR="$LLAMA_CPP_DIR/models"
MODEL_FILE="$MODEL_DIR/qwen2.5-14b-instruct-${QUANT}.gguf"

# 下载源（ModelScope 优先，国内最快；与 install.sh 一致）
MODEL_URLS=(
    "https://www.modelscope.cn/models/Qwen/Qwen2.5-14B-Instruct-GGUF/resolve/master/qwen2.5-14b-instruct-${QUANT}.gguf"
    "https://hf-mirror.com/Qwen/Qwen2.5-14B-Instruct-GGUF/resolve/main/qwen2.5-14b-instruct-${QUANT}.gguf"
    "https://huggingface.co/Qwen/Qwen2.5-14B-Instruct-GGUF/resolve/main/qwen2.5-14b-instruct-${QUANT}.gguf"
)

# 参数合法性守卫（避免 set -e 下被除零直接干掉）
if ! [ "$PARALLEL" -ge 1 ] 2>/dev/null; then
    fail "PARALLEL 必须是 >=1 的整数，当前: '$PARALLEL'"
    exit 1
fi
if ! [ "$CTX_SIZE" -ge 512 ] 2>/dev/null; then
    fail "CTX_SIZE 必须是 >=512 的整数，当前: '$CTX_SIZE'"
    exit 1
fi

# 每槽实得上下文
CTX_PER_SLOT=$(( CTX_SIZE / PARALLEL ))
# KV cache 估算 (MiB)：CTX_SIZE × 0.1875 MiB
KV_MIB=$(( CTX_SIZE * 3 / 16 ))

echo "============================================"
echo "  MyAgent AMD 云环境部署"
echo "  目标: Radeon PRO W7900 / 48GB / ROCm 7.2"
echo "--------------------------------------------"
echo "  量化版本   : $QUANT"
echo "  总上下文   : $CTX_SIZE"
echo "  并发槽位   : $PARALLEL  (每槽 $CTX_PER_SLOT tokens)"
echo "  KV cache   : ~${KV_MIB} MiB"
echo "  GPU 架构   : $AMDGPU_TARGET"
echo "  模型路径   : $MODEL_FILE"
echo "  GPU 路由   : SINGLE_GPU_MODE=$SINGLE_GPU_MODE (单卡=全部角色走 :$LLAMA_PORT)"
echo "============================================"

if [ "$SINGLE_GPU_MODE" != "true" ]; then
    warn "SINGLE_GPU_MODE=$SINGLE_GPU_MODE —— 本脚本只会启动 1 个 llama-server。"
    warn "多 GPU 路由需要你自行起满 8000/8001/8002 三个实例，否则"
    warn "gpu_affinity=gpu1/gpu2 的角色一调用就会 Connection refused。"
fi

if [ "$CTX_PER_SLOT" -lt 4096 ]; then
    warn "每槽上下文只有 $CTX_PER_SLOT tokens，低于 4096。"
    warn "原版角色提示词（coach 约 5000 tokens）会溢出。"
    warn "建议: PARALLEL=1 或调大 CTX_SIZE。"
fi

# ============================================================
# Step 1: 系统依赖检查
# ============================================================
step "1/9" "检查系统依赖"

if command -v rocminfo &> /dev/null; then
    # rocminfo 会先列出 CPU agent，直接取第一条会误报成 CPU 型号。
    # 先尝试 rocm-smi（只列 GPU），失败再回退 rocminfo 并过滤掉 CPU 关键词。
    gpu_name=$(rocm-smi --showproductname --csv 2>/dev/null \
        | awk -F, 'NR>1 && $2 != "" {print $2; exit}' | xargs 2>/dev/null || true)
    if [ -z "$gpu_name" ]; then
        gpu_name=$(rocminfo 2>/dev/null | grep 'Marketing Name' | cut -d: -f2- \
            | grep -viE 'epyc|xeon|core processor|ryzen|threadripper' \
            | head -1 | xargs 2>/dev/null || true)
    fi
    echo "  ✓ GPU: ${gpu_name:-unknown}"
    gfx=$(rocminfo 2>/dev/null | grep -m1 -o 'gfx[0-9a-z]*' || true)
    echo "  ✓ 架构: ${gfx:-unknown}  (期望 gfx1100)"
    if [ -n "$gfx" ] && [ "$gfx" != "$AMDGPU_TARGET" ]; then
        warn "实际架构 $gfx 与 AMDGPU_TARGET=$AMDGPU_TARGET 不符。"
        warn "请重跑: AMDGPU_TARGET=$gfx bash setup_amd_cloud.sh"
    fi
    rocm_version=$(dpkg -l rocm-core 2>/dev/null | grep rocm-core | awk '{print $3}' | cut -d. -f1-2)
    echo "  ✓ ROCm 版本: ${rocm_version:-unknown}  (期望 7.2)"
else
    warn "rocminfo 未找到，但继续（可能在容器中）"
fi

python3 --version
echo "  ✓ Python: $(python3 --version)"

# ============================================================
# Step 2: GPU 显存检查
# ============================================================
step "2/9" "GPU 显存检查"

echo "=== GPU VRAM Check ==="
amd-smi static --vram 2>/dev/null || rocm-smi --showmeminfo vram 2>/dev/null || echo "[WARN] Could not detect VRAM"
echo "Expected: ~48GB for W7900. If significantly lower, abort and check allocation."
echo ""

# 尝试解析实际显存并给出判断
vram_mib=$(rocm-smi --showmeminfo vram --csv 2>/dev/null \
    | awk -F, 'NR>1 && $2 ~ /^[0-9]+$/ {print int($2/1048576); exit}')
if [ -n "$vram_mib" ] && [ "$vram_mib" -gt 0 ]; then
    echo "  检测到显存: ${vram_mib} MiB (~$(( vram_mib / 1024 )) GiB)"
    if [ "$vram_mib" -lt 40000 ]; then
        warn "显存低于 40GiB —— 分配到的可能不是 W7900！"
        warn "建议: 降低 CTX_SIZE 或销毁实例重新排队。"
        warn "5 秒后继续（Ctrl+C 中止）..."
        sleep 5
    else
        echo "  ✓ 显存充足"
    fi
else
    warn "无法自动解析显存数值，请人工核对上方输出。"
fi

# ============================================================
# Step 3: 安装编译工具
# ============================================================
step "3/9" "安装运行依赖（轻量）"

# --- 3a. 屏蔽不可达的 apt 源 ---------------------------------
# AMD 官方容器镜像内置了公司内网源 compute-artifactory.amd.com，
# 公网环境下 DNS 解析失败，apt-get update 会在此长时间阻塞（数分钟）。
# ROCm 本身已随镜像预装，无需该源，直接禁用以避免卡顿。
for f in /etc/apt/sources.list.d/*.list /etc/apt/sources.list.d/*.sources; do
    [ -f "$f" ] || continue
    if grep -qi "compute-artifactory.amd.com" "$f" 2>/dev/null; then
        sudo mv "$f" "$f.disabled" 2>/dev/null || true
        echo "  ✓ 已禁用不可达内网源: $(basename "$f")"
    fi
done

# --- 3b. 只装真正需要的运行时依赖 ------------------------------
# 使用官方预编译 llama.cpp 时不需要 build-essential / cmake，
# 那些包（~500MB）留到 Step 4 回退编译分支时才按需安装。
APT_OPTS="-o Acquire::Retries=1 -o Acquire::http::Timeout=15 -o Acquire::ftp::Timeout=15"
# shellcheck disable=SC2086
sudo apt-get $APT_OPTS update -qq 2>/dev/null || warn "apt update 有源不可达，已忽略"
# shellcheck disable=SC2086
sudo apt-get $APT_OPTS install -y -qq \
    ca-certificates curl wget git nginx python3-venv 2>/dev/null || true

echo "  ✓ 运行依赖就绪（编译工具链按需延后安装）"

# ============================================================
# Step 4: 获取 llama.cpp (优先官方 ROCm 预编译包，回退源码编译)
# ============================================================
step "4/9" "获取 llama.cpp (ROCm 后端, $AMDGPU_TARGET)"

# 官方自 b10xxx 起提供 Ubuntu ROCm 7.2 预编译二进制（~124MB）。
# 直接下载解压 <1 分钟，相比源码编译（10-15 分钟）大幅节省实例机时。
# 若下载失败（网络受限等），自动回退到源码编译路径。
LLAMA_PREBUILT_TAG="${LLAMA_PREBUILT_TAG:-b10267}"
LLAMA_PREBUILT_URL="https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_PREBUILT_TAG}/llama-${LLAMA_PREBUILT_TAG}-bin-ubuntu-rocm-7.2-x64.tar.gz"

if [ -f "$LLAMA_CPP_DIR/build/bin/llama-server" ]; then
    echo "  ✓ llama-server 已存在，跳过获取"
    echo "    (如需重新获取: rm -rf $LLAMA_CPP_DIR/build)"
else
    mkdir -p "$LLAMA_CPP_DIR"
    PREBUILT_OK=0

    echo "  → 尝试下载官方 ROCm 预编译包 ($LLAMA_PREBUILT_TAG, ~124MB)..."
    tmp_tar="/tmp/llama-rocm-${LLAMA_PREBUILT_TAG}.tar.gz"
    rm -f "$tmp_tar"

    # 第一次：正常 TLS 校验
    curl -fL --retry 2 --connect-timeout 20 -o "$tmp_tar" "$LLAMA_PREBUILT_URL" 2>/dev/null || true
    tar_size=$(stat -c%s "$tmp_tar" 2>/dev/null || echo 0)

    # 云实例镜像常缺 CA 根证书（表现为 "unable to establish a secure connection"），
    # 导致下载得到 0 字节。跳过证书校验重试一次——拉取的是 GitHub 官方公开 release，
    # 且下方会以体积 + 二进制存在性双重校验，安全上可接受。
    if [ "$tar_size" -lt 52428800 ]; then
        warn "首次下载失败 (${tar_size} bytes)，多为缺少 CA 根证书；跳过证书校验重试..."
        rm -f "$tmp_tar"
        curl -kfL --retry 2 --connect-timeout 20 -o "$tmp_tar" "$LLAMA_PREBUILT_URL" 2>/dev/null || true
        tar_size=$(stat -c%s "$tmp_tar" 2>/dev/null || echo 0)
    fi

    # 校验体积合理（>50MB）后再解压，避免把错误页当成包
    if [ "$tar_size" -gt 52428800 ]; then
            mkdir -p "$LLAMA_CPP_DIR/build"
            tar -xzf "$tmp_tar" -C "$LLAMA_CPP_DIR/build" --strip-components=1 2>/dev/null \
                || tar -xzf "$tmp_tar" -C "$LLAMA_CPP_DIR/build"
            # 官方包结构可能是 build/bin/ 或直接 bin/，两种都兜住
            if [ ! -f "$LLAMA_CPP_DIR/build/bin/llama-server" ]; then
                found=$(find "$LLAMA_CPP_DIR/build" -name llama-server -type f 2>/dev/null | head -1)
                if [ -n "$found" ]; then
                    mkdir -p "$LLAMA_CPP_DIR/build/bin"
                    cp -a "$(dirname "$found")"/* "$LLAMA_CPP_DIR/build/bin/" 2>/dev/null || true
                fi
            fi
            chmod +x "$LLAMA_CPP_DIR/build/bin/"* 2>/dev/null || true
            if [ -f "$LLAMA_CPP_DIR/build/bin/llama-server" ]; then
                PREBUILT_OK=1
                echo "  ✓ 预编译包就绪（跳过编译，节省约 15 分钟）"
            fi
    else
        warn "预编译包下载失败 (${tar_size} bytes)"
    fi
    rm -f "$tmp_tar"

    if [ "$PREBUILT_OK" -eq 0 ]; then
        warn "回退到源码编译（约 10-15 分钟，编译期屏幕长时间无输出属正常）"
        echo "  → 安装编译工具链（仅回退路径需要）..."
        sudo apt-get $APT_OPTS install -y -qq \
            build-essential cmake libssl-dev libffi-dev libcurl4-openssl-dev 2>/dev/null || true
        if [ ! -d "$LLAMA_CPP_DIR/.git" ]; then
            rm -rf "$LLAMA_CPP_DIR"
            git clone --depth 1 https://github.com/ggml-org/llama.cpp.git "$LLAMA_CPP_DIR"
        fi

        cd "$LLAMA_CPP_DIR"
        git fetch --tags --depth 1 2>/dev/null || true
        latest_tag=$(git tag -l 'b*' --sort=-v:refname | head -1)
        if [ -n "$latest_tag" ]; then
            git checkout "$latest_tag" 2>/dev/null && echo "  ✓ 使用版本: $latest_tag" || true
        fi

        # ROCm 编译。指定 AMDGPU_TARGETS 只编 gfx1100，大幅缩短编译时间。
        mkdir -p build && cd build
        cmake .. \
            -DGGML_HIP=ON \
            -DAMDGPU_TARGETS="$AMDGPU_TARGET" \
            -DCMAKE_C_COMPILER=hipcc \
            -DCMAKE_CXX_COMPILER=hipcc \
            -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -5
        cmake --build . --config Release -j"$(nproc)" 2>&1 | tail -5

        echo "  ✓ llama.cpp 编译完成"
    fi
fi

if [ -f "$LLAMA_CPP_DIR/build/bin/llama-server" ]; then
    echo "  ✓ llama-server 可用: $LLAMA_CPP_DIR/build/bin/llama-server"
else
    fail "llama-server 获取失败！预编译下载与源码编译均未成功。"
    exit 1
fi

# ============================================================
# Step 5: 下载模型
# ============================================================
step "5/9" "下载模型 (Qwen2.5-14B-Instruct $QUANT)"

mkdir -p "$MODEL_DIR"

check_gguf_magic() {
    local f="$1"
    [ -f "$f" ] || return 1
    local magic
    magic=$(head -c 4 "$f" 2>/dev/null)
    [ "$magic" = "GGUF" ]
}

if check_gguf_magic "$MODEL_FILE"; then
    echo "  ✓ 模型已存在且 GGUF 头有效: $MODEL_FILE"
    ls -lh "$MODEL_FILE"
else
    [ -f "$MODEL_FILE" ] && { warn "已存在文件损坏，删除重下"; rm -f "$MODEL_FILE"; }
    echo "  下载中... (q4_k_m 约 9GB / q5_k_m 约 10.5GB，请耐心等待)"

    downloaded=false
    for url in "${MODEL_URLS[@]}"; do
        echo "  尝试: ${url%%/resolve*}"
        if wget -q --show-progress -c -O "$MODEL_FILE" "$url"; then
            if check_gguf_magic "$MODEL_FILE"; then
                downloaded=true
                break
            fi
            warn "GGUF magic 无效，换下一个源"
        fi
        rm -f "$MODEL_FILE"
    done

    if [ "$downloaded" != true ]; then
        fail "模型下载失败，请手动下载到: $MODEL_FILE"
        echo "    优先: https://www.modelscope.cn/models/Qwen/Qwen2.5-14B-Instruct-GGUF"
        exit 1
    fi
    echo "  ✓ 模型下载完成 ($(du -h "$MODEL_FILE" | cut -f1))"
fi

# ============================================================
# Step 6: Python 后端环境
# ============================================================
step "6/9" "配置 Python 后端"

cd "$PROJECT_DIR/backend"
[ -d venv ] || python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip -q
pip install -r requirements.txt -q
deactivate

echo "  ✓ Python 依赖已安装"

# ============================================================
# Step 7: 构建前端
# ============================================================
step "7/9" "构建前端"

FRONTEND_OK=0

# --- 确保有 Node.js（三级回退，任何一级失败都不中断整个部署）---
if ! command -v node &> /dev/null; then
    echo "  · 未检测到 Node.js，尝试安装…"

    # 1) nvm（官方推荐，需能访问 raw.githubusercontent.com）
    export NVM_DIR="$HOME/.nvm"
    if [ ! -d "$NVM_DIR" ]; then
        curl -fsSL --connect-timeout 15 --max-time 120 \
            -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash || true
    fi
    # shellcheck disable=SC1091
    [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh" || true
    if command -v nvm &> /dev/null; then
        nvm install 22 >/dev/null 2>&1 || true
        nvm use 22    >/dev/null 2>&1 || true
    fi

    # 2) 回退：发行版仓库
    if ! command -v node &> /dev/null; then
        echo "  · nvm 不可用，回退 apt…"
        sudo apt-get install -y -qq nodejs npm >/dev/null 2>&1 || true
    fi
fi

if command -v node &> /dev/null && command -v npm &> /dev/null; then
    echo "  ✓ Node.js: $(node --version)"
    echo "  ✓ npm: $(npm --version)"

    cd "$PROJECT_DIR/frontend"
    if npm install --silent 2>&1 | tail -3 && npm run build 2>&1 | tail -5; then
        if [ -d "$PROJECT_DIR/frontend/dist" ]; then
            FRONTEND_OK=1
            echo "  ✓ 前端构建完成 → $PROJECT_DIR/frontend/dist"
        fi
    fi
    cd "$PROJECT_DIR"
fi

if [ "$FRONTEND_OK" -ne 1 ]; then
    warn "前端构建未完成（Node.js 缺失或 npm 失败）。"
    warn "后端 API (:8080) 与推理引擎 (:8000) 不受影响，仍可正常演示。"
    warn "补救: cd $PROJECT_DIR/frontend && npm install && npm run build"
fi

# ============================================================
# Step 8: 配置 Nginx（单端口 80 统一入口）
# ============================================================
step "8/9" "配置 Nginx"

if command -v nginx &> /dev/null; then
    FRONTEND_DIST="$PROJECT_DIR/frontend/dist"
    sed "s|__FRONTEND_DIST__|${FRONTEND_DIST}|g" "$PROJECT_DIR/nginx.conf" > /tmp/nginx_myagent.conf
    sudo cp /tmp/nginx_myagent.conf /etc/nginx/nginx.conf
    rm -f /tmp/nginx_myagent.conf
    sudo rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true
    sudo nginx -t && echo "  ✓ Nginx 配置已就位 (端口 80)"
else
    warn "nginx 未安装，跳过。前端可用 'npx vite preview' 临时预览。"
fi

# ============================================================
# Step 9: 生成启动脚本
# ============================================================
step "9/9" "生成运行时配置与启动脚本"

cd "$PROJECT_DIR"

# ---- backend/.env：把 GPU 路由固化到磁盘 ----
# 为什么必须落盘而不是 export：
#   后端由 start.sh 在**另一个 shell** 中用 uvicorn 拉起，
#   本脚本 export 的环境变量到不了那个进程。
#   backend/.env 是 pydantic Settings 的 env_file，start.sh 里
#   `cd $BACKEND_DIR` 之后一定会被读到，跨 shell、跨重启都生效。
# 幂等：只覆写下面这几个 key，用户手写的其它配置原样保留。
ENV_FILE="$PROJECT_DIR/backend/.env"
touch "$ENV_FILE"

set_env_kv() {
    local key="$1" val="$2"
    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
        # 用 | 作分隔符，避免 URL 里的 / 打架
        sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
    else
        echo "${key}=${val}" >> "$ENV_FILE"
    fi
}

set_env_kv "SINGLE_GPU_MODE" "$SINGLE_GPU_MODE"
set_env_kv "LLAMA_BASE_URL"  "http://localhost:${LLAMA_PORT}/v1"
set_env_kv "LLAMA_MODEL"     "$MODEL_ALIAS"

echo "  ✓ backend/.env 已写入 (GPU 路由固化)"
echo "      SINGLE_GPU_MODE=$SINGLE_GPU_MODE"
echo "      LLAMA_BASE_URL=http://localhost:${LLAMA_PORT}/v1"
echo "      LLAMA_MODEL=$MODEL_ALIAS"

# ---- llama-server 启动脚本（参数从本脚本注入，保持一致）----
# 先写入注入的默认值（可被环境变量覆盖），再追加固定的逻辑体。
{
    echo '#!/bin/bash'
    echo '# 由 setup_amd_cloud.sh 生成 —— 参数已按 W7900 48GB 校准'
    echo '# 所有变量可用环境变量覆盖，例: CTX_SIZE=16384 bash start_llama.sh'
    echo "MODEL=\"\${MODEL:-$MODEL_FILE}\""
    echo "LLAMA_CPP_DIR=\"\${LLAMA_CPP_DIR:-$LLAMA_CPP_DIR}\""
    echo "MODEL_ALIAS=\"\${MODEL_ALIAS:-$MODEL_ALIAS}\""
    echo "CTX_SIZE=\"\${CTX_SIZE:-$CTX_SIZE}\""
    echo "PARALLEL=\"\${PARALLEL:-$PARALLEL}\""
    echo "NGL=\"\${NGL:-$NGL}\""
    echo "BATCH_SIZE=\"\${BATCH_SIZE:-$BATCH_SIZE}\""
    echo "LLAMA_PORT=\"\${LLAMA_PORT:-$LLAMA_PORT}\""
} > start_llama.sh

cat >> start_llama.sh << 'LLAMA_SCRIPT'

if [ ! -f "$MODEL" ]; then
    echo "模型文件不存在: $MODEL"
    echo "请先运行: bash setup_amd_cloud.sh"
    exit 1
fi

echo "启动 llama-server ($MODEL_ALIAS, ROCm)"
echo "  ctx=$CTX_SIZE  parallel=$PARALLEL  (每槽 $(( CTX_SIZE / PARALLEL )))"
echo "  KV cache ~ $(( CTX_SIZE * 3 / 16 )) MiB"

exec "$LLAMA_CPP_DIR/build/bin/llama-server" \
    -m "$MODEL" \
    -a "$MODEL_ALIAS" \
    --host 0.0.0.0 \
    --port "$LLAMA_PORT" \
    -ngl "$NGL" \
    --ctx-size "$CTX_SIZE" \
    --batch-size "$BATCH_SIZE" \
    --parallel "$PARALLEL" \
    --no-webui
LLAMA_SCRIPT
chmod +x start_llama.sh

echo "  ✓ start_llama.sh"
echo "  ✓ 全栈启停请用仓库自带的 start.sh / stop.sh"

# ---- A/B 测速辅助（可 source 使用）----
cat > bench_helpers.sh << 'BENCH_SCRIPT'
#!/bin/bash
# === A/B Benchmark Helper ===
# 用法（必须 source，不能直接 bash 执行）:
#   source bench_helpers.sh
#   benchmark_slim    # 切精简版 prompt (B 组)
#   benchmark_orig    # 切原版 prompt   (A 组基线)
#   bench_one "开发一个带增删改查的待办事项 Web 应用"   # 单次计时

MYAGENT_DIR="${MYAGENT_DIR:-$HOME/myagent}"
# 后端直连端口（nginx 在 80，但测速直连 8080 避开代理开销）
BENCH_PORT="${BENCH_PORT:-8080}"
# 对话端点为 /api/agents/{agent_id}/chat，默认 agent 见 data/agents/
AGENT_ID="${AGENT_ID:-general_assistant}"

_restart_backend() {
    echo "  重启后端以加载新的 PROMPT_VARIANT..."
    bash "$MYAGENT_DIR/stop.sh"  > /dev/null 2>&1 || true
    bash "$MYAGENT_DIR/start.sh" > /dev/null 2>&1 || true
    sleep 3
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

# 单次计时 + 抓 prompt_tokens
# 用法: bench_one "开发一个带增删改查的待办事项 Web 应用"
bench_one() {
    local msg="${1:-开发一个带增删改查的待办事项 Web 应用}"
    local variant="${PROMPT_VARIANT:-original}"
    local url="http://localhost:${BENCH_PORT}/api/agents/${AGENT_ID}/chat"
    local payload start end elapsed tokens

    # 用 python 安全地构造 JSON（消息含中文/引号也不会坏）
    payload=$(MSG="$msg" python3 -c 'import json,os;print(json.dumps({"message":os.environ["MSG"],"stream":False}))')

    start=$(date +%s%3N)
    curl -s -X POST "$url" -H "Content-Type: application/json" -d "$payload" \
        > "/tmp/bench_out_${variant}.json"
    end=$(date +%s%3N)
    elapsed=$(( end - start ))

    # 从 llama-server 日志抓最近一次的真实 prompt_tokens（勿用估算值）
    tokens=$(grep -o '"prompt_tokens":[0-9]*' /tmp/llama.log 2>/dev/null | tail -1 | cut -d: -f2)

    echo "variant=$variant  elapsed=${elapsed}ms  prompt_tokens=${tokens:-N/A}"
    echo "$variant,$elapsed,${tokens:-},$(date -Iseconds)" >> "/tmp/bench_${variant}.csv"
}

# 打印已采集结果
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
chmod +x bench_helpers.sh
echo "  ✓ bench_helpers.sh  (用法: source bench_helpers.sh)"

echo ""
echo "============================================"
echo "  部署完成！"
echo "============================================"
echo ""
echo "  GPU 路由: 单卡模式（默认，无需手动设任何环境变量）"
echo "    全部 18 个角色 → http://localhost:$LLAMA_PORT/v1"
echo "    已固化在 backend/.env，start.sh 会自动读取。"
echo "    后端启动日志里会打印一行 '[RoleLoader] 推理路由: ...'，可肉眼核对。"
echo ""
echo "    换多卡实例时（需自行起满 8000/8001/8002 三个 llama-server）:"
echo "      sed -i 's|^SINGLE_GPU_MODE=.*|SINGLE_GPU_MODE=false|' backend/.env"
echo ""
echo "  启动:"
echo "    cd $PROJECT_DIR && bash start.sh"
echo ""
echo "  访问:"
echo "    http://<实例IP>/               → 前端界面 (nginx:80)"
echo "    http://localhost:$BACKEND_PORT/docs      → API 文档 (FastAPI 直连)"
echo "    http://localhost:$BACKEND_PORT/api/health → 健康检查"
echo "    http://localhost:$LLAMA_PORT/v1/models  → llama-server 模型列表"
echo ""
echo "  A/B 测速:"
echo "    source $PROJECT_DIR/bench_helpers.sh"
echo "    benchmark_orig   # A 组基线"
echo "    benchmark_slim   # B 组精简"
echo ""
echo "  详细上机步骤见: QUICKSTART_CLOUD.md"
echo "============================================"

# ============================================================
#  A/B Benchmark Helper (同时内联定义，便于 source 本脚本时直接使用)
# ============================================================
# Usage:
#   benchmark_slim    # Run with slim prompts (optimized)
#   benchmark_orig    # Run with original prompts (baseline)
benchmark_slim() {
    export PROMPT_VARIANT=slim
    echo "=== BENCHMARK: SLIM (optimized) prompts ==="
    echo "PROMPT_VARIANT=$PROMPT_VARIANT"
    # Restart backend with new env
}

benchmark_orig() {
    unset PROMPT_VARIANT
    echo "=== BENCHMARK: ORIGINAL (baseline) prompts ==="
    echo "PROMPT_VARIANT=${PROMPT_VARIANT:-default}"
}
