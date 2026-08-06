# MyAgent 项目交接文档

> **日期**：2026-08-06  
> **截止时间**：23:59  
> **本次改动**：30 commits，~3000 行代码  
> **状态**：云端实例正在调试，流水线基本可跑但部分环节仍需优化

---

## 一、项目概况

**MyAgent** — 19 角色多 Agent 开发系统。用户的自然语言需求由主控（前台接待）接收，经三级分流（自己干 / 派一人 / 组团），通过预设工作组（pipeline）按序执行，成果返回对话区和右侧面板。

**运行环境**：AMD Radeon PRO W7900 / 48GB VRAM / Qwen2.5-14B / llama.cpp + ROCm  
**云端**：`u-3004-abffcef6`，公网 `https://rc-53833487fc7b93ab.radeon.firstdg.ai`  
**仓库**：`/workspace/template-repos/template-2603/repo`

---

## 二、本次改动清单（按模块）

### 调度系统（master.py）— 最核心
| 改动 | 说明 |
|------|------|
| **三级分流** | Level1(自己干)→Level2(派一人)→Level3(组团)，替代旧关键词匹配 |
| **Plan-First** | 模糊需求先展示计划再执行，明确需求(≥15字)直接开干 |
| **角色边界** | 9 个干活角色加 `[交还前台]` 退回机制 |
| **诚实规则** | 主控不编造假角色（weather/file_manager），不知实时天气 |
| **上下文精简** | Master L0 从 20 条砍到 6 条（3 轮） |
| **工具降级** | llama.cpp JSON 500 错误时自动降级纯文本 |

### 角色 Prompt（prompt.slim.txt）
| 角色 | 改动 |
|------|------|
| **coach** | 删"问问题=犯罪"，加模式感知（流水线中不追问） |
| **designer** | 加 60-30-10 法则；流水线中缺技术栈用默认值 |
| **全部 9 角色** | 加角色边界 + 工具声明 |

### 前端（ChatView.vue）
| 改动 | 说明 |
|------|------|
| **流式折叠** | `{{buf}}` → `v-html`，`<details>` 在传输中即折叠 |
| **文件夹 Tab** | 预览面板新 Tab，显示 `data/outputs/` 真实文件 |
| **展开按钮** | 侧边栏折叠后紫色固定按钮可展开 |
| **HTML 占位** | 生成 HTML 时对话区用占位符替代 |
| **选项按钮** | 反问改为可点击选项（用途/风格/功能） |
| **自动聚焦** | 发消息后焦点回到输入框 |

### 后端（base.py / role_base.py）
| 改动 | 说明 |
|------|------|
| **产物自动落盘** | 回复中的 Markdown/代码块自动写 `data/outputs/` |
| **路径提取** | "已保存到 X" → 真写 X，当前回复无内容时翻历史找 |
| **工具降级** | LLM 500 错误时重试不带工具 |

### 配置
| 文件 | 改动 |
|------|------|
| `dev_full.json` | trigger 去"网页/帮我写"；developer 指定 `frontend/src/components/`；去 experience_evaluator |
| `translation_task.json` | trigger 去"翻译"，只保留"翻译文档"等长任务 |
| `role_pool.json` | master 加 `file_read/write/list` |
| `start.sh` | 加前端自动构建 |

---

## 三、当前已知问题

| # | 问题 | 严重度 | 原因 |
|---|------|:--:|------|
| 1 | 流水线 developer 有时写文件目录不对 | 🟡 | LLM 未严格遵循路径指令 |
| 2 | 右侧面板流水线在 `stream_meta` 后首次渲染时可能不更新 | 🟡 | 前端 pipelineSteps 更新时机 |
| 3 | llama.cpp 工具调用 JSON 偶尔 500 | 🟡 | 14B 模型 JSON 生成质量 |
| 4 | 每个角色 20-40s，7 步流水线总耗时 3-5 分钟 | 🟢 | 14B + AMD GPU，正常 |
| 5 | `data/outputs/` 文件列表刷新有延迟 | 🟢 | setTimeout 500ms 不够 |
| 6 | 前端构建时间长（30-60s） | 🟢 | npm run build 在 AMD 云上慢 |

---

## 四、云端操作速查

```bash
# 拉代码 + 重启
cd /workspace/template-repos/template-2603/repo && git pull && bash start.sh

# 看后端日志
tail -50 /tmp/backend.log

# 看 LLM 日志
tail -20 /tmp/llama.log

# 停止
bash stop.sh

# 查看产物文件
ls -la data/outputs/

# 跑冒烟测试
bash tests/demo_smoke_test.sh
```

---

## 五、演示流程（建议）

1. **B3 记忆**："我叫张三" → "我是谁"（确认记住）
2. **通用问答**："ROCm 是什么"（走 Level1 自己干）
3. **简单翻译**："翻译为英文：AMD GPU 适合 AI 推理"（走 Level2 派一人）
4. **开发流水线**："开发一个简单的 React 计算器，支持加减乘除"（走 Level3 直接执行）
5. **文件产物**：等流水线跑完 → 右侧面板→文件 Tab → 看到生成的文件
6. **模糊需求**："写个网页" → 弹出选项按钮 → 点击选择

---

## 六、如果要继续改

| 优先级 | 方向 |
|:--:|------|
| P0 | 录演示视频（按 docs/演示解说词.md） |
| P0 | 跑 S7 A/B 测速（source bench_helpers.sh → benchmark_orig → bench_one → benchmark_slim） |
| P1 | 解决 developer 写文件目录问题 |
| P1 | 修右侧面板流水线不更新 |
| P2 | 工具调用 JSON 质量——考虑 token healing 或换模型 |
| P2 | 独立前台接待角色（拆出 master 的接待逻辑） |
