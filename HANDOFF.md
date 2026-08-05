# MyAgent 项目移交文档 — 2026-08-06 01:25

## 一、项目身份

| 项目 | MyAgent — AMD Radeon GPU 私有 AI Agent 平台 |
|------|------|
| 赛事 | 2026 AMD AI DevMaster Hackathon · Track 2 |
| 截止 | **2026-08-06 23:59** |
| GitHub | https://github.com/bry9107795553/MyAgent.git |
| 分支 | main (最新: ee52df7) |
| 用户 | bry9107795553（小白） |

---

## 二、云端运行状态

| 服务 | 端口 | 状态 |
|------|------|:--:|
| llama-server (30B MoE) | :8000 | ✅ — 104 tok/s |
| FastAPI 后端 | :8080 | ✅ — 18角色/10工作组 |
| Nginx | :80/:8088 | ✅ |
| rc-tunnel 公网 | 8088→公网 | ✅ — 需手动获取 |

### 获取公网地址
```bash
export PATH="$HOME/.local/bin:$PATH"
rc-tunnel stop 2>/dev/null; sleep 2
nohup rc-tunnel expose --port 8088 > /tmp/rc-tunnel.log 2>&1 &
sleep 8
grep -oE 'https?://rc-[^ ]+' /tmp/rc-tunnel.log
```

### 一键启动/停止
```bash
cd /workspace/template-repos/template-2603/repo
bash start.sh   # 自愈启动
bash stop.sh    # 简单停止
```

### 更新代码
```bash
cd /workspace/template-repos/template-2603/repo
git pull origin main
cd frontend && rm -rf dist && npx vite build && cp -r dist/* /var/www/myagent/
# 如果改了后端 Python: bash stop.sh && bash start.sh
```

---

## 三、模型配置

`.env` 位置: `backend/.env`
```ini
LLAMA_MODEL=/root/llama.cpp/models/Qwen3-30B-A3B-Q4_K_M.gguf
CTX_SIZE=8192
NGL=99
LLAMA_PORT=8000
SINGLE_GPU_MODE=true
PROMPT_VARIANT=slim
```

换模型: `bash switch_model.sh [14b|30b|api|/路径/model.gguf]`

---

## 四、今晚修复清单（18项）

### 架构修复
| # | 修复 | 文件 |
|---|------|------|
| 1 | 流式模式支持工具调用 | `role_base.py` — `_call_llm_stream` |
| 2 | web_search 从占位变为真实搜索 | `search_tools.py` → 接L3知识库 |
| 3 | cleaner/deployer 授予工具权限 | `role_pool.json` |
| 4 | 流水线 `parallel_with` 真正并行 | `master.py` — asyncio.gather |
| 5 | `_should_revise` 返工机制生效 | `master.py` |
| 6 | coach 流水线模式只做 Phase 0 | `coach/prompt.txt` |
| 7 | tester/inspector 反幻觉约束 | `prompt.txt` |
| 8 | 通用对话走真流式逐 token | `master.py` — dispatch_stream |
| 9 | 30B MoE 提取 reasoning_content | `gateway.py` + `role_base.py` |
| 10 | 皮肤 list_skins 返回 variables | `skin/manager.py` |
| 11 | designer/writer 授予 file_write | `role_pool.json` |
| 12 | 工作台从模板创建模块链路 | `module_routes.py` + `generator.py` |

### 前端修复
| # | 修复 |
|---|------|
| 13 | 皮肤切换真正改 CSS 变量 + 记住选择 |
| 14 | HTML 产出区加 iframe 预览 |
| 15 | 新建/删除对话 + localStorage 持久化 |
| 16 | 对话历史移到右侧栏常驻（空闲时可见） |
| 17 | 消息气泡不溢出 + 按内容宽度收缩 |
| 18 | 全局浅色主题（App.vue + ChatView 29处替换） |

---

## 五、待完成（明天截止前）

| 优先级 | 任务 |
|:--:|------|
| 🔴 | **录制演示视频**（3-5分钟，推荐OBS录屏） |
| 🔴 | **Fork AMD-DEV-CONTEST + 提交 PR** |
| 🟡 | 写参赛说明/README 完善 |
| 🟡 | 测试全功能：开发/写报告/翻译/代码审查/邮件 |
| 🟢 | 最终 Git push + 打 tag |

### 演示推荐场景（5个）
1. 三栏界面展示(15s) → 左侧角色/工作组
2. dev_full 开发待办事项(90s 核心) → 演示效果最好
3. 写报告 → 自动 knowledge_retriever→writer→checker
4. 皮肤切换 → 点暖白变浅色
5. 工作台 → 拖拽模块

---

## 六、已知限制

| 限制 | 说明 |
|------|------|
| 30B 思考模式 | 小 token 时 content 为空，已加 reasoning 回退 |
| rc-tunnel 60s 回收 | 空闲后需重开隧道 |
| 单 GPU 模式 | visual_analyzer 无多模态能力 |
| web_search | 本地知识库搜索，非真联网 |

---

## 七、关键文件索引

| 文件 | 内容 |
|------|------|
| `backend/main.py` | FastAPI 入口 |
| `backend/core/role/master.py` | 主控调度中枢 (1380行) |
| `backend/core/role/role_base.py` | 角色基类 + 工具循环 |
| `backend/core/llm/gateway.py` | LLM 统一入口 |
| `backend/core/tools/builtin/` | 6个内置工具 |
| `data/role_pool.json` | 18角色定义+工具权限 |
| `data/workgroups/` | 10个工作组配置 |
| `frontend/src/views/ChatView.vue` | 核心聊天界面 (940行) |
| `frontend/src/App.vue` | 根组件 + CSS 变量 |
| `reports/` | 架构审计+调用链分析 |
| `start.sh` / `stop.sh` | 自愈启停脚本 |
| `.env.template` | 模型配置模板 |

---

## 八、架构概要

```
用户浏览器 → rc-tunnel → Nginx:80 → 前端静态
                                   → WebSocket → FastAPI:8080
                                     → BaseAgent → MasterRole
                                       → 工作组匹配
                                       → 角色流水线 (coach→designer→dev→inspector→tester→deployer→cleaner)
                                         → RoleBase.execute()
                                           → LLMGateway.chat()
                                             → llama-server:8000 (Qwen3-30B MoE)
                                               → AMD Radeon PRO W7900 48GB / ROCm 7.2
```
