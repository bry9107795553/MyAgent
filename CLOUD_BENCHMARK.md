# 云部署 A/B 基准测试手册（CLOUD_BENCHMARK）

> 用途：在**一次性云 GPU** 上完成方案 A 的实测 A/B 测速（Plan A7），拿到可写入提交材料的真实数据。
> 原则：**同一台机器、同一模型、同一 prompt 输入、只换角色 prompt 版本。**
> ⚠️ 禁止把本地「字数降幅 −59.9%」当测速实测值报给评委——那只是 prefill 体积估计，不是 TTFT 实测。

---

## 0. 为什么要在云端做

- 本地无 GPU，跑不了 Qwen2.5-14B-Instruct 真实推理。
- 赛事 GPU 队列难抢，**部署窗口有限**——必须一次部署、脚本化、自动采集，避免反复排队。
- 方案 A 的「速度分 20 分」要靠**真实 prompt_tokens / TTFT** 支撑，估算值不足以服人。

---

## 1. 部署前准备（本地）

1. 确保 `git` 工作区干净：`git status` 无未提交改动（本仓库 HEAD `b884112` 已含全部 A/C 改动）。
2. 确认 `PROMPT_VARIANT` **未设置**（默认走原版 `prompt.txt`，作为 A 组基线）。
3. 把本仓库推到可云端访问的远程（GitHub/GitCode），或打包上传。
4. 准备 3 个**固定**的任务输入（见第 4 节样本），写入文件，A/B 两组用**完全相同**的输入。

---

## 2. 云端环境搭建（一次性）

```bash
# 1. 拉取代码
git clone <your-remote> MyAgent && cd MyAgent

# 2. 安装依赖（项目自带脚本）
bash install.sh
# AMD ROCm 环境确认 llama.cpp 能调用 Radeon GPU
rocm-smi || amd-smi        # 确认 GPU 可见

# 3. 启动 llama-server（Qwen2.5-14B-Instruct-Q4_K_M）
#    （参照项目 setup_amd_cloud.sh / start.sh）
python -m llama_cpp.server \
  --model models/Qwen2.5-14B-Instruct-Q4_K_M.gguf \
  --n-gpu-layers 999 --host 0.0.0.0 --port 8000 &

# 4. 启动 MyAgent 后端
bash start.sh

# 5. 健康自检
curl -s http://localhost/api/health
curl -s http://localhost:8000/v1/models | grep -i qwen
```

---

## 3. A/B 开关机制（已在代码内）⚠️

`backend/core/agent/loader.py`：
- `PROMPT_VARIANT` 不设 → 加载 `prompt.txt`（**A 组：原版**）
- `PROMPT_VARIANT=slim` → 加载 `prompt.slim.txt`（**B 组：精简版**）
- 缺失 slim 自动回退原版（已回归验证）

切换只需在启动后端前设置环境变量，**无需改代码、无需重启模型服务**：

```bash
# A 组（基线，默认）
unset PROMPT_VARIANT

# B 组
export PROMPT_VARIANT=slim
```

---

## 4. 采样设计

- **3 类任务 × 5 次重复 = 15 组 / 版本**，共 30 次 dev_full 跑批。
- 取**中位数**；**丢弃每组首次**（避开模型冷启动）。
- 任务样本（固定输入，A/B 完全一致）：
  1. 「开发一个带增删改查的待办事项 Web 应用」
  2. 「做一个个人博客系统，支持 Markdown」
  3. 「写一个 REST API 服务，含用户鉴权」
- 每次只触发 `dev_full` 工作组（`trigger_keywords` 已含「开发/做一个/写一个」）。

---

## 5. 采集指标（4 项）

| 指标 | 来源 | 说明 |
|------|------|------|
| ① TTFT（首字延迟） | 后端日志 / llama-server `usage` | 第一条 token 耗时 |
| ② 端到端耗时 | dev_full 流水线起止时间戳 | 9–10 步全链路 |
| ③ 输出质量 | `quality_checker` **盲评**（1–5） | 不告知哪版是精简版 |
| ④ 实际 prompt_tokens | llama-server `usage.prompt_tokens` | **直接读，不估算** |

> 关键：④ 必须读 `usage.prompt_tokens` 真实值。蓝图里「约 34000 词元」是 0.7 tok/字 的**估算**，写入材料前必须被此处实测替换。

---

## 6. 自动化采集脚本（建议）

在云端写一个 `bench_ab.sh`，循环 15 次，每次：
1. 设/清 `PROMPT_VARIANT`，重启后端（`bash stop.sh && bash start.sh`）。
2. `curl` 触发 dev_full，带 `X-Request-Id` 头，记录开始/结束时间。
3. 从后端日志抓取该请求的 `prompt_tokens` 与 TTFT。
4. 把结果 append 到 `bench_{variant}.csv`。

伪结构：
```bash
for variant in original slim; do
  [ "$variant" = slim ] && export PROMPT_VARIANT=slim || unset PROMPT_VARIANT
  bash stop.sh; bash start.sh; sleep 5
  for i in 1 2 3 4 5; do
    start=$(date +%s%3N)
    curl -s -X POST http://localhost/api/chat \
      -H "Content-Type: application/json" \
      -d '{"message":"开发一个带增删改查的待办事项 Web 应用"}' > /dev/null
    end=$(date +%s%3N)
    # 从日志抓取 prompt_tokens / ttft，写入 bench_$variant.csv
  done
done
```

---

## 7. 判据（采纳 / 回退）

- **采纳 B 组（精简版上线）**：B 组 `prompt_tokens` 降幅 **≥ 70%** **且** 质量盲评分下降 **≤ 0.3**。
- **回退该份重新精简**：质量分掉 **> 0.5**。
- **保留双版本**：生产默认 `PROMPT_VARIANT` 不设（原版），演示/速度敏感场景切 `slim`（已验证可秒切）。

---

## 8. 报告模板（填入实测后）

| 指标 | A 组（原版）中位数 | B 组（slim）中位数 | 降幅 |
|------|------------------:|------------------:|-----:|
| prompt_tokens / dev_full | ? | ? | ?% |
| TTFT | ? ms | ? ms | ?% |
| 端到端耗时 | ? s | ? s | ?% |
| 质量盲评（1–5） | ? | ? | Δ? |

> 结论：B 组 prefill 降幅 X%、质量分 ΔY（≤0.3 → 采纳）。
> 本地估算曾报 −59.9% 字数 / 约 −83% prefill 词元——**以上实测为准**。

---

## 9. 安全与边界

- 不要在云端提交任何密钥；`secrets.json`/`credentials.json` 已在 `.gitignore`。
- 测速期间不要改 prompt 内容，否则 A/B 不纯粹。
- 队列难抢：脚本化后**一次跑完 30 次**再关实例，避免反复排队烧钱。
- 完成后务必 `bash stop.sh` 并释放云 GPU 实例。
- 90 秒「投毒」演示（EXECUTION_LOG 第 4 节）也在此云端环境录制：用真实 LLM 跑 dev_full，手动改 `data/experiences/` 里一条经验的 `successful_approach` 为错误步骤，观察评估员判 −2 与 −3 出局。
