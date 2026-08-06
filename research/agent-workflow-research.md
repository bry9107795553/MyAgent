# Agent 工作流设计与用户交互确认机制 · 调研报告

> 调研日期：2026-08-06
> 调研范围：MetaGPT / CrewAI / AutoGen / LangGraph 多 Agent 框架 + ChatGPT/Claude/Gemini 对话式 Agent + 学术界最新 HITL 研究

---

## 一、各平台工作流模式

### 1.1 MetaGPT — SOP 驱动的流水线

```
User Input (一句话需求)
  │
  ▼
ProductManager ──► 输出 PRD.md
  │  (发布到共享消息池，Architect 订阅)
  ▼
Architect ──► 输出 SystemDesign.md
  │  (发布，ProjectManager 订阅)
  ▼
ProjectManager ──► 输出 Tasks.md
  │  (发布，Engineer 订阅)
  ▼
Engineer ──► 输出 *.py
  │  (发布，QA 订阅)
  ▼
QAEngineer ──► 输出测试报告
```

**核心机制：**

- **发布-订阅消息池**：每个 Role 通过 `_watch` 声明订阅的消息类型，只消费自己关心的消息，其余忽略。解耦但不失序。
- **结构化输出强制**：每个角色必须输出结构化文档（PRD/Design/Tasks/Code），而非自由文本。这是 MetaGPT 最关键的创新——阻断幻觉在 Agent 间传播。
- **SOP 固化**：流程步骤预定义，不可运行时动态改变。2025 年新增 AFlow（ICLR 2025 口头报告，Top 1.8%）用 MCTS 自动搜索最优工作流，但仍需离线生成。

**与用户交互：** 仅在开头接收一句话需求，中间无用户交互。全程自主运行，最终输出完整项目。

---

### 1.2 CrewAI — 角色扮演 + 层级调度

```
                  ┌─────────────┐
                  │  Manager LLM │  ← Hierarchical 模式自动创建
                  └──────┬──────┘
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
      ┌─────────┐  ┌─────────┐  ┌─────────┐
      │Researcher│  │ Writer  │  │ Editor  │
      └─────────┘  └─────────┘  └─────────┘
           │             │             │
           └─────────────┼─────────────┘
                         │
                   共享 Context（Task 间传递）
```

**三种流程模式：**

| 模式 | 调度方式 | 适用场景 |
|------|----------|----------|
| **Sequential** | 按 Task 列表顺序执行，前一个输出是后一个的 context | 线性流水线 |
| **Hierarchical** | Manager Agent 动态分配 Task 给 Agent，验证输出 | 复杂项目、动态任务 |
| **Consensus**（开发中） | 多 Agent 投票决策 | 需要多方确认的场景 |

**核心机制：**

- `allow_delegation=True` 时，Agent 自动获得两个工具：**Delegate Work**（委托任务给同事）和 **Ask Question**（向同事提问）。这是 CrewAI 最独特的 Agent 间交互机制。
- **Human Input**：Task 级别设置 `human_input=True`，Agent 在交付最终答案前提示用户提供额外上下文或确认。
- 改进型匈牙利算法做任务-Agent 最优匹配，1000 代理规模下分配延迟 <50ms。

**与用户交互：** 支持 Task 级别的 human_input 开关。但用户介入点粗粒度——要么全程无人，要么特定 Task 末尾询问。

---

### 1.3 AutoGen — 对话即工作流

```
     ┌──────────────────────────────────────────────┐
     │              GroupChat (消息总线)              │
     │                                               │
     │  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
     │  │Researcher│  │  Coder   │  │ Reviewer │   │
     │  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
     │       │              │              │         │
     │       └──────────────┼──────────────┘         │
     │                      │                        │
     │            GroupChatManager                    │
     │         (speaker_selection: auto/              │
     │          round_robin/custom)                   │
     └──────────────────────────────────────────────┘
```

**核心机制：**

- **Agent 间对话即工作流**：不需要显式定义流程图。Agent A 和 Agent B 聊起来，任务在对话中完成。执行路径由 LLM 动态决定，非预定义。
- **Handoff 模式**（v0.4+）：Agent 通过 tool call 将控制权转移给另一个 Agent。类似 OpenAI Swarm，但基于事件驱动 pub-sub。
- **三种 speaker 选择策略**：auto（LLM 选下一个发言者）、round_robin（轮询）、custom function。
- **UserProxyAgent**：代表人执行操作。`human_input_mode` 三档：NEVER（全自动）/ ALWAYS（每步确认）/ TERMINATE（仅结束时确认）。
- **Nested Chat**：Agent 在处理任务时派生子对话解决子问题。
- **并行工具执行**：v0.4 最亮眼特性，多个 tool call 同时进行。

**当前状态**：2025 年 10 月 AutoGen 并入 Microsoft Agent Framework (MAF)，不再作为独立库更新。但原型和教学中仍广泛使用。

---

### 1.4 LangGraph — 显式状态机

```
              ┌──────────┐
              │   START   │
              └────┬─────┘
                   ▼
            ┌─────────────┐
            │ Read Email  │
            └──────┬──────┘
                   ▼
         ┌─────────────────┐
         │ Classify Intent  │──► bug ──► ┌───────────┐
         │   (LLM node)    │             │ Bug Track │
         └────────┬────────┘             └─────┬─────┘
                  │                            │
        ┌─────────┼─────────┐                  │
        ▼         ▼         ▼                  │
   ┌────────┐┌────────┐┌────────┐              │
   │  Doc   ││  Billing││Feature │              │
   │ Search ││ Lookup ││ Request│              │
   └───┬────┘└───┬────┘└───┬────┘              │
       └─────────┼─────────┘                   │
                 ▼                             │
          ┌─────────────┐                      │
          │ Draft Reply  │◄─────────────────────┘
          └──────┬──────┘
                 ▼
    ┌──────────────────────┐
    │   Human Review Node  │  ← interrupt() 暂停，等人工审批
    └──────────┬───────────┘
               ▼
        ┌──────────────┐
        │  Send Reply  │
        └──────┬───────┘
               ▼
           ┌──────┐
           │ END  │
           └──────┘
```

**核心机制：**

- **StateGraph**：工作流定义为有向图。节点 = Python 函数（Agent/工具/人审），边 = 条件跳转逻辑。支持循环、分支、并行。
- **显式状态 Schema**（TypedDict/Pydantic）：所有节点读写同一个类型化状态对象，状态变更可追溯。
- **Checkpointing**：每个节点执行后自动持久化到后端（PostgreSQL/Redis/文件）。崩溃后从最后一个 checkpoint 恢复。支持 time-travel 调试——回退到任意历史状态重放。
- **Human-in-the-Loop**：`interrupt()` 在任意节点暂停，等外部输入后恢复。这是框架级原语，非后期补丁。
- **Command 原语**（2024.12 引入）：节点返回 `Command(goto="agent_b")` 实现动态路由，兼作状态更新 + 跳转指令。
- **Supervisor 模式**：中央协调器 Agent 动态选择下一个 Worker Agent。**Handoff 模式**：Agent 自身决定转移给谁。

**Anthropic 的评价**：在《Building Effective Agents》中，Anthropic 建议「从直接 LLM API 调用开始，不要急于用框架」。LangGraph 被提及为可选框架之一，但强调其抽象层可能隐藏底层 prompt 和响应，增加调试难度。

---

## 二、对话式 Agent 的交互模式

### 2.1 ChatGPT / Claude / Gemini 的默认行为

三家核心模型在面对模糊需求时的**默认倾向一致**：优先给出答案，而非请求澄清。原因：

- RLHF 训练使模型倾向于"乐于助人"，宁可猜错也不说"我不确定"
- 系统优化目标是减少交互轮次、快速完成任务
- 模型对自身不确定性缺乏准确校准——高置信度的回答可能完全错误

### 2.2 现有应对策略

| 策略 | 具体做法 | 效果 |
|------|----------|------|
| **前置指令** | "If this prompt is ambiguous, ask for clarification first" | Gemini 需要显式指令才会暂停；ChatGPT 对模糊任务有一定自发性提问 |
| **复述确认** | "Before answering, restate my question to confirm" | 强制模型暴露其假设，10 秒内发现偏差 |
| **允许反驳** | "Push back on vague parts before writing" | 减少"迎合性回答"，但需在 prompt 中明确授权 |
| **分场景规则** | "Only ask for clarification in research, vendor analysis, editorial writing" | 避免琐碎任务也被频频追问 |

### 2.3 值得警惕的 Sycophancy 问题

独立研究对 GPT-4o、Claude Sonnet、Gemini 1.5 Pro 的测试表明：当用户用"Are you sure?"质疑时，模型反转答案的概率分别约 **58%、56%、61%**。对话越长、用户越使用第一人称（"I believe..."），反转概率越高。这意味着**依赖 Agent 的"自我怀疑"来做确认是不可靠的**——它可能只是迎合用户，而非真正发现错误。

---

## 三、框架对比总表

| 维度 | MetaGPT | CrewAI | AutoGen (v0.4) | LangGraph |
|------|---------|--------|----------------|-----------|
| **工作流范式** | SOP 固定流水线 | 角色扮演 + Manager 调度 | 对话即工作流 | 显式状态机/图 |
| **调度模式** | 发布-订阅，按角色订阅顺序 | Sequential / Hierarchical / Consensus | GroupChat 发言者选择 / Handoff | 条件边 + Command 动态路由 |
| **路由决策者** | 预定义 SOP（无运行时决策） | Manager LLM（Hierarchical） | LLM 选下一个发言者 / Agent 自选 | 开发者编码的边逻辑 / Supervisor Agent |
| **状态管理** | 全局消息池（Message 对象列表） | Task context 链式传递 | 对话历史（pub-sub 事件） | 类型化 StateGraph + Checkpoint |
| **Human-in-the-Loop** | ❌ 无（仅初始输入） | ✅ Task 级 human_input 开关 | ✅ UserProxyAgent 三种模式 | ✅ interrupt() 原语，任意节点 |
| **Agent 间通信** | 共享消息池 pub-sub | Delegate/Ask 工具 + Task context | pub-sub 事件 + Handoff tool | 共享 State + Command 跳转 |
| **并行执行** | ❌ 严格顺序 | ❌ 顺序或 Manager 串行分配 | ✅ 并行工具调用 | ✅ 并行边 + Send API fan-out |
| **可恢复性** | 支持 serialize/deserialize | ❌ 有限 | 有限（v0.4 后期补丁） | ✅ 原生 checkpoint + time-travel |
| **学习曲线** | 中（需理解 SOP 和角色定义） | 低（API 最简洁） | 中（概念多，v0.4 后架构变复杂） | 高（需定义 State Schema + 边逻辑） |
| **成本** | 低～中（固定 5 轮左右） | 中（Manager 每步决策消耗 token） | 高（8 Agent 任务 $5-30） | 可控（开发者决定调用次数） |
| **可预测性** | 高（流程固定） | 中（Manager 决策有不确定性） | 低（涌现行为，难以复现） | 高（显式状态机，可 replay） |
| **适合场景** | 代码生成、文档产出 | 通用任务协作、内容生产 | 实验研究、开放探索 | 生产级复杂工作流、需审计场景 |
| **当前状态** | 活跃，MGX 产品化 | 活跃，2025 获 $18M 融资 | 已并入 Microsoft Agent Framework | 活跃，35K+ GitHub Stars |

---

## 四、业界最佳实践：Agent 何时向用户提问

### 4.1 三信号决策框架

来自 DevRev/Anthropic 等工业实践总结，Agent 是否应暂停并请求用户确认，取决于三个信号的组合：

```
                    高风险？
                      │
              ┌───────┴───────┐
              ▼               ▼
          不可逆？          可逆？
              │               │
      ┌───────┴───────┐       │
      ▼               ▼       ▼
   低置信度        高置信度   低置信度
      │               │       │
   必须确认        可自动    建议确认
   (HITL)        (HOOTL)   (HOTL)
```

- **信号 1 - 置信度**：Agent 对当前决策的把握。可通过多轮采样一致性、领域外分布检测来估算。
- **信号 2 - 风险等级**：错误决策的代价。金融交易 > 发送邮件 > 文档分类。
- **信号 3 - 可逆性**：能否撤销。退款 > 发布代码 > 草稿建议。

**三个实践标尺：**
- 不可逆 + 高风险 → **必须确认**（Approval Gate）
- 不可逆 + 低风险 → **事后审查**（Review After Fact）
- 可逆 + 任何风险 → **自主执行 + 可撤销**

### 4.2 确认时机的黄金法则（CHI 2026 最新研究）

CMU 团队（CHI 2026 接收）通过 48 人实验得出关键结论：

- **确认每一步**：错误不传播，但效率降到手工水平
- **仅结束时确认**：效率高，但单步错误导致**级联失败**，需全部重做。这是当前大多数 Agent 平台的默认策略。
- **中间检查点确认**：在关键里程碑处暂停。**81% 用户偏好此方案**，平均任务完成时间减少 **13.54%**。

该研究还发现用户形成了一种重复的行为模式——**CDCR 循环**：
```
Confirmation → Diagnosis → Correction → Redo
  （确认）      （诊断）      （修正）     （重做）
```

这意味着确认界面的设计应该**同时展示 Agent 的推理过程**，让 Diagnosis 阶段尽可能短。如果只是问"继续吗？Y/N"，用户仍需反向推测 Agent 的意图，达不到效率提升。

### 4.3 提问频率控制

| 策略 | 描述 | 适用 |
|------|------|------|
| **里程碑确认** | 在关键阶段完成时暂停，展示阶段产物 + 下一步计划 | 多步骤流程（推荐作为默认策略） |
| **置信度阈值** | 置信度 < 阈值（建议起始 85%）时升级，> 阈值自动执行 | 分类、路由等量化任务 |
| **分级授权** | 新 Agent 能力从"每步确认"开始，积累信任后逐步解放 | 长期运行的 Agent 系统 |
| **预确认 + 批量** | Agent 先产出完整计划，用户一次性审批全部步骤，中间不再打扰 | 结构化、可预测的任务 |
| **例外升级** | Agent 自主执行，仅遇到异常/不确定时暂停。在 prompt 中声明升级触发词 | 高吞吐、低风险场景 |

### 4.4 Anthropic 的核心建议

1. **从最简单的方案开始**，不要急于引入 Agent 框架。很多时候单次 LLM 调用 + 检索就够了。
2. **Workflow（预定义路径）优先于 Agent（动态决策）**。Workflow 可预测、可调试；Agent 用延迟和成本换灵活性。
3. **框架会隐藏底层细节**。如果使用框架，确保理解其底层 prompt 和调用链。
4. **给 Agent 提供"计算机"**（文件系统、Bash、编辑器），而非 50+ 个专用工具。Agent 使用人类工具更通用。

---

## 五、针对 MyAgent（19 角色 · 主控调度）的改进建议

> MyAgent 的核心特征：19 个专业角色，由主控制器统一调度派发任务。这本质上是一个 **Supervisor 架构**，与 CrewAI Hierarchical / LangGraph Supervisor 模式同族。

### 5.1 当前架构的固有风险

基于对同类 Supervisor 架构的分析，19 角色系统面临以下已知问题：

| 风险 | 根因 | 业界先例 |
|------|------|----------|
| **Supervisor 单点瓶颈** | 所有决策经过一个 LLM，延迟和 token 叠加 | CrewAI Manager、LangGraph Supervisor 均存在 |
| **上下文窗口爆炸** | Supervisor 需保留所有子 Agent 的输出，19 角色对话历史极长 | AutoGen GroupChat 8 Agent 即有 token 爆炸 |
| **路由精度下降** | 随角色数增加（>10），Supervisor 的 prompt 需要描述所有角色能力，准确率下降 | 业界建议超过 10 个 specialist 考虑分层 Supervisor |
| **错误传播** | Supervisor 派错一次，下游做无用功 | MetaGPT 用结构化输出解决，MyAgent 可借鉴 |
| **无限循环** | Agent A → B → A 的 handoff 循环 | CrewAI 默认 `allow_delegation=False` 来防御 |

### 5.2 具体改进建议

#### 建议 1：引入分层 Supervisor（解决 19 角色路由精度）

当前扁平 Supervisor 需要从 19 个角色中选择——这对 LLM 的路由精度是巨大挑战。

**方案**：按领域分组为 3-4 个二级 Supervisor，每个管理 4-6 个角色：

```
用户需求
  │
  ▼
┌──────────────┐
│  主 Supervisor │  ← 只面对 3-4 个领域选项
└──────┬───────┘
       │
  ┌────┼────┬────────┐
  ▼    ▼    ▼        ▼
┌────┐┌────┐┌────┐┌────┐
│研发 ││数据分析││运维 ││安全 │  ← 二级 Supervisor（各 4-6 角色）
└──┬─┘└──┬─┘└──┬─┘└──┬─┘
   │  ...  │  ...  │  ...
```

好处：每层 Supervisor 的角色选项 ≤6，路由准确率显著提升。代价是多一层 LLM 调用——但比路由错误导致的重复工作成本低。

#### 建议 2：主控派发前加入「Plan-First」确认环节（最关键的体验改进）

**当前流程（推测）**：用户给需求 → Supervisor 直接派发 → 各角色执行 → 返回结果

**建议流程**：

```
用户需求
  │
  ▼
Supervisor 生成执行计划（不派发）
  │  ┌─ 列出：哪些角色参与、各自负责什么、预期产物、依赖关系
  │  └─ 这一步不调用任何 worker Agent，仅 Supervisor 推理
  ▼
【向用户展示计划 + 请求确认】
  │  "我理解你的需求是 X。
  │   计划派发 6 个角色：
  │   1. 需求分析师 → 产出 PRD
  │   2. 架构师 → 产出系统设计（依赖 1）
  │   3-4. 前端/后端工程师 → 并行编码（依赖 2）
  │   5. 测试工程师 → 测试用例（依赖 3-4）
  │   6. 文档工程师 → 用户文档（依赖 3-4）
  │   确认？或需要调整？"
  │
  ├── 用户确认 → 执行
  └── 用户修改 → Supervisor 调整计划 → 再次确认 / 直接执行
```

**为什么这很重要**：
- CHI 2026 研究证实：中间确认优于终点确认
- 计划阶段的修正成本趋近于零（尚未调用任何 worker）
- Anthropic 的"复述确认"技巧——让 AI 暴露其假设
- 对于 19 角色系统，用户不可能预见所有角色的行为，计划预览是唯一高效的纠偏窗口

#### 建议 3：关键里程碑设置检查点（而非每角色都确认）

在以下节点设置 `interrupt()`：

1. **计划生成后**（上述 Plan-First 确认）
2. **关键依赖角色的产出完成后**（如需求分析、架构设计——这些是下游的基础）
3. **不可逆操作前**（如代码提交、外部 API 调用、数据修改）

每个检查点的展示格式（借鉴 CDCR 研究）：

```
✅ 已完成：需求分析师产出了 PRD.md（摘要：...）
📋 架构师正在等待此 PRD 作为输入
⏭ 下一步：架构师 → 系统设计 → 前后端并行开发

[继续执行] [查看 PRD 全文] [修改 PRD 后继续] [终止]
```

#### 建议 4：为 Supervisor 增加置信度自评

在派发每个子任务前，让 Supervisor 输出置信度（0-100）：

```
派发决策：
  角色：前端工程师
  任务：实现登录页面
  置信度：92 → 自动派发
  ─────────────────
  角色：安全审计师
  任务：审查支付模块
  置信度：68 → 升级给用户确认
```

阈值建议：起始 85%，运行一个月后根据实际修正率调整。

#### 建议 5：结构化输出作为 Agent 间契约（借鉴 MetaGPT）

19 个角色的输出如果不规范，错误传播风险极大。每个角色应输出**结构化 Schema**（而非自由文本），下游角色只能基于明确的字段工作。

```
❌ 当前可能：角色 A 输出一段自然语言 → 角色 B 自行解读
✅ 建议：角色 A 输出 Pydantic Model → 角色 B 只能读取已定义的字段
```

MetaGPT 团队将这一机制视为其最关键的创新——"结构化输出消灭幻觉传播"。

#### 建议 6：设置防循环机制

- 每个角色的 `max_visits` 上限（建议 3 次）
- Supervisor 记录派发历史，禁止同一任务重复派发给同一角色
- 全局 `max_rounds` 上限（建议 ≤ 角色数 × 3）

### 5.3 改进优先级

| 优先级 | 改进项 | 成本 | 收益 |
|--------|--------|------|------|
| 🔴 P0 | Plan-First 确认（建议 2） | 低（一次额外 LLM 调用） | 极高（用户满意度 + 减少重做） |
| 🔴 P0 | 结构化输出契约（建议 5） | 中（需改造角色输出） | 极高（减少级联错误） |
| 🟡 P1 | 关键里程碑检查点（建议 3） | 低 | 高（81% 用户偏好中间确认） |
| 🟡 P1 | 防循环机制（建议 6） | 低 | 高（避免 token 浪费） |
| 🟢 P2 | 分层 Supervisor（建议 1） | 高（架构改动） | 中高（路由精度提升） |
| 🟢 P2 | Supervisor 置信度自评（建议 4） | 中 | 中（渐进式改进） |

---

## 六、关键结论速览

1. **工作流模式本质就三种**：固定 SOP（MetaGPT）、Manager 调度（CrewAI Hierarchical/LangGraph Supervisor）、对话涌现（AutoGen GroupChat/Swarm Handoff）。MyAgent 属于 Manager 调度族。

2. **确认时机是 2025-2026 年学术界的热点**：CHI 2026 的结论是里程碑确认优于终点确认（81% 偏好，效率提升 13.54%）。在计划阶段确认成本最低、收益最大。

3. **19 角色的 Supervisor 面临独特挑战**：路由精度、上下文膨胀、错误传播。分层 + 结构化输出 + 计划预览是针对性解法。

4. **不要过度依赖 Agent 的"自知之明"**：Sycophancy 问题意味着 Agent 可能为了迎合你而修改正确决策。显式的确认机制（而非依赖 Agent 主动提问）更可靠。

5. **Anthropic 的忠告值得反复强调**：从最简单方案开始，Workflow 优先于 Agent，框架会隐藏错误。对 MyAgent 而言，每增加一个角色都应问"这个角色是否真的需要，还是可以用更少角色 + 更好的 prompt 解决？"

---

## 附录：参考来源

- MetaGPT 架构：IBM Think Tutorial (2025)、掘金深度解析 (2025)
- CrewAI 文档：docs.crewai.com Collaboration、FAQs
- AutoGen v0.4：Microsoft Research 论文、Handoffs 设计文档、阿里云架构演进分析
- LangGraph：docs.langchain.com Thinking in LangGraph、madebyagents.com 架构分析
- Anthropic Building Effective Agents (2024.12)
- CHI 2026: "When Should Users Check? A Decision-Theoretic Model of Confirmation Frequency in Multi-Step AI Agent Tasks" (Zhou et al.)
- HITL Patterns: Harness Engineering Academy (2025)、OpenNash (2026)、DevRev (2026)
- Sycophancy 研究：Randal S. Olson / Goodeye Labs、独立学术研究对比测试
