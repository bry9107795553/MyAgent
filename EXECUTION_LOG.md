# 执行日志（EXECUTION_LOG）

> 任务：MyAgent 私有 AI Agent 平台 — 方案 A（prompt 精简）+ 方案 C（记忆系统补齐）
> 赛道：AMD AI DevMaster Hackathon · 赛道 2（私有 AI Agent + AMD Radeon GPU 本地部署）
> 执行方式：用户已授权动源码；git → A → C 三阶段，每阶段完成后 commit。

---

## 1. Git 状态

| 阶段 | Commit | 内容 |
|------|--------|------|
| 初始 | `e8c4716` | 初始提交（157 文件，无密钥泄漏） |
| A-前置 | `eec4f7a` | loader 增加 `PROMPT_VARIANT` 开关 + dev_full 链路 9 份 slim |
| A-收尾 | `bda5bec` | 剩余 9 份 slim（全部 18 份到位，字数入区间） |
| A-回归 | `033fabb` | `tests/regression_plan_a.py`（55 断言） |
| C-落地 | `b884112` | 效用评分 + 知识 TTL + 评估员角色 + 钩子 + 回归测试 |

当前 HEAD：`b884112`。**未 push**（推送需用户 GitHub 账号，`gh` CLI 缺失，Credential Manager 已配）。

> ⚠️ `data/memory/knowledge.json` 为运行时数据（从未入库，git 中不跟踪）。执行过程中回归测试一度误写该文件，**已恢复为干净空结构**，保持未跟踪状态，未进入任何提交。

---

## 2. Plan A：18 份 prompt 精简字数对照表

度量口径：蓝图「字」= 中文字符 CJK（`[\u4e00-\u9fff]`），非总字符数。
复杂角色集合 `{coach, master, handoff_receiver, secretary}` 上限 **1200**；其余上限 **900**。

| 角色 | slim(CJK) | 原版(CJK) | 上限 | 状态 |
|------|----------:|----------:|-----:|:----:|
| cleaner | 620 | 1872 | 900 | ✅ |
| coach | 868 | 3882 | 1200 | ✅ |
| creative | 893 | 2081 | 900 | ✅ |
| deployer | 847 | 1941 | 900 | ✅ |
| designer | 667 | 1967 | 900 | ✅ |
| developer | 640 | 2084 | 900 | ✅ |
| handoff_receiver | 1125 | 2115 | 1200 | ✅ |
| hr_manager | 887 | 1935 | 900 | ✅ |
| inspector | 839 | 2304 | 900 | ✅ |
| knowledge_retriever | 898 | 2098 | 900 | ✅ |
| master | 1086 | 2453 | 1200 | ✅ |
| quality_checker | 601 | 1721 | 900 | ✅ |
| scheduler | 885 | 1906 | 900 | ✅ |
| secretary | 1194 | 2642 | 1200 | ✅ |
| tester | 717 | 2057 | 900 | ✅ |
| translator | 850 | 1377 | 900 | ✅ |
| visual_analyzer | 890 | 2340 | 900 | ✅ |
| writer | 810 | 1415 | 900 | ✅ |
| **TOTAL** | **15317** | **38190** | — | **−59.9%** |

- 原 `prompt.txt` **零改动**（可逆性保证：`PROMPT_VARIANT` 清空即回退原版）。
- 切换机制：`loader.get_prompt_variant()` 读环境变量；`_load_prompt_file()` 在 `slim` 且文件存在时加载 `prompt.slim.txt`，否则回退 `prompt.txt`（缺失自动回退已验证）。

### 2.1 secretary 孤儿文件说明
`backend/core/agent/roles/secretary/prompt.txt`（原 2642 CJK）**从未被 RoleLoader 加载**。
根因：`orchestrator.py:382` 定义 `class Secretary:` 为硬编码 Python 单例（非 LLM 角色），不在 `role_pool.json` 中；其 LLM 调用使用内联 prompt（`orchestrator.py` 内联），从不读 `prompt.txt`。
→ 按用户指示仍精简并写出 `prompt.slim.txt`（1194 CJK），但它是**孤儿文件，运行时不被加载**。如需真正生效，需在 `Secretary` 类中把内联 prompt 改为读取 `prompt.slim.txt`/`prompt.txt`——本轮回退范围，未做。

---

## 3. Plan C：记忆系统补齐落地状态

| 子项 | 内容 | 落地 | 性质 |
|------|------|:----:|------|
| C-1 效用评分 | `ExperienceRecord` +5 字段（`utility_score/applied_count/last_applied/evaluator_notes/status`，全默认） | ✅ | 纯加法，老 JSON 零迁移 |
| C-1 | `vote(record_id, delta, note)`：+1/−1/−2/0；≤−3 标 `archived`；<0 标 `probation` | ✅ | 新增方法 |
| C-1 | `_evict_if_full(task_type, capacity=15)`：池满淘汰最低分 | ✅ | 新增方法 |
| C-1 | `get_utility_report()`：按效用分降序供演示 | ✅ | 新增方法 |
| C-1 | `find()` 排序键改 `(-utility_score, -success_count)` | ✅ | **改 1 行** |
| C-1 | `get_injection()` 过滤 `status=="archived"` | ✅ | **改 1 行** |
| C-2 知识 TTL | `add_triple(knowledge_type="technical")` 新增带默认值参数；三元组加 `knowledge_type/expires_at/staleness` | ✅ | 参数加法，调用方零改动 |
| C-2 | `_compute_staleness()`：permanent=0；technical 6月/security 3月/platform 2月；老三元组 `.get(...,"technical")` 兜底 | ✅ | 新增方法 |
| C-2 | `search()` 加权乘新鲜度系数 | ✅ | **改 1 行** |
| C-2 | `assembly_context()` 过期三元组加 `⚠ 可能已过期` 前缀 | ✅ | **改 1 行** |
| C-2 | `sweep_expired()`：过期只降权不删除（置信度按类型折扣），需显式调用 | ✅ | 新增方法 |
| C-2 | `get_freshness_report()`：供演示 | ✅ | 新增方法 |
| C-4 评估员角色 | `role_pool.json` 新增 `experience_evaluator` 条目 + `gpu2.roles` 追加 | ✅ | 加法 |
| C-4 | `backend/core/agent/roles/experience_evaluator/prompt.txt`（842 CJK） | ✅ | 新增文件 |
| C-4 | `master._apply_experience_eval_hook`：dev 工作组收尾追加评估员步骤，**按 workgroup `members` 显式开关**（零侵入） | ✅ | 新增方法 + 1 调用 |
| C-4 | `dev_full` 的 `members` 追加 `experience_evaluator`（演示路径 opt-in） | ✅ | 加法 |
| C-5 演示脚本 | 90 秒「投毒」演出脚本（见第 4 节） | ✅ | 文档 |

### 3.1 「纯新增、仅改 4 行」声明核验
✅ **成立**。既有逻辑的语义修改恰为 4 行：
1. `orchestrator.py` `find()` 排序键
2. `orchestrator.py` `get_injection()` archived 过滤
3. `knowledge_base.py` `search()` 新鲜度系数
4. `knowledge_base.py` `assembly_context()` 过期前缀

其余均为新增（字段/方法/带默认值参数/JSON 条目/角色文件/钩子方法）。`add_triple` 新增参数带默认值，既有调用方（`add_triples_batch`，行 206，关键字调用）零改动——已 grep 确认仅此一处调用。

### 3.2 Plan B 未做的连带影响（重要）
用户决策：**不做方案 B**（保留全部 18 角色、10 个工作组）。
- Plan C-4 原计划「借 Plan B 腾空的 cleanup 钩子位接评估员」的前提不成立。已改为**独立新增钩子** `_apply_experience_eval_hook`，未复用 cleanup 槽位。
- 后果：dev 工作组（如 `dev_full`）收尾会**多 1 步**（评估员 LLM 调用），因未裁 cleaner 而净 +1 步。该调用按 `members` 开关，默认仅 `dev_full` 启用；非 dev 工作组不受影响。

---

## 4. C-5：90 秒「投毒」演示脚本（拿创意分的关键）

> 目标：让评委 90 秒内**看见记忆在自我进化**，而非听我们说它会。

| 时间 | 画面 | 旁白要点 |
|------|------|---------|
| 0–15s | 分屏：左对话框，右 `data/experiences/` 的 JSON 实时刷新 | “我们的团队有记忆。但记忆本身也需要被管理。” |
| 15–35s | **第一次**提同一任务，团队跌跌撞撞完成，经验被记录，`utility_score: 0` | “第一次做，它把成功路径记了下来。” |
| 35–55s | **第二次**提相似任务，经验被注入（高亮注入块），一次通过。评估员打 **+1**，JSON 分数跳到 1.0 | “第二次，它照着自己的经验走，一次过。评估员给了 +1。” |
| 55–75s | **手动篡改**一条经验为错误步骤，再跑 → 失败 → 评估员判 **−2** 并指出哪一步误导 → 分数跌到 −2 | “关键在这——我们故意塞了一条错经验。它失败了，但它**知道是哪一步坑了自己**。” |
| 75–85s | 再跑一次，该经验降到 −3，**自动从注入池消失**，团队恢复正常 | “−3 出局。坏记忆会被自己淘汰掉。” |
| 85–90s | 切知识库面板，一条标着「⚠ 可能已过期」的三元组 | “知识也一样——有保质期。” |

**戏眼**：55–75 秒的「主动投毒」把抽象架构变成**可证伪的现场实验**（Harvard 2025 结论：add-all 比不存更差），评委看得懂、记得住。
**注**：该闭环依赖真实 LLM 调用，需云端 GPU 部署后录制（见 `CLOUD_BENCHMARK.md`）。本地仅验证了效用评分/淘汰/TTL 的**逻辑层**（回归测试 18/0）。

---

## 5. 回归测试结果

| 测试 | 文件 | 断言数 | 结果 |
|------|------|------:|------|
| Plan A 开关 + 完整性 | `tests/regression_plan_a.py` | 55 | ✅ 全过 |
| Plan C 效用评分 + TTL + 接线 | `tests/regression_plan_c.py` | 18 | ✅ 全过 |

Plan A 覆盖：`PROMPT_VARIANT` 未设→原版 / `=slim`→精简版（18 角色均验证）、slim 缺失自动回退、slim 文件非空+含身份+含负向约束+字数入区间。
Plan C 覆盖：老数据缺字段→默认 active 正常注入、`vote` +1/−1/−2/−3 状态流转、`archived` 不注入、`_evict_if_full` 池满淘汰、`get_utility_report` 降序；`_compute_staleness`（permanent=0 / 过期≥1 / 老三元组兜底）、`search` 新鲜度加权、`assembly_context` 过期前缀、`sweep_expired` 只降权不删；钩子仅 members 含评估员且 dev 工作组才追加。

---

## 6. 时间 vs 预估

| 阶段 | 计划预估 | 实际 | 说明 |
|------|---------|------|------|
| Plan A 精简 | 8h（11 份 + 2h A/B + 1h 返修） | 已完成代码 | 实际精简 **18 份**（用户要全做）；GPU A/B 测速按用户边界**推迟到云端**，见 CLOUD_BENCHMARK |
| Plan C | 10h | 已完成代码 + 回归 | 效用评分 + TTL + 评估员 + 钩子 + 脚本，逻辑层全验证 |

> 本环境无 GPU / 真实 LLM，无法跑端到端 A/B（TTFT、prompt_tokens、质量盲评）。这部分按用户边界明确推迟：一次性云部署后按 `CLOUD_BENCHMARK.md` 执行。**禁止把本地的字数降幅当测速实测值报评委。**

---

## 7. 遗留问题 / 需用户决策

1. **secretary 孤儿**：`prompt.slim.txt` 已写但不被加载。若要真正生效，需在 `Secretary` 类把内联 prompt 改为读文件——超出本轮回退范围，待决策。
2. **Plan C 闭环需云端验证**：`experience_evaluator` 作为真实流水线步骤的 LLM 调用、90 秒投毒演示，需在云 GPU 上录制。
3. **+1 步代价**：因未做 Plan B，`dev_full` 收尾多一次评估员 LLM 调用（延迟/成本）。若演示想 zero-step-cost，可后续对 `dev_full` 也临时关掉 cleaner 或评估员。
4. **git push**：当前所有提交在本地，未推送。推送需用户 GitHub 账号（`gh` 缺失，Credential Manager 已配，直接 `git push` 会弹窗授权）。
