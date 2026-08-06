# 侦察报告 · 多Agent前台接待（Triage/Dispatcher）设计

## 关键发现

### 1. 业界共识：路由/分诊是独立的架构模式，不是附带的优化
Anthropic 将 Routing 列为五大工作流模式之一，与 Prompt Chaining、Parallelization、Orchestrator-Workers、Evaluator-Optimizer 并列[1]。OpenAI Agents SDK 将 Triage Agent + Handoff 作为多Agent系统的核心入口模式，handoff 被设计为一级原语（本质上是 tool call 的变体——agent 调用 handoff 函数即转移执行权）[2]。两者都强调：前台只做路由，不回答业务问题。

### 2. 前台 prompt 的五个关键部分（来自多Agent prompt 工程实践和 Anthropic/OpenAI 指南的交叉验证）

**一个能用的前台 prompt 必须包含以下五个部分：**

**(1) 角色边界——“你只做路由”**
必须显式写 `NEVER attempt to answer the user's question yourself`。没有这句话，Claude/GPT-4 这类强模型会在看到自己能回答的问题时直接"帮忙"，绕过路由体系[3]。路由Agent的角色声明应极窄："Analyze incoming requests and route to the correct specialist. You do NOT answer questions directly."

**(2) 子Agent能力清单——让前台知道"谁擅长什么"**
每个子Agent需要暴露 `name` + `instructions`（描述其职责和能力），前台据此做路由决策[2][4]。清单写法要点：每个子Agent的描述应该是"什么时候路由给它"的条件，而非抽象的角色描述。例如：`"Route here when the user asks for facts, definitions, or data"` 优于 `"ResearchAgent: handles research"`。

**(3) 结构化输出契约——JSON schema 不可妥协**
前台必须输出结构化JSON（而非自由文本），包含：`route_to`（目标agent名）、`reasoning`（一句话理由）、`original_request`（用户原话，不改动）、`context`（目标agent需要的附加上下文）[3]。结构化输出让下游agent和编排代码都能可靠解析，出错可追溯。

**(4) 兜底与升级规则——"NONE"路由 + 置信度阈值**
两个层次：① 当没有agent能处理时，必须返回 `route_to: "NONE"` 而非强行匹配——few-shot 中必须包含 NONE 的示例，否则模型会强制匹配[3]；② 置信度不足时可以追问 1-2 个澄清问题后再决策（企业级客服的"渐进式澄清"模式，典型阈值 0.7-0.8）[5]。涉及敏感操作（退款、投诉、账户删除）建议设置硬规则直接升级人工，不经过AI路由[5]。

**(5) 上下文传递协议——handoff 时带什么信息**
路由决策本身不传递业务上下文，handoff 执行时必须携带：用户原始请求、前台推理摘要、已确认的关键实体（日期/金额/账号等）。企业级系统实测：结构化实体提取准确率 92.1%，自由文本仅 74-81%[5]——这意味着前台应尽量在对话中引导用户给出结构化信息。

### 3. 从企业级客服借鉴的关键模式
- **渐进式澄清**（progressive clarification）：置信度在 0.4-0.7 之间时，AI 追问 1-2 个问题再决定，非直接放弃或乱猜[5]。
- **多信号升级**：不只依赖意图置信度，同时监控用户情绪（sentiment）、重复提问频率（friction signals）、业务敏感词（"退款""投诉"）作为升级触发[5][6]。
- **温转接**（warm transfer）：AI 在转接前向人类坐席推送上下文摘要，让客户不用重复叙述[5]。对AI-to-AI handoff同样适用。

### 4. 模型选择策略
- 路由/分诊：用快且便宜的模型（Claude Haiku 或 GPT-4o-mini），因为分类任务不需要深度推理[1][2]。
- 复杂任务子Agent：用强模型。
- Anthropic 原文："将简单问题路由到 Haiku，复杂问题路由到 Sonnet——在优化成本的同时保持质量。"

### 5. 不要过早引入多Agent
Anthropic 和 OpenAI 都明确：从单Agent开始，仅在遇到明确瓶颈时拆分。对前台接待场景而言——如果子Agent数量 ≤5 且职责清晰不重叠，triage pattern 有用；如果只有 2-3 个下游，一个稍长的 prompt + 工具调用可能就够了[1][2]。

## 风险与注意事项

- **范围蔓延是路由Agent最常见的失败模式**：没有明确"你不能回答问题"时，强模型会自己回答。这是多篇实践文章一致指出的头号坑[3][7]。
- **Few-shot 必须包含负面示例**：如果没有"route_to: NONE"的示例，模型会在所有输入上都强行匹配到某个子agent，导致错误路由[3]。
- **协调Agent用 temperature=0**：路由决策不需要创意，temperature>0 会导致同一输入产生不同路由，不可调试[3]。
- **handoff 带来的延迟累积**：每次 handoff 增加 1-3 秒。前台→子Agent 一次 handoff 尚可接受，但应避免链式多次 handoff（A→B→C→D）[2]。
- **企业级客服的 confidence threshold 需要按意图分别调优**：不同意图对误判的容忍度不同。取消账户的阈值应远高于查询物流[5]。

## 建议关注

1. **Anthropic 的"ACI（Agent-Computer Interface）"概念**：将工具定义、参数schema、错误语义视为Agent对世界的感知界面，质量直接决定Agent行为质量[1]——对前台而言，子Agent的 name+instructions 就是它的ACI。
2. **OpenAI Agents SDK 的 handoff 原语设计**：handoff 被实现为 tool call 的语法糖，前台 agent 通过"调用 handoff 函数"来转移控制权——这是一个极简且可调试的抽象，值得在设计前台时参考[2]。
3. **多信号升级体系**：企业级客服已经验证了"意图置信度 + 情绪 + 业务规则 + 用户价值"的组合路由优于纯意图路由[5][6]，这对复杂业务场景的前台设计有直接参考价值。

---
来源：
[1] Anthropic, "Building Effective Agents", Dec 2024
[2] OpenAI, "A Practical Guide to Building Agents" (Agents SDK), 2025; OpenAI Swarm/Agents SDK 文档
[3] Helain Zimmermann, "Prompt Engineering for Multi-Agent Workflows", 2025
[4] Anthropic Engineering, "How we built our multi-agent research system", Mar 2025
[5] JustCall, "How AI Contact Center Determines Caller Intent", 2025; Baidu Cloud 智能客服架构分析
[6] Buzzi.ai, "Hybrid Chatbot Development: Intelligent Routing", 2025
[7] Luis Mori, "How to Write Robust System Prompts for AI Agents Across LLMs", 2025
