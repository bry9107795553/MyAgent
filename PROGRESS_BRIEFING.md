# MyAgent 项目进度简报 — 2026-08-05 22:37

> 交接用。新对话先读这份，再看 STATUS_REPORT.md 和 EXECUTION_LOG.md。

---

## 一、项目基本信息

| 字段 | 内容 |
|------|------|
| 项目 | MyAgent — AMD Radeon GPU 私有 AI Agent 平台 |
| 赛道 | 2026 AMD AI DevMaster Hackathon · Track 2 |
| 截止 | **2026-08-06 23:59**（剩余约 25 小时） |
| 用户 | bry9107795553（小白，需代劳命令行） |
| GitHub | https://github.com/bry9107795553/MyAgent.git |
| 云端 | https://rc-83305f57d63fc9d3.radeon.firstdg.ai |
| GPU | AMD Radeon PRO W7900 48GB · ROCm 7.2.1 |

---

## 二、已完成 ✅

### 代码层面（全部已 push）
| 改造 | 状态 |
|------|:--:|
| Plan A — 18 份 prompt 精简（15,317 CJK vs 38,190，-59.9%） | ✅ |
| Plan C — 经验效用评分 + 知识 TTL + 评估员角色 | ✅ |
| P0 单卡模式修复（single_gpu_mode=True，三层防御） | ✅ |
| 工具调用闭环（file_write/read 真落盘，developer 角色可用） | ✅ |
| 工具白名单清理（删除 17 个角色的虚假工具名） | ✅ |
| ChatView.vue 三栏界面（左面板+对话+产出区） | ✅ |
| BrowserView.vue 文件浏览器 | ✅ |
| Nginx WebSocket 代理修复 | ✅ |
| dev_full 流水线精简（9步→7步，砍掉冗余 coach 调用） | ✅ |
| 反幻觉 prompt（coach 禁止提问 / inspector+tester 不编造） | ✅ |
| 冒烟测试 + 平台全功能测试脚本 | ✅ |

### 部署层面
| 项目 | 状态 |
|------|:--:|
| 云端后端（18角色/10工作组/single_gpu） | ✅ 运行中 |
| 云端三栏前端 | ✅ 运行中 |
| WebSocket 聊天 | ✅ 通 |
| dev_full 10 步流水线 | ✅ 跑通 |

---

## 三、当前问题 🔴

### 核心瓶颈：模型质量
- **当前模型**：Qwen2.5-14B-Instruct Q4_K_M（8.4GB）
- **问题**：coach 反复提问、inspector 编造不存在的代码、tester 编造测试覆盖率
- **根因**：14B Q4_K_M 量化质量不足以支撑多步 Agent 推理

### 解决方案（进行中）
- **正在下载**：Qwen3-30B-A3B-Instruct Q4_K_M（17GB，MoE 架构）
- **来源**：ModelScope 国内镜像（快速）
- **下载命令**：
```bash
cd /root/llama.cpp/models && wget -c \
  "https://modelscope.cn/models/lmstudio-community/Qwen3-30B-A3B-GGUF/resolve/master/Qwen3-30B-A3B-Q4_K_M.gguf"
```
- **下载完成后切换**：
```bash
cd /workspace/template-repos/template-2603/repo && bash stop.sh
# 修改 .env 中的模型路径为新模型
sed -i 's/qwen2.5-14b.*\.gguf/Qwen3-30B-A3B-Q4_K_M.gguf/' backend/.env
bash start.sh
```

---

## 四、待完成 🔴（明天截止前必须做）

| 优先级 | 任务 | 依赖 |
|:--:|------|------|
| 🔴 | **下载+切换 Qwen3-30B 模型** | 正在进行 |
| 🔴 | **验证新模型质量**（跑 dev_full 看输出） | 模型切换后 |
| 🔴 | **录制演示视频**（3-5 分钟） | 质量验证通过 |
| 🔴 | **Fork + PR**（AMD-DEV-CONTEST repo） | 随时可做 |
| 🟡 | **A/B 测速数据**（14B vs 30B tokens/s） | 可选，有剩余时间 |
| 🟡 | **PPT / 海报** | 可选 |
| 🟢 | **Git push 最终版** | 完成后 |

---

## 五、演示推荐场景

1. **三栏界面展示**（15s）— 展开左栏角色/工作组
2. **dev_full 流水线**（90s 核心戏眼）— "开发一个React待办事项应用"
3. **代码审查**（30s）— 给坏代码触发 dev_code_review
4. **经验投毒**（60s 创意分）— 改 experience JSON → 评估员 −2 → 自动淘汰
5. **AMD GPU 画面**（10s）— 终端分屏显示 rocm-smi + htop

---

## 六、云端速查命令

```bash
# 项目目录
cd /workspace/template-repos/template-2603/repo

# 拉取代码
git pull origin main

# 重启服务
bash stop.sh && bash start.sh

# 查看日志
tail -f /tmp/backend.log
tail -f /tmp/llama.log

# 检查模型
ls -lh /root/llama.cpp/models/

# 模型切换（14b ↔ 32b/30b）
bash switch_model.sh 14b    # 14B
# 或改 .env 后 restart

# 冒烟测试
bash tests/demo_smoke_test.sh

# 前端部署（如需要）
cd frontend && rm -rf dist && npx vite build && cp -r dist/* /var/www/myagent/
```

---

## 七、关键文件索引

| 文件 | 内容 |
|------|------|
| STATUS_REPORT.md | 完整项目状态报告 |
| BRIEFING.md | 赛事要求 + 项目简报 |
| EXECUTION_LOG.md | 所有改动执行日志 |
| REFACTOR_PLAN.md | Plan A/B/C 方案设计 |
| CLOUD_BENCHMARK.md | A/B 测速方案 |
| PROGRESS_BRIEFING.md | 本文件 |

---

## 八、当前状态卡在哪里

**模型下载中**。Qwen3-30B Q4_K_M 约 17GB，从 ModelScope 下载。完成后切换模型、重启、验证质量。

**演示视频**是新模型验证通过后的第一优先级。
