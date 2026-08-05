# MyAgent 后端调用链路完整分析

> 分析日期: 2026-08-05 22:45  
> 分析范围: 角色调度链、工具调用、多任务执行、回复模式

---

## 一、总体架构概览

```
用户 → WebSocket (/api/agents/{id}/ws)
  → BaseAgent.chat_stream()
    → MasterRole.dispatch_stream()          # 前台接待 + 调度中心
      ├─ 简单问候 → 直接回复
      ├─ 匹配工作组 → _execute_pipeline()   # 10个预设工作组
      ├─ 关键词匹配 → _dispatch_to_roles()  # 按GPU分组并行
      └─ 兜底 → _handle_general()           # 主控自己LLM处理
        → RoleBase.execute()
          → _assemble_context()            # L0+L1+L2+L3+黑板
          → _call_llm()                    # 带工具调用循环
            → LLMGateway.chat()
              → llama.cpp (本地 GGUF 模型)
```

**结论：调用链路完整，从入口到LLM推理的每个环节都有实现。**

---

## 二、角色调度链分析

### 2.1 18角色定义 (`role_pool.json`)

| 分组 | 角色 | GPU | 工具权限 |
|------|------|-----|---------|
| 通用 | master, knowledge_retriever, writer, quality_checker, scheduler, creative, translator, visual_analyzer, experience_evaluator | gpu0/gpu1/gpu2 | mostly 无 |
| 开发 | coach, designer, developer, inspector, tester, deployer, handoff_receiver | gpu0/gpu2 | developer有4工具 |
| 后勤 | cleaner | gpu2 | 无 |
| 管理 | hr_manager | gpu2 | 无 |

### 2.2 10个预设工作组

| 工作组 | 用途 | 流水线 |
|--------|------|--------|
| dev_full | 完整开发 | coach→designer→developer→inspector→tester→deployer→cleaner (+experience_evaluator) |
| dev_design_only | 仅设计 | coach→designer |
| dev_code_review | 代码审查 | inspector→cleaner |
| dev_modification | 修改迭代 | handoff_receiver→developer→inspector→tester |
| dev_tech_debt | 技术债 | handoff_receiver→inspector→developer→cleaner |
| report_writing | 报告写作 | writer→quality_checker |
| research_investigation | 调研 | knowledge_retriever→writer |
| schedule_planning | 日程规划 | scheduler |
| translation_task | 翻译 | translator→quality_checker |
| visual_analysis_task | 视觉分析 | visual_analyzer |

### 2.3 ✅ 调度链正常工作的部分

1. **入口路由正确**: WebSocket/HTTP → BaseAgent → MasterRole → RoleBase → LLM
2. **工作组匹配**: `trigger_keywords` 精确匹配，支持多关键词打分
3. **关键词回退**: 50+关键词映射到能力→角色，开发类自动加coach+质量门禁
4. **跨GPU并行**: `_dispatch_to_roles` 按GPU亲和性分组 → `asyncio.gather` 并行
5. **超时/重试/降级**: 120s超时 + 1次重试 + 失败降级提示
6. **防火墙**: `_build_task_packet` / `_build_pipeline_task` 实现最小信息原则
7. **记忆系统**: L0(WM)→L1/L2(SM)→L3(KB) 四级分层，上下文按需组装

---

## 三、🔴 关键缺陷与风险

### 3.1 工具调用能力严重受限

| 问题 | 严重度 | 详细说明 |
|------|:---:|------|
| **仅developer有真实工具** | 🔴 高 | 18个角色中，只有 developer 的4个工具（file_read/write/list/code×exec）真正可用 |
| **web_search是占位** | 🔴 高 | knowledge_retriever 唯一工具 web_search 恒定返回"未启用"，无法联网搜索 |
| **cleaner无工具** | 🟡 中 | 清洁员只能"建议"清理，不能实际操作文件系统 |
| **writer无工具** | 🟡 中 | 写作角色只能产文本，无法调用任何格式转换或导出工具 |
| **scheduler无工具** | 🟡 中 | 日程角色无法创建提醒/日历项 |
| **deployer无工具** | 🟡 中 | 部署角色无法执行构建/部署命令 |

### 3.2 流式模式不支持工具调用

🔴 **这是最严重的功能缺口。**

```python
# role_base.py: _call_llm_stream() 直接调用 gateway.chat_stream()
# 完全跳过了 _call_llm() 中的工具调用循环 (_run_tool_loop)
# 意味着：WebSocket 流式对话时，模型请求的工具调用会被静默忽略
```

**影响**：
- WebSocket 聊天中 developer 角色的 `file_write`/`file_read` 等工具完全失效
- `dev_full` 工作组的 developer 步骤（step 3）在流式模式下无法产出代码文件
- 用户在前端 ChatView 中看到的回复不包含工具执行结果

### 3.3 流水线并行未实现

```python
# master.py: _execute_pipeline() 逐步骤串行执行
# pipeline 定义中的 parallel_with 字段虽然存在，但代码中未检查
# _should_revise() 恒定返回 False，返工机制形同虚设
```

**影响**：
- `dev_full` 的 inspector + tester 步骤本可并行，实际串行
- 单次 dev_full 执行时间 = 所有步骤耗时之和

### 3.4 角色提示词定位与实际能力不匹配

| 角色 | prompt声称 | 实际能力 |
|------|-----------|---------|
| knowledge_retriever | "联网搜索、多源搜索" | web_search工具恒返回"未启用" |
| writer | "多格式输出转换" | 无任何格式转换工具，纯LLM文本 |
| scheduler | "时间管理/提醒" | 无提醒机制 |
| cleaner | "安全清理、文件系统管家" | 无文件操作工具 |
| visual_analyzer | "图片分析/截图审查" | 单卡模式无多模态模型 |

---

## 四、具体任务场景分析

### 4.1 "整理文件"
- **调度路径**: 关键词"清理/整理" → 匹配 cleaner 角色
- **实际效果**: cleaner 只有 prompt 能力，没有工具。能给出清理建议，但不能实际操作文件
- **评级**: 🟡 可输出文本建议，无法执行

### 4.2 "代发邮件"  
- **调度路径**: 关键词"邮件" → 匹配 writer 角色
- **实际效果**: writer 能起草邮件文本，但**没有SMTP发送工具**。系统没有任何邮件发送能力
- **评级**: 🔴 无法完成，缺关键能力

### 4.3 "智能助手"（通用对话）
- **调度路径**: 走 master._handle_general() 直接用LLM
- **实际效果**: 取决于模型质量。当前14B Q4_K_M量化模型在复杂推理场景下效果不佳
- **评级**: 🟡 基础对话可用，智能程度受限于模型

### 4.4 "dev_full 开发流水线"
- **调度路径**: 匹配 dev_full 工作组 → 7步串行流水线
- **实际效果**: 
  - 非流式模式：全部7步可执行，developer能调用工具写文件
  - 流式模式：**developer无法调用工具**，步骤3无法产出代码文件
- **评级**: 🟡 非流式可用，流式模式下 developer 步骤断裂

---

## 五、回复模式分析

### 5.1 HTTP 非流式 (`POST /api/agents/{id}/chat`)
| 项目 | 状态 |
|------|:--:|
| 基础对话 | ✅ |
| 工作组匹配 | ✅ |
| 角色调度 | ✅ |
| 工具调用 | ✅ (developer 4工具可用) |
| 超时处理 | ✅ |
| 记忆保存 | ✅ |
| 调度元数据返回 | ✅ (type/workgroup/roles_used) |

### 5.2 WebSocket 流式 (`/api/agents/{id}/ws`)
| 项目 | 状态 |
|------|:--:|
| 基础流式对话 | ✅ |
| 工作组匹配 | ✅ |
| 角色调度进度提示 | ✅ ("[匹配到工作组...]") |
| 工具调用 | 🔴 **不支持** |
| stream_meta 元数据 | ✅ (type/workgroup/roles_used) |
| 连接管理 | ✅ (自动清理断连) |
| 对话记忆 | ✅ (每轮save_memory) |

---

## 六、系统整体评分

| 维度 | 评分 | 说明 |
|------|:--:|------|
| 调用链路完整性 | 🟢 8/10 | 入口→调度→执行→LLM→返回，链路完整 |
| 工具调用能力 | 🔴 3/10 | 18角色仅1个有真实工具，流式不支持工具 |
| 多任务并行 | 🟡 5/10 | 跨GPU并行可用，流水线无并行 |
| 回复模式 | 🟡 6/10 | 非流式完整，流式缺工具支持 |
| 通用Agent能力 | 🟡 4/10 | 对话可用，文件操作仅有developer，无邮件/搜索/提醒 |
| 容错机制 | 🟢 7/10 | 超时/重试/降级/JSDON容错/工具异常捕获 |

**总分: 5.5/10** — 调度架构设计良好，但工具和执行层存在关键短板

---

## 七、优先级修复建议

| 优先级 | 问题 | 修复方向 |
|:--:|------|------|
| 🔴 P0 | **流式模式不支持工具调用** | 在 `_call_llm_stream` 中实现简化版工具循环，或在 master 层对 developer 步骤用非流式执行 |
| 🔴 P0 | **web_search 是占位** | 接入本地 DuckDuckGo/Brave Search API，或至少实现基于本地 knowledge_base 的检索 |
| 🟡 P1 | **cleaner/deployer 无工具** | 为 cleaner 授予 file_list/delete 工具；为 deployer 授予 code_exec 工具 |
| 🟡 P1 | **流水线无并行** | 实现 `parallel_with` 字段逻辑，让 inspector+tester 可并行 |
| 🟡 P2 | **writer 无格式转换** | 添加 markdown→html/pdf 转换工具 |
| 🟡 P2 | **无邮件发送** | 添加 SMTP 工具或 API 集成 |

---

## 八、参赛截止前最紧迫要做的事

当前瓶颈不是"调用链路是否完整"，而是：
1. **模型质量**（14B Q4_K_M → 30B）—— 直接影响所有角色输出质量
2. **流式+工具断裂**—— 如果演示走 WebSocket（前端默认），dev_full 将无法产出代码
3. **演示时建议直接走 dev_full 非流式** 或临时在 master 层对 developer 步骤绕过流式
