#!/bin/bash
# MyAgent 模型切换脚本 — 云端运行
# 用法: bash switch_model.sh [14b|32b]

VARIANT="${1:-32b}"

# 停止服务
cd /workspace/template-repos/template-2603/repo && bash stop.sh 2>/dev/null

# 写入 .env
ENV_FILE="/workspace/template-repos/template-2603/repo/backend/.env"
mkdir -p "$(dirname "$ENV_FILE")"

if [ "$VARIANT" = "32b" ]; then
    cat > "$ENV_FILE" << 'EOF'
# MyAgent 32B 模型配置
LLAMA_MODEL=/root/llama.cpp/models/qwen2.5-32b-instruct-q4_k_m.gguf
CTX_SIZE=8192
NGL=99
LLAMA_PORT=8000
SINGLE_GPU_MODE=true
PROMPT_VARIANT=slim
EOF
    echo "已切换到 32B 模型"
elif [ "$VARIANT" = "14b" ]; then
    cat > "$ENV_FILE" << 'EOF'
# MyAgent 14B 模型配置
LLAMA_MODEL=/root/llama.cpp/models/qwen2.5-14b-instruct-q4_k_m.gguf
CTX_SIZE=8192
NGL=99
LLAMA_PORT=8000
SINGLE_GPU_MODE=true
PROMPT_VARIANT=slim
EOF
    echo "已切换到 14B 模型"
else
    echo "用法: bash switch_model.sh [14b|32b]"
    exit 1
fi

echo "配置已写入: $ENV_FILE"
cat "$ENV_FILE"

# 启动
echo "重启中..."
bash start.sh
