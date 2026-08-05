#!/bin/bash
# =====================================================
# MyAgent 云端前端部署 — 粘贴到 JupyterLab 终端运行
# =====================================================
set -e

echo "=== 步骤1: 定位项目目录 ==="
D="/workspace/template-repos/template-2603/repo"
[ ! -f "$D/backend/main.py" ] && D=$(find /workspace -maxdepth 5 -name "main.py" -path "*/backend/main.py" 2>/dev/null | head -1 | xargs dirname | xargs dirname)
if [ -z "$D" ] || [ ! -f "$D/backend/main.py" ]; then
    echo "找不到项目目录，请确认已进入正确的云端工作区"
    exit 1
fi
echo "项目目录: $D"

echo ""
echo "=== 步骤2: 拉取最新代码 ==="
cd "$D"
# 尝试 git pull（如果 CA 证书有问题则从本地文件部署）
if git pull origin main 2>/dev/null; then
    echo "代码已更新"
else
    echo "git pull 不可用，使用本地已有文件"
fi

echo ""
echo "=== 步骤3: 写入 ChatView.vue 三栏界面 ==="
# 从 base64 还原 ChatView.vue
python3 << 'PYEOF'
import base64, pathlib

# ChatView.vue — 三栏界面（base64 编码）
chat_b64 = "PHRlbXBsYXRlPgogIDxkaXYgY2xhc3M9ImFnZW50LXBsYXRmb3JtIj4KICAgIDwhLS0gPT09PT0g5bem5qCPOiDns7vnu5/nirbmgIEgKyDmmbrog73kvZMgKyDlt6XkvZznu4QgKyDop5LoibIgPT09PT0gLS0+CiAgICA8YXNpZGUgY2xhc3M9ImxlZnQtcGFuZWwiPgogICAgICA8ZGl2IGNsYXNzPSJzeXMtYmFyIiA6Y2xhc3M9Insgb25saW5lOiBsbG1PbmxpbmUgfSIgQGNsaWNrPSJzaG93U3lzPSFzaG93U3lzIj4KICAgICAgICA8c3BhbiBjbGFzcz0ic3lzLWRvdCI+PC9zcGFuPgogICAgICAgIDxzcGFuIGNsYXNzPSJzeXMtdGV4dCI+e3sgbGxtT25saW5lID8gbW9kZWxOYW1lIDogJ+emu+e6vycgfX08L3NwYW4+CiAgICAgIDwvZGl2PgogICAgICA8ZGl2IHYtaWY9InNob3dTeXMiIGNsYXNzPSJzeXMtZGV0YWlsIj4KICAgICAgICA8ZGl2IGNsYXNzPSJrdiI+PHNwYW4+5qih5Z6LPC9zcGFuPjxzcGFuPnt7IG1vZGVsTmFtZSB9fTwvc3Bhbj48L2Rpdj4KICAgICAgICA8ZGl2IGNsYXNzPSJrdiI+PHNwYW4+6KeS6ImyPC9zcGFuPjxzcGFuPnt7IHJvbGVzLmxlbmd0aCB9fTwvc3Bhbj48L2Rpdj4KICAgICAgICA8ZGl2IGNsYXNzPSJrdiI+PHNwYW4+5bel5L2c57uEPC9zcGFuPjxzcGFuPnt7IHdvcmtncm91cHMubGVuZ3RoIH19PC9zcGFuPjwvZGl2PgogICAgICA8L2Rpdj4KCiAgICAgIDxkaXYgY2xhc3M9InNlY3Rpb24iPgogICAgICAgIDxkaXYgY2xhc3M9InNoZWFkIj7mmbrog73kvZM8L2Rpdj4KICAgICAgICA8ZGl2IHYtZm9yPSJhIGluIGFnZW50cyIgOmtleT0iYS5hZ2VudF9pZCIgY2xhc3M9ImEtaXRlbSIgOmNsYXNzPSJ7IGFjdGl2ZTogY3VycmVudEFnZW50PT09YS5hZ2VudF9pZCB9IgogICAgICAgICAgICAgQGNsaWNrPSJzZWxlY3RBZ2VudChhLmFnZW50X2lkKSI+CiAgICAgICAgICA8c3BhbiBjbGFzcz0iYS1pY29uIj7wn6SWPC9zcGFuPgogICAgICAgICAgPGRpdj48ZGl2IGNsYXNzPSJhLW5hbWUiPnt7IGEubmFtZSB9fTwvZGl2PjxkaXYgY2xhc3M9ImEtZGVzYyI+e3sgYS5kZXNjcmlwdGlvbiB9fTwvZGl2PjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICA8L2Rpdj4KCiAgICAgIDxkaXYgY2xhc3M9InNlY3Rpb24iPgogICAgICAgIDxkaXYgY2xhc3M9InNoZWFkIiBAY2xpY2s9IndnT3Blbj0hd2dPcGVuIj7lt6XkvZznu4Qge3sgd2dPcGVuPyfilrQnOifilr4nIH19PC9kaXY+CiAgICAgICAgPGRpdiB2LWlmPSJ3Z09wZW4iIGNsYXNzPSJzbGlzdCI+CiAgICAgICAgICA8ZGl2IHYtZm9yPSJ3ZyBpbiB3b3JrZ3JvdXBzIiA6a2V5PSJ3Zy5pZCIgY2xhc3M9IndnLWNoaXAiIEBjbGljaz0idHJpZ2dlcldnKHdnKSI+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9IndnLXRvcCI+PHNwYW4+e3sgd2cubmFtZSB9fTwvc3Bhbj48c3BhbiBjbGFzcz0ic3RlcHMiPnt7IHdnLnBpcGVsaW5lX3N0ZXBzIH19PGJyLz48L3NwYW4+PC9kaXY+CiAgICAgICAgICAgIDxkaXYgY2xhc3M9IndnLWtleXdvcmRzIj57eyAod2cudHJpZ2dlcl9rZXl3b3Jkc3x8W10pLnNsaWNlKDAsMykuam9pbignIOKJoyAnKSB9fTwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgIDwvZGl2PgoKICAgICAgPGRpdiBjbGFzcz0ic2VjdGlvbiIgc3R5bGU9ImZsZXg6MSI+CiAgICAgICAgPGRpdiBjbGFzcz0ic2hlYWQiIEBjbGljaz0icm9sZU9wZW49IXJvbGVPcGVuIj7op5LoibIgKHt7IHJvbGVzLmxlbmd0aCB9fSkge3sgcm9sZU9wZW4/J8KwJzonwrYnIH19PC9kaXY+CiAgICAgICAgPGRpdiB2LWlmPSJyb2xlT3BlbiIgY2xhc3M9InNsaXN0Ij4KICAgICAgICAgIDxkaXYgdi1mb3I9IihncnMsZ3JwKSBpbiByb2xlR3JvdXBzIiA6a2V5PSJncnAiPgogICAgICAgICAgICA8ZGl2IGNsYXNzPSJyb2xlLWdyb3VwLWxhYmVsIj57eyBncm91cExhYmVsc1tncnBdfHxncnAgfX08L2Rpdj4KICAgICAgICAgICAgPGRpdiB2LWZvcj0iciBpbiBncnMiIDprZXk9InIuaWQiIGNsYXNzPSJyb2xlLWNoaXAiPgogICAgICAgICAgICAgIDxzcGFuIGNsYXNzPSJyb2xlLWRvdCIgOmNsYXNzPSJnLSIrci5ncHVfYWZmaW5pdHkiPjwvc3Bhbj4KICAgICAgICAgICAgICA8c3BhbiBjbGFzcz0icm9sZS1uYW1lIj57eyByLm5hbWUgfX08L3NwYW4+CiAgICAgICAgICAgIDwvZGl2PgogICAgICAgICAgPC9kaXY+CiAgICAgICAgPC9kaXY+CiAgICAgIDwvZGl2PgogICAgPC9hc2lkZT4KCiAgICA8IS0tID09PT09IOS4reaPkDog5a+56K+dID09PT09IC0tPgogICAgPGRpdiBjbGFzcz0iY2hhdC1jb2wiPgogICAgICA8ZGl2IGNsYXNzPSJtZXNzYWdlcyIgcmVmPSJtc2dFbCI+CiAgICAgICAgPGRpdiB2LWlmPSJtc2dzLmxlbmd0aD09PTAmJiFzdHJlYW1pbmciIGNsYXNzPSJlbXB0eS1tc2ciPgogICAgICAgICAgPGRpdiBjbGFzcz0iZW1wdHktaWNvbiI+8J+SqjwvZGl2PgogICAgICAgICAgPGRpdiBjbGFzcz0iZW1wdHktdGl0bGUiPk15QWdlbnQg5bey57uP5Ye65Y+RPC9kaXY+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJwcm9tcHQtc3VnZ2VzdCI+CiAgICAgICAgICAgIDxzcGFuIGNsYXNzPSJwcm9tcHQtcGlsbCIgQGNsaWNrPSJzZW5kUXVpY2soJ+aIkeePreimgeWBmuW8j+W6j+W8gOWPkScpIj7nqIvlup/lvIDlj5E8L3NwYW4+CiAgICAgICAgICAgIDxzcGFuIGNsYXNzPSJwcm9tcHQtcGlsbCIgQGNsaWNrPSJzZW5kUXVpY2soJ+WuoeafpeS7o+eggScpIj7ku6PnoIHlrqHmn6U8L3NwYW4+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8ZGl2IHYtZm9yPSIobSxpKSBpbiBtc2dzIiA6a2V5PSJpIiBjbGFzcz0ibXNnIiA6Y2xhc3M9Im0ucm9sZSI+CiAgICAgICAgICA8ZGl2IGNsYXNzPSJtc2ctYnViYmxlIiB2LWh0bWw9Im1hcmtkb3duKG0uY29udGVudCkiPjwvZGl2PgogICAgICAgIDwvZGl2PgogICAgICAgIDxkaXYgdi1pZj0ic3RyZWFtaW5nIiBjbGFzcz0ibXNnIGFzc2lzdGFudCI+PGRpdiBjbGFzcz0ibXNnLWJ1YmJsZSI+e3sgc3RyZWFtQnVmZmVyIH19PHNwYW4gY2xhc3M9ImN1cnNvciI+fDwvc3Bhbj48L2Rpdj48L2Rpdj4KICAgICAgPC9kaXY+CiAgICAgIDxkaXYgY2xhc3M9ImlucHV0LWJhciI+CiAgICAgICAgPGlucHV0IHYtbW9kZWw9ImlucHV0VGV4dCIgY2xhc3M9ImlucHV0LWZpZWxkIiBAa2V5dXAuZW50ZXI9InNlbmRNZXNzYWdlIgogICAgICAgICAgOnBsYWNlaG9sZGVyPSdpbnB1dFRleHQ/J+Whq+WFpeS4gOS4quagh+iusOOAgemDqOe9sn5+JzogJ+i+k+WFpeS4gOS4quagh+iusO+8jOmDqOe9suaJp+ihjCcrJycKICAgICAgICAgIDpkaXNhYmxlZD0ic3RyZWFtaW5nIiAvPgogICAgICAgIDxidXR0b24gY2xhc3M9ImJ0bi1zZW5kIiBAY2xpY2s9InNlbmRNZXNzYWdlIiA6ZGlzYWJsZWQ9InN0cmVhbWluZyI+e3sgc3RyZWFtaW5nID8gJ+afpeeUqOKApuKApiIgOiAn6aG26YCBJyB9fTwvYnV0dG9uPgogICAgICA8L2Rpdj4KICAgIDwvZGl2PgoKICAgIDwhLS0gPT09PT0g5Y+z5qCPOiDkuqfoh7rljLoocmlnaHQgcGFuZWwpID09PT09IC0tPgogICAgPGFzaWRlIGNsYXNzPSJyaWdodC1wYW5lbCI+CiAgICAgIDxkaXYgY2xhc3M9InBhbmVsLWhlYWQiPgogICAgICAgIDxzcGFuIGNsYXNzPSJwYW5lbC1iYWRnZSIgOmNsYXNzPSJ7IHBpcGVsaW5lQWN0aXZlID8gJ2FjdGl2ZScgOiAnaWRsZScgfSI+e3sgcGlwZWxpbmVBY3RpdmUgPyAn5omn6KGM5Li75Lq6LicgOiAn5bex57uPJyB9fTwvc3Bhbj4KICAgICAgICA85Lqn5Ye65Yy6CiAgICAgIDwvZGl2PgogICAgICA8ZGl2IGNsYXNzPSJwYW5lbC1ib2R5Ij4KICAgICAgICA8IS0tIOmTuuihjOatpemqpCAtLT4KICAgICAgICA8ZGl2IHYtaWY9ImRpc3BhdGNoU3RlcHMubGVuZ3RoPjAiIGNsYXNzPSJkaXNwYXRjaC1zdGVwcyI+CiAgICAgICAgICA8ZGl2IHYtZm9yPSIocyxpKSBpbiBkaXNwYXRjaFN0ZXBzIiA6a2V5PSJpIiBjbGFzcz0ic3RlcCIgOmNsYXNzPSJ7CiAgICAgICAgICAgIHBlbmRpbmc6IHMuc3RhdHVzPT09J3BlbmRpbmcnLAogICAgICAgICAgICBydW5uaW5nOiBzLnN0YXR1cz09PSdydW5uaW5nJywKICAgICAgICAgICAgZG9uZTogcy5zdGF0dXM9PT0nZG9uZScsCiAgICAgICAgICAgIGZhaWxlZDogcy5zdGF0dXM9PT0nZmFpbGVkJwogICAgICAgICAgfSIgQGNsaWNrPSJzZWxlY3RTdGVwKGkpIj4KICAgICAgICAgICAgPHNwYW4gY2xhc3M9InN0ZXAtaWNvbiI+e3sgCiAgICAgICAgICAgICAgcy5zdGF0dXM9PT0nZG9uZScgPyAn4pyFJyA6IAogICAgICAgICAgICAgIHMuc3RhdHVzPT09J2ZhaWxlZCcgPyAn5q2JJyA6IAogICAgICAgICAgICAgIHMuc3RhdHVzPT09J3J1bm5pbmcnID8gJ+KAoCcgOiAKICAgICAgICAgICAgICBpKzEgICAgICAgICAgICAgICAgICAgICAgICAKICAgICAgICAgICAgfX08L3NwYW4+CiAgICAgICAgICAgIDxzcGFuIGNsYXNzPSJzdGVwLXJvbGUiPnt7IHMucm9sZSB9fTwvc3Bhbj4KICAgICAgICAgICAgPHNwYW4gdi1pZj0icy5kdXJhdGlvbiIgY2xhc3M9InN0ZXAtZHVyYXRpb24iPnt7IHMuZHVyYXRpb24gfX3np7s8L3NwYW4+CiAgICAgICAgICA8L2Rpdj4KICAgICAgICA8L2Rpdj4KICAgICAgICA8IS0tIOm7mOiupOepuumXtCAtLT4KICAgICAgICA8ZGl2IHYtaWY9ImRpc3BhdGNoU3RlcHMubGVuZ3RoPT09MCIgY2xhc3M9InBhbmVsLWVtcHR5Ij4KICAgICAgICAgIOaOpeaIkOS4gOasoemTuuihjOWQju+8jOS7p+WKoeatpemqpOS8muaYvuijnOatpOWkhDwvZGl2PgogICAgICA8L2Rpdj4KICAgIDwvYXNpZGU+CiAgPC9kaXY+CjwvdGVtcGxhdGU+"

# 如果 base64 正确，写入文件
try:
    content = base64.b64decode(chat_b64).decode('utf-8')
    target = pathlib.Path.cwd() / "frontend" / "src" / "views" / "ChatView.vue"
    target.write_text(content, encoding='utf-8')
    print(f"ChatView.vue 已写入 ({len(content)} 字符)")
except Exception as e:
    print(f"base64 解码失败，尝试直接读取本地文件: {e}")
    # fallback: 从已存在的文件读取
    local = pathlib.Path.cwd() / "frontend" / "src" / "views" / "ChatView.vue"
    if local.exists():
        print(f"使用本地文件 ({local.stat().st_size} bytes)")
    else:
        print("错误: ChatView.vue 不存在！")
PYEOF

echo ""
echo "=== 步骤4: 构建前端 ==="
cd "$D/frontend"
rm -rf dist 2>/dev/null || true
npx vite build 2>&1

echo ""
echo "=== 步骤5: 部署到 Nginx ==="
TARGET=/var/www/myagent
mkdir -p "$TARGET"
rm -rf "$TARGET"/*
cp -r dist/* "$TARGET"/

echo ""
echo "============================================"
echo "  部署完成！"
echo "  访问: https://rc-83305f57d63fc9d3.radeon.firstdg.ai"
echo "============================================"
ls -la "$TARGET/index.html"
