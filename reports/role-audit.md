# 角色体系 & 调用链路审计报告

> 审计时间：2026-08-06 | 覆盖范围：19 角色提示词 + 10 工作组 + 主控调度引擎

---

## 一、总体评估：✅ 闭环

核心流水线 `dev_full`（完整开发 7 步）**可以形成闭环**：

```
用户请求 → Master 匹配工作组 → [Coach → Designer → Developer → Inspector → Tester → Deployer → Cleaner]
                                    ↑                                            │
                                    └────────────── 不通过 → 返工重检 ──────────┘
```

每个角色有完整的提示词、工具权限、输出格式规范，步骤间有输入/输出管道连接。

---

## 二、逐角色分析

### 🟢 提示词质量：优秀

| 角色 | 字数 | 提示词质量 | 关键能力 |
|------|:---:|:---:|------|
| **Master** | 9.6KB | ⭐⭐⭐⭐⭐ | 任务分类+工作组匹配+信息防火墙+任务包模板+异常处理 |
| **Coach** | 16.8KB | ⭐⭐⭐⭐⭐ | Phase 0-3 分阶段注意力+竞品调研+教学+PROJECT_STATUS 维护 |
| **Designer** | 9.7KB | ⭐⭐⭐⭐ | 技术栈感知+多页面+响应式+设计Token |
| **Developer** | 8.9KB | ⭐⭐⭐⭐ | 7项自检+文件读写+代码规范 |
| **Inspector** | 10.0KB | ⭐⭐⭐⭐⭐ | 8维审查+反幻觉铁律+技术债识别+返工判定 |
| **Tester** | 10.2KB | ⭐⭐⭐⭐ | 7步门禁+反幻觉铁律+诚实标注 |
| **Deployer** | 8.4KB | ⭐⭐⭐⭐ | 8步管道+健康检查+回滚方案 |
| **Cleaner** | 8.6KB | ⭐⭐⭐⭐ | 临时文件+构建缓存+dead code |

### 🟡 边缘角色

| 角色 | 提示词 | 状态 | 备注 |
|------|:---:|:---:|------|
| Translator | 有 | 🔵 单步 | 直接翻译，无依赖 |
| Writer | 有 | 🔵 含质检 | Writer → Quality Checker |
| Knowledge Retriever | 有 | 🔵 调研 | 接入 web_search 工具 |
| Scheduler/Creative | 有 | 🔵 独立 | 无流水线依赖 |
| Visual Analyzer | 有 | 🟡 降级 | 单GPU部署时降级为文本角色 |
| HR Manager | 有 | 🔵 管理 | 角色审计/提示词优化 |
| Handoff Receiver | 有 | 🔵 接手 | 存量项目修改入口 |
| Experience Evaluator | 有 | 🔵 收尾 | 经验注入 |

---

## 三、流水线闭环质量

### ✅ 已确认的闭环点

1. **关键词匹配**：Master 有 18 个触发关键词（开发/做项目/写应用/建网站…），足够覆盖用户输入
2. **任务包构造**：Master 按 4 字段模板（指令/输入/标准/输出）裁剪下发
3. **返工机制**：Inspector/Tester 输出含"不通过"→ Master 检测到 → 跳回 Developer → 最多 3 次
4. **防幻觉约束**：Inspector + Tester 在提示词第 0 部分就有"禁止编造"铁律
5. **Coach 自限流**：Coach 只做 Phase 0，不自推进后续阶段
6. **技术债追踪**：Inspector 识别 → tech_debt.md → Coach 维护 PROJECT_STATUS → 标注偿还
7. **并行执行**：支持 `parallel_with` 字段（如 Designer 并行派样图时用）
8. **超时保护**：每个角色 120s 超时，自动重试 1 次

### 🟡 潜在断裂点

| 风险 | 描述 | 建议 |
|------|------|------|
| **Inspector/Tester 无执行工具** | 提示词写明 tools 为空，实际审查全靠"读文件+文本分析" | 体验上降级但可接受；LLM 本身能从代码文本中判断大部分问题 |
| **Inspector 反馈传递链** | Inspector 写报告 → Master 需解析"不通过"关键词 → 构造返工任务包 | 当前靠文本匹配，可能漏判；建议统一用 `结论：不通过` 格式标记 |
| **Developer 重检承接** | Developer 重做时能否真正理解"从哪里改、改到什么程度"？ | 目前靠 Master 将 Inspector 报告原文转发；Inspector 报告中已有文件+行号定位 |
| **Deployer 依赖检测** | 如果前端没构建工具怎么办？ | Deployer 提示词中有"先确认构建工具是否存在"的铁律 |

---

## 四、工具权限分布

```
完整开发流水线 7 步的工具覆盖：

Coach:              [无工具] ← 只分析需求
Designer:           file_write, file_read, file_list
Developer:          code_exec, file_read, file_write, file_list  ← 最全
Inspector:          file_read, file_list
Tester:             file_read, file_list
Deployer:           code_exec, file_read, file_list
Cleaner:            file_read, file_write, file_list

✅ 文件读写串联覆盖完整
⚠  Inspector 不能直接调用 code_exec — 但 LLM 可从文本审查代码
```

---

## 五、结论

**整体闭环质量：良好（7.5/10）**

- 提示词覆盖度高、角色边界清晰、流水线有返工机制
- 最大的技术债是 Inspector/Tester 无法真正跑工具（tsc/eslint/vitest）— 属于环境限制
- 建议改进点：统一返工标记格式 + 增加跨步骤状态 API

**可以跑通，可以演示。**
