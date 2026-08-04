#!/bin/bash
# =============================================================================
# MyAgent Docker 入口脚本
# 1. 验证环境变量
# 2. 确保默认模型 → 云端 API (智谱)
# 3. 启动 FastAPI + Nginx
# =============================================================================
set -e

echo "========================================"
echo "  MyAgent Docker — AMD ROCm 模拟环境"
echo "========================================"
echo ""

# ===== 1. 检查环境变量 =====
echo "[1/4] 检查环境变量..."

if [ -n "$ZHIPU_API_KEY" ]; then
    echo "  ✓ ZHIPU_API_KEY 已设置"
else
    echo "  ⚠ ZHIPU_API_KEY 未设置!"
    echo "    LLM 推理将不可用，请设置环境变量:"
    echo "    export ZHIPU_API_KEY=your_key_here"
    echo "    或修改 .env.docker 文件"
fi

# 设置默认模型 (云端智谱优先)
export DEFAULT_MODEL="${DEFAULT_MODEL:-cloud-zhipu}"
echo "  默认模型: $DEFAULT_MODEL"

# ===== 2. 切换默认模型 =====
echo ""
echo "[2/4] 配置模型..."

# 备份原始 models.yaml
cp /app/backend/config/models.yaml /app/backend/config/models.yaml.bak

# 如果默认模型是 cloud-zhipu，交换 profile 顺序让它成为第一个
if [ "$DEFAULT_MODEL" = "cloud-zhipu" ]; then
    python3 -c "
import yaml
with open('/app/backend/config/models.yaml', 'r') as f:
    config = yaml.safe_load(f)
profiles = config.get('profiles', [])
# 把 cloud-zhipu 移到第一位
for i, p in enumerate(profiles):
    if p['id'] == 'cloud-zhipu':
        profiles.insert(0, profiles.pop(i))
        break
config['profiles'] = profiles
with open('/app/backend/config/models.yaml', 'w') as f:
    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
print('  ✓ 默认模型已切换为 cloud-zhipu')
"
fi

# ===== 3. 设置 Nginx =====
echo ""
echo "[3/4] 启动 Nginx..."

# 确保 Nginx 日志目录存在
mkdir -p /var/log/nginx

# 启动 Nginx (前台)
nginx -g 'daemon off;' &
NGINX_PID=$!
echo "  ✓ Nginx 已启动 (PID: $NGINX_PID)"

# ===== 4. 启动 FastAPI =====
echo ""
echo "[4/4] 启动 FastAPI 后端..."

cd /app/backend
source venv/bin/activate

echo ""
echo "========================================"
echo "  服务启动中..."
echo "  API:    http://localhost:8080/api"
echo "  前端:   http://localhost/"
echo "  文档:   http://localhost:8080/docs"
echo "========================================"
echo ""

# 启动 FastAPI
exec uvicorn main:app --host 0.0.0.0 --port 8080 --log-level info