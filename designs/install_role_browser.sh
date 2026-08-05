#!/usr/bin/env bash
# 一键部署 MyAgent 功能中心页 — 挂在公网入口的 /browse/ 路径
# 不动 MyAgent 主代码，只加一个独立静态资源目录 + nginx location 块
# 失败时自动回滚（还原 nginx.conf 备份）
set -e

BROWSE_DIR="/var/www/html/browse"
HTML_SRC="/root/browse.html"   # 用户会通过 heredoc 写入
NGINX_CONF="/etc/nginx/nginx.conf"
BAK_CONF="/etc/nginx/nginx.conf.bak.browse"

echo "===== MyAgent 功能中心页部署 ====="

# ---- 1. 准备目录 ----
echo "[1/5] 准备目录 ${BROWSE_DIR}"
mkdir -p "${BROWSE_DIR}"

# ---- 2. 写入 HTML（用户已 heredoc 写入 ${HTML_SRC}） ----
echo "[2/5] 写入 index.html → ${BROWSE_DIR}/index.html"
if [ ! -f "${HTML_SRC}" ]; then
    echo "[FAIL] ${HTML_SRC} 不存在。请先粘贴 HTML heredoc 到 /root/browse.html"
    exit 1
fi
cp -f "${HTML_SRC}" "${BROWSE_DIR}/index.html"
chmod 644 "${BROWSE_DIR}/index.html"

# ---- 3. 备份 nginx.conf ----
echo "[3/5] 备份 ${NGINX_CONF} → ${BAK_CONF}"
if [ ! -f "${BAK_CONF}" ]; then
    cp -f "${NGINX_CONF}" "${BAK_CONF}"
fi

# ---- 4. 注入 location /browse/ block（精准插入到 location = /api/agents 之前） ----
echo "[4/5] 注入 nginx location /browse/ 块"
python3 <<'PYEOF'
import re, pathlib
p = pathlib.Path("/etc/nginx/nginx.conf")
src = p.read_text(encoding="utf-8")

# 如果已经有了就不重复加（幂等）
if "/browse/" in src and "alias /var/www/html/browse" in src:
    print("  → location /browse/ 已存在，跳过")
else:
    new_block = (
        "        # 外挂功能中心页 (独立静态资源, 不动 MyAgent 主代码)\n"
        "        location /browse/ {\n"
        "            alias /var/www/html/browse/;\n"
        "            index index.html;\n"
        "            try_files $uri $uri/ /browse/index.html;\n"
        "        }\n\n"
    )
    # 插在 "location /api/ " 块之前
    marker = "        # FastAPI 后端 API\n        location /api/ {"
    if marker not in src:
        # 兜底：插在 listen 8088; 那行之后
        marker = "        listen 8088;"
    src = src.replace(marker, new_block + marker, 1)
    p.write_text(src, encoding="utf-8")
    print("  → 已注入 location /browse/ 块")
PYEOF

# ---- 5. 测试 + 重启 nginx ----
echo "[5/5] nginx -t 校验 → 重启"
if ! nginx -t; then
    echo "[FAIL] nginx -t 不通过！回滚 nginx.conf"
    cp -f "${BAK_CONF}" "${NGINX_CONF}"
    nginx -t || true
    exit 2
fi
pkill -TERM nginx 2>/dev/null || true
sleep 1
nginx

# ---- 验证 ----
echo ""
echo "===== 部署完成 ====="
echo "测试命令（云端终端）："
echo "  curl -I http://localhost:8088/browse/"
echo "  curl -s http://localhost:8088/browse/ | head -5"
echo ""
echo "用户在浏览器打开（公网入口，需 tunnel 端口 8088 已通过 nohup rc-tunnel 暴露）："
echo "  https://<your-tunnel>.radeon.firstdg.ai/browse/"
