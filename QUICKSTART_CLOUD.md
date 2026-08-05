# 上机速查表（排到实例后照着做）

> 这份文件是你**排到 Radeon Cloud 实例后打开的第一个文件**。
> 所有命令都可以**直接复制粘贴**，不需要改任何东西（除非我明确写了「把 xxx 换成 yyy」）。
> 目标环境：AMD Radeon PRO W7900 / 48GB VRAM / ROCm 7.2 / Ubuntu 22.04
>
> **时间预算**：环境确认 2 分钟 → 部署 30–50 分钟（大头是编译 + 下模型）→ 测速 20 分钟 → 录屏 15 分钟。

---

## 名词速查（怕你不熟 Linux）

| 你会看到 | 意思 |
|---|---|
| `$` 或 `#` 开头 | 提示符，**不要**复制它，只复制后面的命令 |
| `~` | 你的家目录，等于 `/home/你的用户名` |
| `sudo` | 用管理员权限执行，可能会要你输密码 |
| `Ctrl + C` | 强行中止当前正在跑的命令 |
| `tail -f xxx.log` | 实时滚动看日志，**按 Ctrl + C 退出**（不会影响服务） |
| 命令行卡住不动 | 大概率是正常的（在编译/下载），先看日志再决定 |

---

## 0. 确认环境（第一件事，2 分钟）

登录实例后，**先跑这三条**，确认分到的确实是 W7900 48GB。

### 0.1 看 GPU 型号和架构

```bash
rocminfo | grep -E "Marketing Name|gfx" | head -6
```

**预期输出**（关键看这两行）：
```
  Marketing Name:          AMD Radeon PRO W7900
  Name:                    gfx1100
```

- ✅ 看到 `W7900` + `gfx1100` → 对了，继续
- ❌ 看到别的型号（比如 `W7800` / `V620`）→ 记下 `gfx` 后面的数字，第 1 步部署时要改参数（见 0.4）

### 0.2 看显存（最关键的一条）

```bash
rocm-smi --showmeminfo vram
```

**预期输出**：
```
====================== ROCm System Management Interface ======================
================================ Memory Usage ================================
GPU[0]      : VRAM Total Memory (B): 51527024640
GPU[0]      : VRAM Total Used Memory (B): 10502144
==============================================================================
```

把 `VRAM Total Memory` 那个大数字 **除以 1073741824** 就是 GB：
`51527024640 / 1073741824 ≈ 48.0 GB` ✅

懒得算就跑这条，直接给你 GB 数：

```bash
rocm-smi --showmeminfo vram --csv | awk -F, 'NR>1 && $2 ~ /^[0-9]+$/ {printf "VRAM = %.1f GB\n", $2/1073741824}'
```

**判断标准**：
- **≥ 45 GB** → ✅ 正常，往下走
- **30–45 GB** → ⚠️ 不是 W7900，但还能跑。部署时用 `CTX_SIZE=8192`（默认值），别调高
- **< 30 GB** → ❌ **立刻停**。跳到 0.5「不对劲怎么办」

### 0.3 看 ROCm 版本

```bash
cat /opt/rocm/.info/version 2>/dev/null || dpkg -l | grep rocm-core
```

**预期**：`7.2.x`。如果是 6.x 也能跑，只是编译参数可能要微调。

### 0.4 如果 GPU 不是 gfx1100

记下 0.1 里看到的实际架构（比如 `gfx1030`），第 1 步的部署命令改成：

```bash
AMDGPU_TARGET=gfx1030 bash setup_amd_cloud.sh
```

（把 `gfx1030` 换成你实际看到的）

### 0.5 不对劲怎么办（显存 < 30GB）

1. **先别销毁**，再确认一次是不是多卡环境：
   ```bash
   rocm-smi
   ```
   如果列出 `GPU[0]` `GPU[1]` 多张卡，说明显存是分开算的，单卡够用就行。

2. 确认真的只有一张小卡 → **销毁实例重新排队**。
   在 Radeon Cloud 控制台点「销毁 / Terminate」，重新申请 W7900。
   排队期间可以先看第 3 节「录屏 checklist」做准备。

3. 或者**将就跑**（降低参数，会影响测速数据的说服力）：
   ```bash
   CTX_SIZE=4096 QUANT=q4_k_m bash setup_amd_cloud.sh
   ```

---

## 1. 一键部署（复制粘贴就能跑）

一共 12 步。**第 4 步和第 5 步最慢**（编译 + 下模型），加起来 30–50 分钟。

### 步骤 1：更新系统 + 装基础工具

```bash
sudo apt-get update && sudo apt-get install -y git curl wget nginx build-essential cmake python3-venv
```

**预期**：一堆滚动的安装日志，最后回到提示符，没有红色 `E:` 开头的报错。

### 步骤 2：拉代码

```bash
cd ~ && git clone <你的仓库地址> myagent && cd ~/myagent
```

> 把 `<你的仓库地址>` 换成你的 GitHub/GitCode 地址。
> **如果没有远程仓库**，用本地上传：在你自己电脑上打包成 zip 传上来，然后
> `cd ~ && unzip myagent.zip -d myagent && cd ~/myagent`

**预期**：
```
Cloning into 'myagent'...
remote: Enumerating objects: ...
Resolving deltas: 100% ...
```

### 步骤 3：确认文件都在

```bash
cd ~/myagent && ls setup_amd_cloud.sh start.sh stop.sh nginx.conf backend/ frontend/
```

**预期**：能看到这 6 个名字，没有 `No such file`。

### 步骤 4：跑部署脚本（最慢的一步，30–50 分钟）

```bash
cd ~/myagent && bash setup_amd_cloud.sh 2>&1 | tee ~/setup.log
```

> `tee ~/setup.log` 的作用：一边显示一边存日志。出问题时把 `~/setup.log` 发出来就能排查。

**预期输出（开头）**：
```
============================================
  MyAgent AMD 云环境部署
  目标: Radeon PRO W7900 / 48GB / ROCm 7.2
--------------------------------------------
  量化版本   : q4_k_m
  总上下文   : 8192
  并发槽位   : 1  (每槽 8192 tokens)
  KV cache   : ~1536 MiB
  GPU 架构   : gfx1100
  模型路径   : /home/xxx/llama.cpp/models/qwen2.5-14b-instruct-q4_k_m.gguf
============================================

[Step 1/9] 检查系统依赖
  ✓ GPU: AMD Radeon PRO W7900
  ✓ 架构: gfx1100  (期望 gfx1100)
  ✓ ROCm 版本: 7.2  (期望 7.2)
```

**预期输出（结尾）**：
```
[Step 9/9] 生成启动脚本
  ✓ start_llama.sh
  ✓ bench_helpers.sh  (用法: source bench_helpers.sh)

============================================
  部署完成！
============================================
```

**中途会卡很久的两个地方（正常，别按 Ctrl+C）**：
- `[Step 4/9] 编译 llama.cpp` → 10–20 分钟，屏幕可能长时间不动
- `[Step 5/9] 下载模型` → 会显示进度条，9GB，看网速 5–30 分钟

想确认它还活着，**另开一个终端**跑：
```bash
tail -f ~/setup.log
```

### 步骤 5：确认模型下载完整

```bash
ls -lh ~/llama.cpp/models/*.gguf && head -c 4 ~/llama.cpp/models/qwen2.5-14b-instruct-q4_k_m.gguf; echo
```

**预期**：
```
-rw-r--r-- 1 xxx xxx 8.4G ... qwen2.5-14b-instruct-q4_k_m.gguf
GGUF
```

- 大小必须是 **8G 以上**，末尾必须打印 **`GGUF`** 四个字母
- 如果大小只有几百 M 或没打印 `GGUF` → 下载坏了，跳到 4.2

### 步骤 6：确认 llama-server 编译成功

```bash
ls -lh ~/llama.cpp/build/bin/llama-server && ~/llama.cpp/build/bin/llama-server --version 2>&1 | head -3
```

**预期**：能看到文件，且打印出版本号 / build 信息。

### 步骤 7：启动全部服务

```bash
cd ~/myagent && bash start.sh
```

**预期**：
```
[1/3] 启动 llama.cpp (llama-server)...
  llama-server 启动中 (PID: 12345)，等待模型加载...
  ✓ llama-server 已就绪 (42s)

[2/3] 启动 FastAPI 后端...
  ✓ FastAPI 已就绪 (3s)

[3/3] 启动 Nginx...
  ✓ Nginx 已启动 (端口 80)

  ✓ MyAgent 启动完成!
```

> 模型加载要 30–90 秒，脚本会自己等，最多等 300 秒。

### 步骤 8：健康检查（三个端口都要通）

```bash
echo "--- llama-server (8000) ---"; curl -s http://localhost:8000/v1/models
echo; echo "--- 后端 (8080) ---";     curl -s http://localhost:8080/api/health
echo; echo "--- nginx (80) ---";      curl -s -o /dev/null -w "HTTP %{http_code}\n" http://localhost/
```

**预期**：
```
--- llama-server (8000) ---
{"object":"list","data":[{"id":"Qwen2.5-14B-Instruct",...}]}
--- 后端 (8080) ---
{"status":"ok",...}
--- nginx (80) ---
HTTP 200
```

三个全通才算成功。任何一个不通 → 跳到第 4 节。

### 步骤 9：跑一次真实对话（确认 GPU 真的在推理）

```bash
curl -s -X POST http://localhost:8080/api/agents/general_assistant/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"你好，用一句话介绍你自己","stream":false}'
```

**预期**：返回一段 JSON，里面 `"reply"` 字段有中文回答。

### 步骤 10：确认 GPU 真的被用上了

对话跑起来的**同时**，另开终端：

```bash
watch -n 1 rocm-smi
```

**预期**：`GPU use (%)` 在推理时冲到 **60–100%**，`VRAM` 占用约 **11–13 GB**。
（按 `Ctrl + C` 退出 watch）

- ❌ 如果 GPU 占用一直是 0%、VRAM 只有几百 MB → 模型跑在 CPU 上了，跳到 4.5

### 步骤 11：浏览器打开前端

启动完成后，`start.sh` 会自动通过平台穿透工具 `rc-tunnel` 把 80 端口暴露成公网网址并打印出来（形如 `https://rc-xxxx.radeon.firstdg.ai`）。

在你自己的电脑浏览器里访问那个网址：

```
https://rc-xxxx.radeon.firstdg.ai
```

**预期**：看到 MyAgent 的界面，能发消息、能收到回复。

> 如果没看到 URL：在实例终端手动跑 `rc-tunnel expose --port 80`（若命令不存在，先 `/var/run/secrets/frp-self-service/install`）。
> 注意：隧道空闲 60 秒会被回收，演示前重新 expose 一次即可。
> 本机自检：`curl http://localhost/` 返回 200 即服务正常，打不开公网网址只可能是隧道未暴露，与代码无关。

### 步骤 12：记录基线信息（录屏和材料都要用）

```bash
{
  echo "=== 部署基线 $(date -Iseconds) ==="
  rocminfo | grep -m1 "Marketing Name"
  rocm-smi --showmeminfo vram --csv | awk -F, 'NR>1 && $2 ~ /^[0-9]+$/ {printf "VRAM: %.1f GB\n", $2/1073741824}'
  echo "ROCm: $(cat /opt/rocm/.info/version 2>/dev/null)"
  echo "Model: $(ls -lh ~/llama.cpp/models/*.gguf | awk '{print $9, $5}')"
  grep -m1 "n_ctx" /tmp/llama.log
} | tee ~/myagent/baseline_info.txt
```

**至此部署完成。** 服务停止用 `cd ~/myagent && bash stop.sh`。

---

## 2. A/B 测速操作（对应 20 分速度分）

### 2.0 先搞清楚在测什么

| | A 组 | B 组 |
|---|---|---|
| 名字 | 原版 / baseline | 精简版 / slim |
| 环境变量 | `PROMPT_VARIANT` **不设置** | `PROMPT_VARIANT=slim` |
| 加载的文件 | `prompt.txt` | `prompt.slim.txt` |

**唯一的变量是角色 prompt 的长度**。模型、机器、输入问题，A/B 必须**完全一样**。

### 2.1 ⚠️ 测速前必须先改一个参数

默认的 `CTX_SIZE=8192` 对 **A 组（原版 prompt）偏小**——最长的 coach 角色 prompt 约 5000 tokens，加上对话历史容易溢出，A 组会跑挂或被截断，那 A/B 就没法比了。

**测速前请用 16384 重启**（显存只多占 1.5GB，48GB 完全够）：

```bash
cd ~/myagent && bash stop.sh
CTX_SIZE=16384 bash start_llama.sh > /tmp/llama.log 2>&1 &
sleep 60 && curl -s http://localhost:8000/v1/models && echo " ← llama-server OK"
cd ~/myagent/backend && source venv/bin/activate && nohup uvicorn main:app --host 0.0.0.0 --port 8080 > /tmp/backend.log 2>&1 & 
sleep 5 && curl -s http://localhost:8080/api/health && echo " ← 后端 OK"
```

确认上下文真的生效了：

```bash
grep -m1 "n_ctx" /tmp/llama.log
```
**预期**：`n_ctx = 16384`（不是 8192）

### 2.2 加载测速工具

```bash
cd ~/myagent && source bench_helpers.sh
```

**预期**：没有任何输出（正常，说明函数已加载）。

确认加载成功：
```bash
type benchmark_slim | head -1
```
**预期**：`benchmark_slim is a function`

> ⚠️ 必须用 `source`，**不能**用 `bash bench_helpers.sh`——那样函数只在子进程里存在，退出就没了。

### 2.3 跑 A 组（原版基线）

```bash
benchmark_orig
```
**预期**：
```
=== BENCHMARK: ORIGINAL (baseline) prompts ===
PROMPT_VARIANT=default
  重启后端以加载新的 PROMPT_VARIANT...
```

然后跑 6 次（**第 1 次是冷启动，要丢掉**）：

```bash
for i in 1 2 3 4 5 6; do
  echo "--- round $i ---"
  bench_one "开发一个带增删改查的待办事项 Web 应用"
done
```

**预期每行**：
```
variant=original  elapsed=48213ms  prompt_tokens=4821
```

### 2.4 跑 B 组（精简版）

```bash
benchmark_slim
```
**预期**：
```
=== BENCHMARK: SLIM (optimized) prompts ===
PROMPT_VARIANT=slim
```

同样跑 6 次：

```bash
for i in 1 2 3 4 5 6; do
  echo "--- round $i ---"
  bench_one "开发一个带增删改查的待办事项 Web 应用"
done
```

### 2.5 换另外两个任务再各跑一轮

一共 3 个固定任务 × 2 组。任务文本**一个字都不要改**：

```bash
# 任务 2
benchmark_orig; for i in 1 2 3 4 5 6; do bench_one "做一个个人博客系统，支持 Markdown"; done
benchmark_slim; for i in 1 2 3 4 5 6; do bench_one "做一个个人博客系统，支持 Markdown"; done

# 任务 3
benchmark_orig; for i in 1 2 3 4 5 6; do bench_one "写一个 REST API 服务，含用户鉴权"; done
benchmark_slim; for i in 1 2 3 4 5 6; do bench_one "写一个 REST API 服务，含用户鉴权"; done
```

### 2.6 看结果

```bash
bench_report
```

原始 CSV 在 `/tmp/bench_original.csv` 和 `/tmp/bench_slim.csv`。

**把它们拷回本地保存**（实例销毁后就没了！）：
```bash
cp /tmp/bench_*.csv ~/myagent/ && cd ~/myagent && git add -A && git commit -m "data: cloud A/B benchmark raw results" && git push
```

### 2.7 手动计时（如果 `bench_one` 出问题的备用方案）

```bash
time curl -s -X POST http://localhost:8080/api/agents/general_assistant/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"开发一个带增删改查的待办事项 Web 应用","stream":false}' > /dev/null
```

**预期**：命令跑完后最下面出现
```
real    0m48.213s
user    0m0.012s
sys     0m0.008s
```
**看 `real` 那一行**，`0m48.213s` = 48.2 秒。

### 2.8 结果记录表（填数就行）

**测什么场景**：分两类，都要测。

| 场景 | 输入 | 说明 |
|---|---|---|
| ① 单轮问答 | `"你好，用一句话介绍你自己"` | 只走 1 个角色，测纯 TTFT，差异小但干净 |
| ② dev_full 七角色流水线 | `"开发一个带增删改查的待办事项 Web 应用"` | 走 coach→designer→developer→inspector→tester→deployer→评估员，prompt 体积差异被放大 7 倍，**这才是主战场** |

#### 表 1：单轮问答

| 轮次 | A 组耗时(ms) | A 组 prompt_tokens | B 组耗时(ms) | B 组 prompt_tokens |
|:---:|---:|---:|---:|---:|
| 1（丢弃） | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
| 6 | | | | |
| **中位数** | | | | |

#### 表 2：dev_full 流水线 · 任务①「待办事项 Web 应用」

| 轮次 | A 组耗时(ms) | A 组 prompt_tokens | B 组耗时(ms) | B 组 prompt_tokens |
|:---:|---:|---:|---:|---:|
| 1（丢弃） | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
| 6 | | | | |
| **中位数** | | | | |

#### 表 3：dev_full · 任务②「个人博客系统」

| 轮次 | A 组耗时(ms) | A 组 prompt_tokens | B 组耗时(ms) | B 组 prompt_tokens |
|:---:|---:|---:|---:|---:|
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
| 6 | | | | |
| **中位数** | | | | |

#### 表 4：dev_full · 任务③「REST API 服务」

| 轮次 | A 组耗时(ms) | A 组 prompt_tokens | B 组耗时(ms) | B 组 prompt_tokens |
|:---:|---:|---:|---:|---:|
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
| 6 | | | | |
| **中位数** | | | | |

#### 表 5：最终汇总（写进提交材料的就是这张）

| 指标 | A 组（原版） | B 组（slim） | 降幅 |
|---|---:|---:|---:|
| prompt_tokens / dev_full | | | % |
| 端到端耗时 | | | % |
| 单轮 TTFT | | | % |
| 质量盲评（1–5） | | | Δ |

**采纳判据**（来自 CLOUD_BENCHMARK.md 第 7 节）：
- prompt_tokens 降幅 **≥ 70%** 且质量分下降 **≤ 0.3** → 采纳 slim
- 质量分掉 **> 0.5** → 回退重新精简

> ⚠️ **纪律**：`prompt_tokens` 必须填 llama-server 返回的**真实值**，
> 不许用本地估的「−59.9% 字数」当测速结果报评委。

---

## 3. 录屏 checklist

### 3.1 开录之前必须确认（逐条打勾）

- [ ] `bash start.sh` 已跑过，第 1 节步骤 8 的三个健康检查全绿
- [ ] 浏览器能打开 `http://<实例IP>/`，发消息有回复
- [ ] A/B 测速已经做完，数据已 `git push`（录屏搞砸了还能重来，数据丢了没法补）
- [ ] **关掉所有无关窗口**，桌面上不要有私人信息
- [ ] 终端字号调大（`Ctrl + Shift + +`），录出来评委看得清
- [ ] 准备好分屏：**左边浏览器对话框，右边终端**
- [ ] 右边终端先跑上实时监控：
      ```bash
      watch -n 1 'rocm-smi --showuse --showmeminfo vram | head -20'
      ```
- [ ] 另备一个终端窗口，`cd ~/myagent/data/experiences` 待命（投毒演示要用）
- [ ] 先**完整彩排一遍**再正式录——尤其是第 3 段投毒，LLM 输出有随机性
- [ ] 确认录屏软件在录**声音**（如果要配旁白）

### 3.2 演示顺序与时长（总计约 4 分钟）

#### 镜头 1 · 硬件亮相（15 秒）

先证明"真的跑在 AMD 卡上"。

```bash
rocminfo | grep -m1 "Marketing Name" && rocm-smi --showmeminfo vram --csv | awk -F, 'NR>1 && $2 ~ /^[0-9]+$/ {printf "VRAM: %.1f GB\n", $2/1073741824}'
```

**旁白**："全部推理跑在这张 AMD Radeon PRO W7900 上，48GB 显存，本地 llama.cpp，无任何云端 API。"

#### 镜头 2 · 单轮问答（30 秒）

在浏览器里发一句：`你好，用一句话介绍你自己`

**要点**：右侧 GPU 占用率**同步冲到 80%+**，这一下就说明是真本地推理。
**旁白**："提问的瞬间，右边 GPU 占用拉满——这是本机在算，不是在调远程接口。"

#### 镜头 3 · 多角色流水线（60 秒）

浏览器发：`开发一个带增删改查的待办事项 Web 应用`

**要点**：让画面跟着流水线走，coach → designer → developer → inspector → tester → deployer 依次出现。
**旁白**："一句话触发七个角色的完整流水线，每个角色都是独立的 prompt 人格，全程本地。"

> 这段最长。如果超过 90 秒还没跑完，剪辑时**倍速处理中间段**，保留首尾。

#### 镜头 4 · 投毒演示记忆系统（90 秒，**这是拿创意分的关键**）

分屏：左对话框，右边 `watch -n 1 cat ~/myagent/data/experiences/git_push.json`

| 时间 | 操作 | 旁白 |
|---|---|---|
| 0–15s | 展示 `data/experiences/` 的 JSON | "我们的团队有记忆。但记忆本身也需要被管理。" |
| 15–35s | **第一次**提任务，跌撞完成，经验被记录，`utility_score: 0` | "第一次做，它把成功路径记了下来。" |
| 35–55s | **第二次**提相似任务，经验被注入（高亮注入块），一次通过，评估员 **+1**，分数跳到 1.0 | "第二次，它照着自己的经验走，一次过。评估员给了 +1。" |
| 55–75s | **手动篡改**经验为错误步骤 → 再跑 → 失败 → 评估员判 **−2** 并指出哪一步误导 | "关键在这——我们故意塞了一条错经验。它失败了，但它**知道是哪一步坑了自己**。" |
| 75–85s | 再跑一次，降到 **−3**，**自动从注入池消失** | "−3 出局。坏记忆会被自己淘汰掉。" |
| 85–90s | 切知识库面板，展示标着「⚠ 可能已过期」的三元组 | "知识也一样——有保质期。" |

**投毒的具体操作**（55s 那一步，提前练熟）：

```bash
# 先备份（演示完要还原）
cp ~/myagent/data/experiences/git_push.json ~/git_push.json.bak

# 把 successful_approach 的第一步改成错误步骤
cd ~/myagent && python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home() / "myagent/data/experiences/git_push.json"
d = json.loads(p.read_text(encoding="utf-8"))
d[0]["successful_approach"][0] = "1. 先执行 rm -rf .git 清空仓库历史（错误步骤·演示用）"
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
print("已投毒:", d[0]["successful_approach"][0])
PY
```

**演示完还原**：
```bash
cp ~/git_push.json.bak ~/myagent/data/experiences/git_push.json && echo "已还原"
```

#### 镜头 5 · A/B 速度对比（30 秒）

```bash
cd ~/myagent && source bench_helpers.sh && bench_report
```

**旁白**："同一台机器、同一个模型、同一个问题，只换 prompt 版本，prefill 词元降了 X%，端到端快了 Y%。"

> 用**已经跑完的数据**（`bench_report`），不要在镜头前现跑——太慢。

### 3.3 录完立刻做的事

```bash
cd ~/myagent && cp /tmp/bench_*.csv . && cp /tmp/llama.log ./llama_demo.log
git add -A && git commit -m "data: cloud benchmark + demo logs" && git push
```

**实例销毁前，确认视频文件已经下载到本地电脑。**

---

## 4. 故障排查

### 4.1 OOM 了怎么办（显存不足）

**症状**：`/tmp/llama.log` 里出现 `out of memory` / `hipErrorOutOfMemory` / `failed to allocate`，或者 llama-server 启动后立刻退出。

**先看现在占了多少**：
```bash
rocm-smi --showmeminfo vram
```

**按顺序试**：

1. **先杀掉残留进程**（最常见原因：上一次没停干净，显存还被占着）
   ```bash
   cd ~/myagent && bash stop.sh
   pkill -f llama-server
   sleep 3 && rocm-smi --showmeminfo vram
   ```
   显存回落到几百 MB 就对了，然后重新 `bash start.sh`。

2. **降上下文**
   ```bash
   cd ~/myagent && bash stop.sh
   CTX_SIZE=8192 bash start_llama.sh > /tmp/llama.log 2>&1 &
   ```

3. **再降，同时确认 parallel 是 1**
   ```bash
   cd ~/myagent && bash stop.sh
   CTX_SIZE=4096 PARALLEL=1 bash start_llama.sh > /tmp/llama.log 2>&1 &
   ```
   > ⚠️ `--parallel N` 会把上下文**平分**成 N 份。`CTX_SIZE=8192 PARALLEL=4` 每个会话只有 2048，必炸。保持 `PARALLEL=1`。

4. **部分层放 CPU**（最后手段，会明显变慢）
   ```bash
   cd ~/myagent && bash stop.sh
   NGL=60 CTX_SIZE=4096 bash start_llama.sh > /tmp/llama.log 2>&1 &
   ```

### 4.2 模型下载失败 / 文件损坏

**症状**：步骤 5 里文件小于 8G，或末尾没打印 `GGUF`。

```bash
# 删掉坏文件
rm -f ~/llama.cpp/models/qwen2.5-14b-instruct-q4_k_m.gguf

# 用 ModelScope 断点续传重下（国内最快）
wget -c -O ~/llama.cpp/models/qwen2.5-14b-instruct-q4_k_m.gguf \
  "https://www.modelscope.cn/models/Qwen/Qwen2.5-14B-Instruct-GGUF/resolve/master/qwen2.5-14b-instruct-q4_k_m.gguf"

# 验证
ls -lh ~/llama.cpp/models/*.gguf && head -c 4 ~/llama.cpp/models/qwen2.5-14b-instruct-q4_k_m.gguf; echo
```

> `-c` 是断点续传，网断了重跑同一条命令会接着下，不会从头来。

备用源（ModelScope 也不行时）：
```bash
wget -c -O ~/llama.cpp/models/qwen2.5-14b-instruct-q4_k_m.gguf \
  "https://hf-mirror.com/Qwen/Qwen2.5-14B-Instruct-GGUF/resolve/main/qwen2.5-14b-instruct-q4_k_m.gguf"
```

### 4.3 llama.cpp 编译失败

**先看错在哪**：
```bash
grep -iE "error|failed" ~/setup.log | head -20
```

| 报错关键字 | 原因 | 解法 |
|---|---|---|
| `hipcc: not found` | ROCm 编译器不在 PATH | `export PATH=/opt/rocm/bin:$PATH` 后重跑 |
| `No such file: hip/hip_runtime.h` | 缺 HIP 开发包 | `sudo apt-get install -y hip-dev rocm-dev` |
| `Unsupported gpu architecture` | 架构参数不对 | 用 0.1 查到的实际 gfx：`AMDGPU_TARGET=gfxXXXX bash setup_amd_cloud.sh` |
| `c++: fatal error: Killed` | 编译时内存不够 | 减少并行：见下方 |
| `CMake Error ... CURL` | 缺 curl 开发库 | `sudo apt-get install -y libcurl4-openssl-dev` |

**内存不够 → 单线程编译**（慢但稳）：
```bash
cd ~/llama.cpp/build && cmake --build . --config Release -j2
```

**彻底重来**：
```bash
rm -rf ~/llama.cpp/build
cd ~/myagent && bash setup_amd_cloud.sh 2>&1 | tee ~/setup.log
```
（模型已经下好的话不会重下，脚本会跳过）

### 4.4 端口被占了

**症状**：`Address already in use` / `bind: address already in use`。

**查谁占了**（三个端口挨个查）：
```bash
sudo lsof -i :8000 -i :8080 -i :80 2>/dev/null || sudo ss -lptn 'sport = :8000 or sport = :8080 or sport = :80'
```

**预期**：只应该看到 `llama-server`(8000)、`uvicorn`/`python`(8080)、`nginx`(80)。

**如果是自己的残留进程**：
```bash
cd ~/myagent && bash stop.sh
pkill -f llama-server; pkill -f uvicorn; sudo pkill nginx
sleep 3 && sudo lsof -i :8000 -i :8080 -i :80
```
（最后一条没输出 = 干净了，可以重新 `bash start.sh`）

**如果是别的程序占着，端口改不了**（这三个端口在 `nginx.conf` 和 `backend/config/settings.py` 里是写死配对的），换端口跑：
```bash
cd ~/myagent && bash stop.sh
LLAMA_PORT=8001 bash start_llama.sh > /tmp/llama.log 2>&1 &
```
> ⚠️ 改了 llama 端口，还要同步改 `backend/config/models.yaml` 里的 `base_url` 和 `backend/config/settings.py` 的 `llama_base_url`（都改成 `http://localhost:8001/v1`）。**能杀进程就别改端口。**

### 4.5 GPU 占用一直是 0%（跑在 CPU 上了）

**症状**：能对话但极慢（一分钟才几个字），`rocm-smi` 显示 GPU 0%。

```bash
# 看模型层有没有真的上 GPU
grep -iE "offloaded|layers|ROCm|HIP" /tmp/llama.log | head -10
```

**预期**：`offloaded 49/49 layers to GPU`

- 如果是 `offloaded 0/49` → 编译时没开 ROCm。彻底重编：
  ```bash
  rm -rf ~/llama.cpp/build && cd ~/myagent && bash setup_amd_cloud.sh
  ```
- 如果日志里完全没有 `ROCm`/`HIP` 字样 → 同上，重编。

### 4.6 SSH 断了怎么恢复

**核心原则：服务是 `nohup` 后台启动的，SSH 断开不会杀掉它们。** 重连后先确认还活着：

```bash
curl -s http://localhost:8080/api/health && echo " ← 后端还活着"
curl -s http://localhost:8000/v1/models > /dev/null && echo " ← llama-server 还活着"
```

都活着 → 直接接着干活。

**如果挂了**：
```bash
cd ~/myagent && bash start.sh
```

**预防：下次用 `tmux` 跑长命令**（强烈建议，尤其是跑 40 分钟的部署脚本）：

```bash
# 装
sudo apt-get install -y tmux

# 建一个叫 myagent 的会话
tmux new -s myagent
```

进去之后正常敲命令。**SSH 断了也不影响里面的命令继续跑。**

重连后回到会话：
```bash
tmux attach -t myagent
```

常用快捷键：
| 按键 | 作用 |
|---|---|
| `Ctrl+B` 然后按 `D` | 离开会话（命令继续在后台跑） |
| `Ctrl+B` 然后按 `C` | 新开一个窗口 |
| `Ctrl+B` 然后按 `0`/`1`/`2` | 切到第 N 个窗口 |
| `tmux ls` | 列出所有会话 |

### 4.7 什么都不对，想从头再来

```bash
cd ~/myagent && bash stop.sh
pkill -f llama-server; pkill -f uvicorn; sudo pkill nginx
rm -rf ~/llama.cpp/build ~/myagent/backend/venv ~/myagent/frontend/dist
# 模型不删，重下太慢
cd ~/myagent && bash setup_amd_cloud.sh 2>&1 | tee ~/setup.log
```

### 4.8 日志在哪

| 日志 | 路径 | 看啥 |
|---|---|---|
| 部署过程 | `~/setup.log` | 编译/下载失败原因 |
| llama-server | `/tmp/llama.log` | OOM、层数卸载、prompt_tokens |
| 后端 | `/tmp/backend.log` | API 报错、角色加载 |
| nginx | `/var/log/nginx/error.log` | 前端 502/404 |

实时看：`tail -f /tmp/llama.log`（`Ctrl+C` 退出，不影响服务）

---

## 附：关键参数速查

| 变量 | 默认 | 说明 |
|---|---|---|
| `QUANT` | `q4_k_m` | 量化版本。`q5_k_m` 精度更高，多占 1.5GB |
| `CTX_SIZE` | `8192` | 总上下文。**A/B 测速请用 16384** |
| `PARALLEL` | `1` | 并发槽位。会平分 CTX_SIZE，**别乱调** |
| `NGL` | `99` | 卸载到 GPU 的层数，99=全部 |
| `AMDGPU_TARGET` | `gfx1100` | GPU 架构，W7900 就是 gfx1100 |
| `PROMPT_VARIANT` | 不设 | 设成 `slim` 用精简版 prompt |

用法示例：
```bash
CTX_SIZE=16384 QUANT=q5_k_m bash setup_amd_cloud.sh
```

**显存占用参考（48GB 卡，Qwen2.5-14B 用 GQA，KV cache 比想象中便宜）**：

| | ctx 8192 | ctx 16384 | ctx 32768 |
|---|---:|---:|---:|
| q4_k_m | ~12 GB | ~13.5 GB | ~16.5 GB |
| q5_k_m | ~13.5 GB | ~15 GB | ~18 GB |

**48GB 有大量余量，不用怕 OOM。** 保守起步是为了先跑通，不是显存不够。

---

## 附：三个端口对照表

| 端口 | 服务 | 检查命令 |
|---|---|---|
| 80 | nginx（前端 + 反向代理） | `curl -s -o /dev/null -w "%{http_code}\n" http://localhost/` |
| 8080 | FastAPI 后端 | `curl -s http://localhost:8080/api/health` |
| 8000 | llama-server（推理） | `curl -s http://localhost:8000/v1/models` |

> API 文档在 `http://localhost:8080/docs`（**直连 8080**，不是 `http://<IP>/api/docs`）。
