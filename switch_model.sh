#!/bin/bash
# MyAgent 模型切换脚本
# 用法:
#   bash switch_model.sh /path/to/model.gguf        # 指定完整路径
#   bash switch_model.sh 14b                         # 快捷方式: 14B
#   bash switch_model.sh 30b                         # 快捷方式: Qwen3-30B-A3B
#   bash switch_model.sh api                         # 切换到远程 API 模式

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/backend/.env"
ARG="${1:-}"

if [ -z "$ARG" ]; then
    echo "用法:"
    echo "  bash switch_model.sh /path/to/model.gguf  指定 GGUF 文件路径"
    echo "  bash switch_model.sh 14b                  内置快捷方式: Qwen2.5-14B"
    echo "  bash switch_model.sh 30b                  内置快捷方式: Qwen3-30B-A3B MoE"
    echo "  bash switch_model.sh api                  切换到远程 API 模式"
    echo ""
    echo "当前配置:"
    [ -f "$ENV_FILE" ] && grep "^LLAMA_MODEL\|^LLAMA_BASE_URL" "$ENV_FILE" 2>/dev/null || echo "  (未配置 .env)"
    exit 0
fi

bash "$SCRIPT_DIR/stop.sh" 2>/dev/null

mkdir -p "$(dirname "$ENV_FILE")"

case "$ARG" in
    api|API)
        cat > "$ENV_FILE" << 'EOF'
# === 远程 API 模式 ===
LLAMA_BASE_URL=https://api.openai.com/v1
LLAMA_API_KEY=sk-your-key-here
LLAMA_MODEL=gpt-4
SINGLE_GPU_MODE=true
PROMPT_VARIANT=slim
EOF
        echo "已切换到远程 API 模式"
        echo "⚠ 请编辑 $ENV_FILE 填入实际的 BASE_URL / API_KEY / MODEL"
        ;;
    14b|14B)
        cat > "$ENV_FILE" << 'EOF'
# MyAgent 14B 模型配置
LLAMA_MODEL=/root/llama.cpp/models/qwen2.5-14b-instruct-q4_k_m.gguf
CTX_SIZE=8192
NGL=99
LLAMA_PORT=8000
SINGLE_GPU_MODE=true
PROMPT_VARIANT=slim
EOF
        echo "已切换到 14B (Qwen2.5)"
        ;;
    30b|30B)
        cat > "$ENV_FILE" << 'EOF'
# MyAgent 30B MoE 模型配置
LLAMA_MODEL=/root/llama.cpp/models/Qwen3-30B-A3B-Q4_K_M.gguf
CTX_SIZE=8192
NGL=99
LLAMA_PORT=8000
SINGLE_GPU_MODE=true
PROMPT_VARIANT=slim
EOF
        echo "已切换到 Qwen3-30B-A3B MoE"
        ;;
    *)
        # 用户指定了模型路径
        if [ -f "$ARG" ]; then
            cat > "$ENV_FILE" << EOF
# MyAgent 自定义模型配置
LLAMA_MODEL=$ARG
CTX_SIZE=8192
NGL=99
LLAMA_PORT=8000
SINGLE_GPU_MODE=true
PROMPT_VARIANT=slim
EOF
            echo "已切换到: $ARG"
        else
            echo "✗ 模型文件不存在: $ARG"
            echo "  用法: bash switch_model.sh /path/to/model.gguf"
            exit 1
        fi
        ;;
esac

echo "配置已写入: $ENV_FILE"
cat "$ENV_FILE"
echo ""
echo "重启中..."
bash "$SCRIPT_DIR/start.sh"
