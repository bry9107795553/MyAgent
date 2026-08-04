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

---

## 8. 单卡模式修复（P0 · 上机演示阻断级）

> 触发：核查发现「配置默认值与实际部署环境不符」——`single_gpu_mode` 默认 `False`（三卡路由），
> 而交付环境是 Radeon Cloud **单卡** Radeon PRO W7900 / 48GB，`setup_amd_cloud.sh` 也只起 1 个 llama-server。
> 授权范围：修复类，直接改源码，改完 commit。

### 8.1 问题定性

| 项 | 结论 |
|---|---|
| 现象 | 部署阶段**完全正常**，单角色对话也正常；跑到多角色流水线中途才 `Connection error` |
| 根因 | `settings.single_gpu_mode = False` → `gpu_affinity=gpu1/gpu2` 的 **11 个角色**路由到 :8001 / :8002，那里没有服务 |
| 为什么隐蔽 | 失败被 `_degrade()` 吞成降级文案（`[⚠ 角色「X」执行失败，已重试耗尽]`），管线**仍然返回成功**，`[执行失败]` 计数为 0 |
| 危害等级 | P0。GPU 实例排队困难、上机机会可能只有一次，演示录屏跑到一半炸 |

**负向对照实测**（保留旧默认 `SINGLE_GPU_MODE=false`，只起 :8000 的 mock）：

```
[LLM Gateway] 新建本机 GPU 客户端: http://localhost:8002/v1
[Master] 角色 inspector            执行失败 (尝试 1/2, 2/2): Connection error.
[Master] 角色 tester               执行失败 (尝试 1/2, 2/2): Connection error.
[Master] 角色 deployer             执行失败 (尝试 1/2, 2/2): Connection error.
[Master] 角色 cleaner              执行失败 (尝试 1/2, 2/2): Connection error.
[Master] 角色 experience_evaluator 执行失败 (尝试 1/2, 2/2): Connection error.
FAILED_STEPS = 0        ← 管线自认为成功，这正是最恶劣的地方
```

`dev_full` 十步里**后五步全部哑火**，问题被完全掩盖。修复的价值判断以此为准。

### 8.2 为什么不能用 `export SINGLE_GPU_MODE=true`

这是本轮最关键的一个判断。原始建议方向是在 `setup_amd_cloud.sh` 里 `export`，**这条路走不通**：

> 后端不是由 setup 脚本拉起的，而是稍后由 `start.sh` 在**另一个 shell 进程**中用 uvicorn 启动。
> setup 里 export 的环境变量不会传递到那个进程，跑完 setup 关掉终端就更彻底失效。

因此采用**三层防御**，任何一层单独存在都能保证正确：

| 层 | 位置 | 作用 |
|---|---|---|
| L1 默认值 | `backend/config/settings.py` → `single_gpu_mode: bool = True` | 什么都不配也是对的。即使绕过所有脚本手工起后端仍然正确 |
| L2 落盘固化 | `setup_amd_cloud.sh` Step 9 → 写 `backend/.env` | 跨 shell、跨重启生效；显式可审计，`cat backend/.env` 一眼看到 |
| L3 启动预检 | `start.sh` Step 0 + `RoleLoader._report_gpu_routing()` | 启动日志打印实际路由，上机 5 秒自查，不用等演示炸场 |

### 8.3 改动清单

| 文件 | 改动 | 可回退性 |
|---|---|---|
| `backend/config/settings.py` | 默认 `single_gpu_mode=True`（含注释说明取值理由）；新增模块常量 `MULTI_GPU_ENDPOINTS`；新增 `resolve_inference_url()` / `describe_gpu_routing()` | 改回 `False` 即恢复旧行为 |
| `backend/core/role/role_base.py` | `_get_gpu_url()` 去掉硬编码端口表，改为薄封装调用 `settings.resolve_inference_url()`；`get_status()` 增加 `inference_url` 字段 | 纯收敛，无行为增量 |
| `backend/core/role/loader.py` | `load_all()` 末尾新增 `_report_gpu_routing()`：打印路由摘要 + 单卡降级告警 / 多卡就绪告警 | 纯新增日志 |
| `setup_amd_cloud.sh` | 新增 `SINGLE_GPU_MODE` 变量（默认 true）+ 参数横幅展示 + 非 true 时告警；Step 9 幂等写 `backend/.env`（`set_env_kv`，只覆写 3 个 key，用户其它配置保留）；完成横幅说明单卡路由与切多卡方法 | 删除 Step 9 的 env 块即可 |
| `start.sh` | 新增 Step 0 GPU 路由预检：读 `backend/.env`，缺省视为 true；多卡模式下打印醒目告警 | 纯新增 |
| `data/role_pool.json` | 新增 `single_gpu_fallback` 元数据块：说明 gpu_allocation 仅多卡生效、model 字段是元数据、visual_analyzer 降级说明 | 纯文档字段，不被代码读取 |
| `tests/regression_single_gpu.py` | **新增** 32 断言回归 | 独立文件 |

**路由收敛**是本轮的结构性改进：改之前端口表硬编码在 `role_base._get_gpu_url()` 里，
单卡分支写死 `http://localhost:8000/v1` —— 意味着按 `QUICKSTART_CLOUD.md` 改 `LLAMA_PORT` 避端口冲突时，
单卡路由还会往 8000 打。现在全系统只有 `settings.resolve_inference_url()` 一个出口，单卡模式跟随 `llama_base_url`。

### 8.4 同类隐患核查结论

按「既然发现一处默认值与部署环境不符，把同类问题一次查完」的要求，逐项核实（读实现，不看注释）：

**1. gpu1/gpu2 的 11 个角色是否真的全部回落 8000 —— 是。**

`resolve_inference_url()` 在 `single_gpu_mode` 分支**直接 return，根本不查 MULTI_GPU_ENDPOINTS**，
不存在「漏网亲和值」的可能。回归中对 11 个角色逐个点名断言，另加 `gpu7` / 空字符串两个越界输入，全部回落。

**2. `model` 字段会不会导致 400 unknown model —— 不会。这一点属于误判，已验证澄清。**

- role_pool 里角色的 `model` 只有 `text` / `vision` 两个值；`Qwen2.5-7B` 那两处在 `gpu_allocation` 块里，
  是**分配规划元数据，代码从不读取**（全仓 grep 确认：只有 `role_base` 读 `model` 和 `gpu_affinity`）。
- 真正决定请求里 model 名的是 `gateway._get_model_name()`，它**恒定返回 `settings.llama_model`**，
  连 `base_url` 参数都没用上。角色的 `model` 字段**永远到不了 llama-server**。
- 结论：单卡加载 14B 时，`visual_analyzer` 不会因模型名不存在而报 400。
- **真实影响是能力降级而非崩溃**：VL 权重没加载，该角色会以文本模型身份正常应答，「看图」是假的。
  已按「宁可显式降级、不要静默假装」处理：启动日志打印
  `⚠ 单 GPU 模式下未加载专用模型的角色: visual_analyzer …`，role_pool 中记入 `degraded_roles`，
  README 中加 Note 明示。该角色不在 `dev_full` 链路，不影响演示。

**3. `setup_amd_cloud.sh` 的三卡残留 —— 核查后确认脚本正文本来就没有。**

脚本里没有 8001/8002 端口、没有 `ROCR_VISIBLE_DEVICES`、没有多实例启动逻辑，无需清理。
真正的三卡残留在 README（见 8.6）和 `role_pool.json` 的 `gpu_allocation`
（已加 `single_gpu_fallback` 块限定其适用范围）。

### 8.5 回归验证

环境：Windows / Python 3.13 / venv `.venv-diag` / mock llama-server **只监听 :8000**
（故意不起 8001/8002 —— 任何越界路由都会立刻表现为连接失败，而不是被静默容忍）。

```
.venv-diag/Scripts/python.exe tests/regression_single_gpu.py
  单 GPU 模式回归: PASS=32  FAIL=0
```

| 验证项 | 结果 |
|---|---|
| 不设任何环境变量 → `single_gpu_mode=True` | ✅ |
| `resolve_inference_url` 对 gpu0/gpu1/gpu2/gpu7/空 一律回落 | ✅ 5/5 |
| 改 `LLAMA_BASE_URL` 后单卡路由跟随（未硬编码 8000） | ✅ |
| 18 个角色实例端点全部一致 | ✅ |
| 原亲和 gpu1/gpu2 的 11 个角色逐个点名 | ✅ 11/11 |
| gateway 模型名恒为 `settings.llama_model` | ✅ |
| **`dev_full` 端到端跑通** | ✅ 命中工作组，10 步（9 步 + 评估员钩子）全绿 |
| 流水线零失败 / **零降级**标记 | ✅（同时数 `[执行失败]` 与 `执行失败，已重试耗尽`，避免漏判） |
| **全程实际访问端点集合** | ✅ `['http://localhost:8000/v1']` —— 埋点抓取，零 8001/8002 |
| 多卡能力保留：`SINGLE_GPU_MODE=false` → gpu1→8001 / gpu2→8002 | ✅ |
| 环境变量可关闭单卡模式 | ✅ |

存量回归无退化：`regression_plan_a.py` 58/58 ✅、`regression_plan_c.py` 18/18 ✅。

> 埋点方式：monkeypatch `llm_gateway._new_local_client` / `_get_client`，记录每一个被请求过的 `base_url`。
> 这比「看日志有没有报错」强 —— 即使某次调用失败被降级吞掉，端点集合里也会留下痕迹。

### 8.6 README 技术描述修正

原 `## ROCm / AMD GPU Optimization` 下「2. Multi-GPU Parallel Inference」把三卡写成主线，
而演示视频是单卡 —— 评委对不上会怀疑材料真实性。按「单卡优先 + 多卡可选扩展」重写：

| 位置 | 修正前 | 修正后 |
|---|---|---|
| ROCm §2 | Multi-GPU Parallel Inference（三卡 14B/7B/7B 为主线） | **Single-GPU Deployment (Default — as demonstrated)**：实际启动命令、`resolve_inference_url` 说明、启动日志样例，以及「19 角色如何塞进一张 48GB 卡」的四条技术依据（Q4_K_M / GQA KV 预算 / 顺序执行 / 全量 offload） |
| ROCm §3 | Single GPU Mode（一段话带过） | **Multi-GPU Affinity (Optional Scale-Out)**：保留三卡设计与命令，明确标注 *designed and implemented but not part of the demonstrated deployment* |
| 角色数 | 正文 3 处 "15 roles" | **19**。核实口径：`role_pool.json` 18 个可调度角色 + `secretary`（常驻后台，`orchestrator.py` 中实现，不走 role_pool）= 19，与 `backend/core/agent/roles/` 的 19 个提示词目录一致。角色表补齐原先漏列的 Handoff Receiver / HR Manager / Experience Evaluator / Secretary |

同批修掉的其它「与实际不符」（同一类技术性错误，一并更正）：

- **部署架构图里的 `Cloud API / Fallback Only` 方框** —— 与 README §5「Local-Only Inference Guarantee」
  和代码事实（云端通路已物理删除）**直接矛盾**。这是合规硬伤：一边声明「不存在远程通路」，
  一边画图承认有云端兜底，评委看到会直接质疑合规声明的可信度。已替换为单卡架构图 + 可选多卡架构图。
- 预设工作组 "9" → **10**（漏列 `dev_modification`），并按 `data/workgroups/*.json` 实际 pipeline
  逐个校正流水线串（原表多处与实际不符，如 dev_full 漏了 Deployer）。
- Models Used 表的 GPU 列改为「默认单卡部署是否加载」，明示 7B / VL-7B 在演示配置中**未加载**。
- Prerequisites 的 VRAM 行原写 `≥48GB (3-GPU)`，改为以单卡为基准。
- Core Capabilities §3 "parallel scheduling across 3 GPU instances" 改为单卡顺序执行为主、多卡为可选。

未触碰 `## Team` / `## Demo Video` 两节（前台出口材料，另有归属）。

### 8.7 遗留观察（本轮未改，留给决策）

1. **`start.sh` 不使用 setup 生成的 `start_llama.sh`** —— setup 按 W7900 校准出
   `CTX_SIZE=8192 / PARALLEL=1 / BATCH=512` 并写进 `start_llama.sh`，但 `start.sh` 自己用
   `-c 32768 -ngl 99` 硬编码另起一份 llama-server，**调参结果实际没被用上**。
   端口一致（都是 8000）所以不影响本轮修复的正确性，但属于同类「两处配置各说各话」，建议后续统一。
2. **单卡模式下 `_dispatch_to_roles` 仍按 gpu_affinity 分组并行** —— 三组会并发打同一个
   llama-server。`--parallel 1` 下请求排队不会崩，但排队时间计入各角色 120s 超时，
   角色多时有超时放大风险。`dev_full` 是纯串行 pipeline（`parallel_with` 全空），**不受影响**，
   故本轮未动；若后续演示走「动态组装」路径需复评。
3. **`dispatcher_config.json` 的 `parallel_matrix.gpu2_roles` 缺 `experience_evaluator`** ——
   与 `role_pool.json` 的 gpu2 列表不一致。仅影响多卡模式下的并行规划元数据，单卡无影响，未改。

---

## 9. 工具调用闭环接通（评分表「工具调用」能力项 · 20 分）

> 触发：赛道评分表第 2 项要求「任务分解、**工具调用**、RAG、记忆管理」，
> 我们一直对外声称实现了工具调用，但核查代码发现**它实际没接通**——两端（工具实现层 / 注册表 / 网关）都是完整的，中间两环断着。
> 授权范围：修复类，直接改源码，改完 commit；只做这一件事（上云脚本 / prompt / 记忆系统未碰）。

### 9.1 问题定性

| 项 | 结论 |
|---|---|
| 工具实现层 | 完整：`backend/core/tools/builtin/` 5 个真工具（file_read / file_write / file_list / code_exec / web_search），含 `_is_within_project()` 沙箱校验 |
| 注册表 | 完整：`ToolRegistry` 有 `register/get/get_available_tools/get_tool_definitions`，`BaseTool.to_openai_format()` 输出标准 schema，全局单例 `tool_registry` 在 base.py:160 |
| 网关层 | 完整：`gateway.py:134` 已把 `tools` 传给 `client.chat.completions.create()`，`:143-149` 已把 `tool_calls` 解析成 `result["tool_calls"]` |
| 断点 A | 没人往里传工具定义：全库 grep `get_tool_definitions\|tool_registry\|get_available_tools`（排除 `core/tools/` 自身）外部调用点为零 → gateway 的 `tools` 永远收到 `None` |
| 断点 B | 没人消费返回的 `tool_calls`：全库 grep `tool_calls` 只有 gateway.py 那 5 行，没有任何地方执行工具、回填 messages、再请求模型 |
| **隐藏根因** | **内置工具从未在运行时注册**：`core/tools/__init__.py` 的 `from core.tools import builtin`（注册副作用）从未被任何启动路径 import，导致 `tool_registry` 始终为空。即使接上 A/B，不修这个也是空转 |

> `loader.py:366` 那句 `tools = "、".join(self.tool_names)` 只是把工具名拼进提示词文本，**那是"告诉模型你有这些工具"，不是 function calling**，勿误判为已实现。

### 9.2 改动清单

| 文件 | 改动 | 可回退性 |
|---|---|---|
| `backend/core/role/role_base.py` | 顶部 `import json` + `from core.tools.base import tool_registry`（导入即触发内置工具注册，修复隐藏根因）；新增模块常量 `MAX_TOOL_ITERATIONS = 5`；重构 `_call_llm()`：构造 `agent_config={"tools": {name:True for name in self.tool_names}}`，调 `tool_registry.get_tool_definitions(agent_config)` 取该角色授权 schema 传给 gateway（断点 A）；新增 `_run_tool_loop()`：模型返回 `tool_calls` → 逐个 `tool_registry.execute_tool()` 执行 → 结果以 `role:"tool"` 消息回填 → 再请求模型，直到不再要求调工具或达上限（断点 B） | 纯新增 + 收敛，无行为增量；回退即恢复旧 `_call_llm` |
| `data/role_pool.json` | `developer.tools` 由虚构名 `["code_writer","file_manager","dependency_checker","git_tools","debt_tracker"]` 改为真实注册名 `["code_exec","file_read","file_write","file_list"]`——让演示路径（写文件）真能调起 file_write，且白名单变为真实可调用工具 | 改回原数组即恢复 |

**未碰**：其他 17 个角色的 `tools` 仍是虚构名（无对应注册工具 → 经注册表过滤后自然为零工具，行为不变）；`setup_amd_cloud.sh` / prompt 文件 / 记忆系统均未改动。

### 9.3 断点 A / B 接通方式（尊重角色级授权，不绕过）

- 角色级工具授权是**设计好的**（`get_available_tools(agent_config)` 按 `tools` 段过滤），`role_pool.json` 的 `tools` 字段即授权白名单。本改动严格走这条过滤链：角色 `tool_names` → `agent_config["tools"]` → `get_tool_definitions()`，不另起一套。
- 无工具授权的角色：`tool_defs` 为空 → 传 `tools=None`，与历史行为**字节级一致**（gateway 本就接收 `tools=None`）。
- 有授权的角色（developer）：传入 4 个真实 schema，模型可发起 function calling。

### 9.4 最大轮次 & 容错（上机演示防死循环）

- **最大轮次上限 `MAX_TOOL_ITERATIONS = 5`**：模型连续要求调工具达到 5 轮后强制返回，绝不无限循环占死 GPU。
- **容错**（llama.cpp 对 function calling 支持不如闭源 API 稳定，格式可能不标准）：
  - `arguments` 非合法 JSON → 解析失败降级为空参 `{}`，不崩；
  - 未知工具名 → 注册表返回「工具不存在」，作为 tool 消息回填让模型自行恢复，不崩；
  - 工具执行异常 → 注册表 `execute_tool()` 已捕获 `TypeError/Timeout/Exception` 并返回错误 dict；
  - LLM 调用本身异常 → 循环内 try/except 交还上一轮文本，不让工具循环吞掉错误。
- 解析失败 / 未知工具均**不误写文件**（回归已验证）。

### 9.5 回归验证

环境：Windows / Python 3.13 / venv `.venv-diag` / 真·mock llama-server（OpenAI 兼容，监听 :8000，模型 `Qwen2.5-14B-Instruct`，上一会话遗留仍在运行）。

| 测试 | 结果 |
|---|---|
| `tests/regression_tool_loop.py`（新增，进程内假 LLM 客户端闭环） | **PASS=19  FAIL=0** |
| ├ 内置工具已注册（修复隐藏根因） | ✅ 5 个工具全部注册 |
| ├ 断点 A：developer 的 LLM 调用带上了工具 schema（4 个） | ✅ |
| ├ 断点 B：file_write 闭环 → **真实落盘** → 结果回填 → 模型二次回答 → 返回最终文本（2 次 LLM 调用） | ✅ 文件确实出现在磁盘 |
| ├ 最大轮次上限：模型死循环调工具在第 5 轮强制结束 | ✅ 恰好 5 次调用，不卡死 |
| ├ 容错：参数非合法 JSON / 未知工具名 → 不崩、降级为普通回复、不误写文件 | ✅ |
| ├ 未授权角色（coach，tools 全虚构名）→ 不带 tools（与历史一致） | ✅ |
| └ `dev_full` 七角色流水线在工具循环激活下照样跑通，零失败标记，developer 在管线内也带上了工具 schema | ✅ |
| `tests/regression_single_gpu.py`（既有，32 断言） | **PASS=32  FAIL=0** —— 无回归，dev_full 十步全绿、零 8001/8002 |

### 9.6 llama.cpp 启动参数结论（需云端最终验证）

- `tools` 走标准 OpenAI function-calling 格式，`llm_gateway` 透传给 `client.chat.completions.create(tools=...)`。Qwen2.5-14B-Instruct GGUF 自带 function-calling chat template，**无需额外 `--jinja` / 特殊 flag** 即可启用工具调用（与闭源 API 同协议）。
- 但**本环境无真实 GPU / 真 llama.cpp**，上述仅基于协议层推断 + mock 验证链路通。真模型对 `tool_calls` 的格式遵循度、是否需要 `--chat-template` 微调，需在云端 W7900 上录制演示时复核。若届时出现工具不被触发或格式错乱，最可能的开关在 `setup_amd_cloud.sh` 的 llama-server 启动参数（`--jinja` / chat template 相关）——届时可在此处追加。

### 9.7 演示路径（评委看得见）

- 用户让 developer 角色「写个文件」→ developer 被授权 `file_write` → 模型返回 `file_write` tool_call → 后端执行、文件**真的出现在磁盘**（沙箱限定在项目根目录内）→ 结果回填 → 模型总结「已写入」。这是一条可演示的工具调用闭环。
- 前端展示位：当前未确认前端是否已有 tool_call 展示位。后端执行与落盘已就绪；若前端无展示位，**按边界不自行设计 UI**，交由 team-lead 决定。

### 9.8 遗留 / 边界记录

1. **其他 17 个角色的 `tools` 字段仍是虚构名**（`requirement_tools`、`dispatch_tools` 等），无对应注册工具 → 经注册表过滤后为零工具。这是「权限控制」能力的真实面：只有 developer 当前接了真实工具。若要扩展演示覆盖面，需为每个角色补齐真实注册工具（超出本轮回退范围）。
2. **流式路径（`execute_stream` / `chat_stream`）未接工具循环**：本轮只接通非流式 `execute() → _call_llm()` 路径（演示路径即此）。流式角色不会触发 function calling，属已知限制，未动以免扩大范围。
3. **`streaming` 与 `tools` 不可同时**：OpenAI 流式接口下 tool_calls 拼接复杂，故意不在本轮实现。
