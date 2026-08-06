# MyAgent 项目移交 — 2026-08-06 01:50

## 一、项目身份

| 项目 | MyAgent — AMD Radeon GPU 私有 AI Agent 平台 |
|------|------|
| 赛事 | 2026 AMD AI DevMaster Hackathon · Track 2 |
| 截止 | **2026-08-06 23:59** (约22小时) |
| GitHub | https://github.com/bry9107795553/MyAgent.git |
| 分支 | main (最新: 868a2fd) |
| 用户 | bry9107795553（小白，需代劳命令行） |

---

## 二、云端服务

| 服务 | 地址 | 状态 |
|------|------|:--:|
| llama-server | :8000 — Qwen3-30B-A3B MoE | ✅ 104 tok/s |
| FastAPI 后端 | :8080 — 18角色/10工作组 | ✅ |
| Nginx | :80 / :8088 | ✅ |
| rc-tunnel | 8088 → 公网 | ✅ 需手动获取 |

### 获取公网 URL
```bash
export PATH="$HOME/.local/bin:$PATH"
rc-tunnel stop 2>/dev/null; sleep 2
nohup rc-tunnel expose --port 8088 > /tmp/rc-tunnel.log 2>&1 &
sleep 8
grep -oE 'https?://rc-[^ ]+' /tmp/rc-tunnel.log
```

### 运维命令
```bash
cd /workspace/template-repos/template-2603/repo
bash start.sh   # 自愈一键启动
bash stop.sh    # 停止
bash switch_model.sh [30b|14b|api]   # 切换模型
```

### 更新代码（拉 + 前端构建 → 无需重启动）
```bash
cd /workspace/template-repos/template-2603/repo
git pull origin main
cd frontend && rm -rf dist && npx vite build && cp -r dist/* /var/www/myagent/
# 如果改了 Python 后端: bash stop.sh && bash start.sh
```

---

## 三、当前进度

### ✅ 已完成

**后端修复 (8项):** 同上

**前端修复 (10+1项):**
| 修复 |
|------|
| 皮肤切换 → CSS 变量 + localStorage 记忆 |
| HTML 产出区 → iframe 预览 |
| 对话管理 → 新建/删除/历史 (localStorage) |
| 全局浅色主题 → App.vue + ChatView |
| 工作组移出左侧栏 → 顶部横栏 chips |
| 阅览页移除重复的工作组 tab |
| 消息气泡不溢出 + 浅色统一 |
| 输入框上移 (padding 缩小) |
| 气泡按内容宽度收缩 |
| **🆕 全局CSS设计系统 → Linear+Claude风格 (2026-08-06 08:58)** |

**架构清理:** 23死文件 + 3报告

### ✅ 最新完成：UI 设计同步 (2026-08-06)

`designs/chat-preview.html` 的 Linear+Claude 设计系统已同步到产品代码：

| 改动 | 文件 | 说明 |
|------|------|------|
| 全局 CSS 变量升级 | `App.vue` | 13 个设计 token：`--accent` / `--bg-app` / `--bg-surface` / `--text-primary` 等 |
| 聊天界面视觉重构 | `ChatView.vue` | 全部 500+ 行样式重写，统一使用 CSS 变量 |
| 布局微调 | `ChatView.vue` | 左栏 280→260px，右栏 360→340px，消息居中 max-width 740px |
| 构建验证 | `frontend/` | ✅ vite build 通过，54 模块，零错误 |

### 🔴 待完成（今晚）

| 优先级 | 任务 | 说明 |
|:--:|------|------|
| 🔴 | **部署到云端** | 在云服务器执行更新命令（见下方） |
| 🔴 | **录制演示视频** | 3-5分钟 OBS，按演示脚本录 |
| 🔴 | **Fork + PR 提交** | GitHub 操作 |
| 🟡 | 全功能验收测试 | 部署后测试关键流程 |
| 🟢 | 最终 push | `git push origin main` |

---

## 四、演示推荐脚本

| 时间 | 场景 | 操作 |
|------|------|------|
| 15s | 界面展示 | 左栏对话历史 + 顶部工作组横栏 + 干净chat |
| 90s | **dev_full 核心** | 输入"开发一个React待办事项"→ 7步流水线 → 预览 |
| 30s | 写报告 | "写一份AMD GPU市场分析"→ 检索→写作→质检 |
| 15s | 皮肤切换 | 皮肤页 → 点暖白 → 整站变浅 |
| 10s | GPU 画面 | 终端分屏 `rocm-smi` + `htop` |

---

## 五、关键文件

| 文件 | 说明 |
|------|------|
| `backend/core/role/master.py` | 主控调度 (核心中枢) |
| `backend/core/role/role_base.py` | 角色基类 + 工具循环 |
| `backend/core/llm/gateway.py` | LLM 统一入口 |
| `backend/core/tools/builtin/` | 6 个内置工具 |
| `data/role_pool.json` | 18 角色 + 工具权限 |
| `data/workgroups/` | 10 个工作组 JSON |
| `frontend/src/views/ChatView.vue` | 聊天界面 (~980行) |
| `frontend/src/App.vue` | 根组件 + 全局 CSS |
| `designs/chat-preview.html` | **最新 UI 样图 (Linear+Claude风格)** |
| `reports/architecture-audit.md` | 架构审计报告 |
| `reports/backend-chain-analysis.md` | 调用链路分析 |
| `start.sh` / `stop.sh` | 自愈启停 |
| `backend/.env.template` | 模型配置模板 |

---

## 六、设计方向（待确认）

`designs/chat-preview.html` — 参考 Linear + Claude + ChatGPT 的克制专业风格：

- **左侧栏**：对话历史常驻，悬浮出删除按钮
- **顶部横栏**：工作组 chips 单行横向滚动
- **对话区**：居中 max-width 740px，两边留白
- **输入框**：白底圆角 + 紫蓝 focus 光环
- **配色**：#fafbfc 底 + #4f46e5 紫蓝强调 + #eef2ff 柔化

---

## 七、架构速查

```
浏览器 → rc-tunnel → Nginx:80 → 前端静态 (Vue 3)
                               → WebSocket → FastAPI:8080
                                 → MasterRole(调度)
                                   → 工作组匹配 → 流水线执行
                                     → RoleBase → LLMGateway
                                       → llama-server:8000
                                         → Qwen3-30B MoE → W7900 48GB/ROCm
```

---

## 八、注意事项

- rc-tunnel 空闲 60s 回收，演示前需重新获取 URL
- 模型重启需 1-2 分钟加载到显存
- Ctrl+F5 强刷解决浏览器缓存
- 30B MoE 小 token 时可能 content 为空（已修）
- 单 GPU 模式，18 角色共享 llama_base_url
