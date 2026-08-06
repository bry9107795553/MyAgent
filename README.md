# MyAgent — Private AI Agent Platform with AMD Radeon GPU + ROCm

**Track 2: Development & Local Deployment of Private AI Agents**
**2026 AMD AI DevMaster Hackathon**

A fully local, privacy-first AI agent platform powered by AMD Radeon GPUs and ROCm. All inference runs on local GPU via llama.cpp — zero cloud dependency, works offline, and no user data ever leaves the machine.

---

## Application Scenarios

MyAgent is designed for users who need a capable AI assistant without sacrificing data privacy:

- **Software Development**: Full development lifecycle from requirements analysis to deployment, orchestrated by 19 specialized AI roles (Coach, Designer, Developer, Inspector, Tester, Deployer)
- **Knowledge Work**: Research reports, document writing, translation, and data analysis with multi-role quality assurance
- **Personal Productivity**: Schedule management, creative brainstorming, code review, and file organization
- **Offline-First Environments**: Fully functional without internet — ideal for air-gapped or low-connectivity scenarios

**Target Users**: Developers, researchers, writers, and privacy-conscious individuals who need GPU-accelerated AI assistance on their own hardware.

---

## Agent Architecture

MyAgent uses a **4-layer hierarchical architecture** with a central orchestrator:

```
+---------------------------------------------------+
|  L4  UI Layer                                      |
|  Vue 3 + GridStack.js + Universal Module Renderer   |
|  Chat View · Workbench · Skin Marketplace          |
+---------------------------------------------------+
|  L3  Agent Configuration Layer (Directory-Isolated) |
|  data/agents/{agent_id}/                           |
|  config.yaml → master personality, role pool, tools|
|  prompt.txt  → custom system prompt                |
|  knowledge/  → knowledge base · ui_layout.json     |
+---------------------------------------------------+
|  L2  Orchestration Layer (Always Running)           |
|  FastAPI + WebSocket + Dispatcher + 19 Roles        |
|  + 4-Level Progressive Memory + Shared Blackboard  |
|  Master Dispatch · Role Collaboration · Agent Gen  |
+---------------------------------------------------+
|  L1  Foundation Layer                               |
|  llama.cpp + ROCm + Nginx                          |
|  Local Inference · GPU Acceleration · Single Port  |
+---------------------------------------------------+
```

### 19-Role System

The Master role acts as a **firewall and dispatcher** — all requests go through it, and roles never communicate directly.

18 roles are declared in `data/role_pool.json` and dispatched by Master; the Secretary is an always-on background role implemented in `backend/core/agent/orchestrator.py` (it observes every turn rather than being dispatched). 18 + 1 = 19.

The **GPU column is the affinity tag** (`gpu_affinity` in `role_pool.json`) used for optional multi-GPU scale-out. In the default single-GPU deployment all roles run on the one physical GPU — see [Single-GPU Deployment](#2-single-gpu-deployment-default--as-demonstrated). The **Model column reflects the multi-GPU plan** in `role_pool.json → gpu_allocation`; it is metadata only. On a single card every role is served by the one loaded model (`gateway._get_model_name()` always returns `settings.llama_model`) — in the demonstrated deployment this is **Qwen3-30B-A3B MoE**.

| Group (`category`) | Role (`id`) | GPU Affinity | Model (multi-GPU plan) | Capability |
|-------|------|--------------|-------------|------------|
| general | `master` | gpu0 | Qwen2.5-14B | Dispatch / Firewall / Summarization |
| general | `knowledge_retriever` | gpu1 | Qwen2.5-7B | Knowledge-base retrieval |
| general | `writer` | gpu0 | Qwen2.5-14B | Reports / Emails / Copywriting |
| general | `quality_checker` | gpu2 | Qwen2.5-7B | Fact-checking / Logic Validation |
| general | `scheduler` | gpu1 | Qwen2.5-7B | Time Management |
| general | `creative` | gpu0 | Qwen2.5-14B | Brainstorming / Insight Extraction |
| general | `translator` | gpu1 | Qwen2.5-7B | Multi-language Translation |
| general | `visual_analyzer` | gpu1 | Qwen2.5-VL-7B | Image Analysis (Multimodal) — see note |
| general | `experience_evaluator` | gpu2 | Qwen2.5-7B | Experience Scoring / Memory Pruning |
| dev | `coach` | gpu0 | Qwen2.5-14B | Requirements / Dev Team Orchestration |
| dev | `designer` | gpu0 | Qwen2.5-14B | Design System / Multi-page Mockups |
| dev | `developer` | gpu0 | Qwen2.5-14B | Code Implementation |
| dev | `inspector` | gpu2 | Qwen2.5-7B | Architecture Review / Code Audit |
| dev | `tester` | gpu2 | Qwen2.5-7B | Type Checking / Linting / Unit Tests |
| dev | `deployer` | gpu2 | Qwen2.5-7B | Build / Deploy / Rollback |
| dev | `handoff_receiver` | gpu0 | Qwen2.5-14B | Existing-project Takeover / Impact Assessment |
| logistics | `cleaner` | gpu2 | Qwen2.5-7B | File System Cleanup |
| management | `hr_manager` | gpu2 | Qwen2.5-7B | Role Audit / Prompt Optimization |
| *(not in role pool)* | `Secretary` *(always-on)* | — | current model | Turn Recording / Experience Injection / Summarization |

> **Note on Visual Analyzer**: multimodal analysis requires the Qwen2.5-VL-7B weights, which are only loaded in the multi-GPU configuration. On the single-GPU deployment the role remains dispatchable and answers as a text role, but true image understanding is unavailable — this degradation is declared in `role_pool.json → single_gpu_fallback.degraded_roles` and warned about at startup rather than failing silently.

### 10 Preset Workgroups

Defined as one JSON file per workgroup under `data/workgroups/`. Trigger keywords are **Chinese** (the dispatcher matches Chinese input); English glosses are given below for readability. Pipelines are listed exactly as stored — a role appearing twice in a row is a genuine multi-step assignment, not a typo.

| Workgroup | Trigger Keywords (Chinese, sample) | Pipeline |
|-----------|-----------------|----------|
| `dev_full` | 开发 / 做项目 / 写应用 / 建网站 | coach → coach → designer → coach → developer → inspector → tester → deployer → cleaner |
| `dev_modification` | 修改 / 改代码 / 修bug / 重构 / 加功能 | handoff_receiver → handoff_receiver → inspector → handoff_receiver → designer → developer → deployer → developer → inspector → tester → deployer → cleaner |
| `dev_code_review` | 审查代码 / 巡检 / 代码审查 | inspector → inspector → developer → tester → cleaner |
| `dev_design_only` | 设计 / 出样图 / UI设计 / 做原型 | coach → designer → designer → designer → quality_checker |
| `dev_tech_debt` | 技术债 / 还债 / 重构 / 清理代码 | inspector → inspector → developer → tester → cleaner → inspector |
| `report_writing` | 写报告 / 写分析 / 写总结 / 出报告 | knowledge_retriever → writer → quality_checker → writer |
| `research_investigation` | 调研 / 对比 / 选型 / 竞品分析 | knowledge_retriever → creative → quality_checker → knowledge_retriever |
| `translation_task` | 翻译 / translate / 中译英 / 本地化 | translator → quality_checker → translator |
| `schedule_planning` | 安排日程 / 规划时间 / 提醒 / 排期 | scheduler → creative → quality_checker → scheduler |
| `visual_analysis_task` | 看图 / 分析图片 / 截图分析 / 分析UI | visual_analyzer → writer |

Development pipelines additionally append an **Experience Evaluator** step at completion — dispatcher rule `experience_eval_hook`, implemented in `backend/core/role/master.py::_apply_experience_eval_hook()` — which scores the experiences injected during the run and prunes stale memory.

---

## Core Capabilities

### 1. Natural Language Agent Generation
Describe your needs in plain language, and the AI auto-generates a complete Agent configuration (personality, role pool, tools, knowledge base). Zero coding required.

### 2. 4-Level Progressive Memory

Implemented in `backend/core/memory/`:

| Level | Module | Content | Promotion trigger (`working_memory.py`) |
|---|---|---|---|
| L0 (Raw / hot) | `working_memory.py` + `archive.py` | Sliding window of live messages; every message also append-only archived | > 20 turns **or** > 4000 est. tokens → compress to L1 |
| L1 (Light summary) | `working_memory.py` / `compressor.py` | Incremental summaries injected back into context | > 5 L1 summaries → compress to L2 |
| L2 (Dense summary) | `session_memory.py` | Cross-session semantic compression for long-term recall | > 10 L2 summaries → entity extraction to L3 |
| L3 (Knowledge triples) | `knowledge_base.py` | Entity-relation triples + entity index + semantic retrieval | — |

Supporting modules: `store.py` (atomic JSON I/O + crash recovery), `compressor.py` (score → archive → LLM compress → entity extraction), `blackboard.py` (shared blackboard with publish/subscribe access control and Master firewall routing), `exporter.py` (conversation export with desensitization).

No truncation — only semantic compression. Raw messages are archived **before** compression, and the archive is append-only.

### 3. Dynamic Dispatch System
Keyword matching (`data/dispatcher_config.json`) + dynamic workgroup assembly. On the default single-GPU deployment roles execute sequentially on one llama-server; the same GPU-affinity metadata enables parallel scheduling across multiple GPUs when more than one card is available.

### 4. Tool Calling (real disk side effects)

Five tools are registered at import time in `backend/core/tools/builtin/__init__.py` and exposed to the model in OpenAI function-calling format:

| Tool | Implementation | Behaviour | Default (`AgentTools`) |
|---|---|---|---|
| `file_read` | `file_tools.py::FileReadTool` | Reads a real file; relative paths resolved against `settings.project_root` | **on** |
| `file_write` | `file_tools.py::FileWriteTool` | Writes/appends a real file; refuses paths outside the project root | off |
| `file_list` | `file_tools.py::FileListTool` | Lists a real directory with glob filtering | on — shares the `file_read` switch (`config_key = "file_read"`) |
| `code_exec` | `code_tools.py::CodeExecTool` | Runs Python in a subprocess; default timeout 10 s, max 30 s, output capped at 10 000 chars | off |
| `web_search` | `search_tools.py::WebSearchTool` | **Real local retrieval** — queries the L3 knowledge graph (`core/memory/knowledge_base`) plus L1/L2 session memory and returns ranked entity-relation triples. No network egress; the project stays fully offline. Enable per-agent via `AgentTools.web_search`. | off (default) |

Per-agent switches live in `backend/core/agent/agent_schemas.py::AgentTools`. File tools genuinely touch disk, so their output is verifiable and auditable. `web_search` now performs real local knowledge retrieval (no network), closing the earlier placeholder gap while keeping the project fully offline.

### 5. Project State Tracking
Cross-session project awareness via `PROJECT_STATUS.md` (`backend/core/project/project_status.py`). The Coach role maintains structured progress tracking, and the system auto-restores context after restart.

### 6. Directory-Level Isolation
Agents and roles are independent folders. Add/remove = add/remove folders. Watchdog-based hot-reload (`backend/core/agent/lifecycle.py`, `registry.py`) — no system restart required.

### 7. Secretary Experience System
Records successful operation patterns across sessions (`backend/core/agent/orchestrator.py::Secretary`). When the same task type is encountered, relevant experiences are injected into LLM context — preventing repeated trial-and-error.

---

## ROCm / AMD GPU Optimization

### 1. llama.cpp with ROCm/HIP backend

`setup_amd_cloud.sh` (Step 4/9) first tries the **official prebuilt ROCm binary** and falls back to a source build:

```bash
# Preferred: official prebuilt, ROCm 7.2 / Ubuntu x64 (~124 MB)
LLAMA_PREBUILT_TAG=b10267
https://github.com/ggml-org/llama.cpp/releases/download/b10267/llama-b10267-bin-ubuntu-rocm-7.2-x64.tar.gz

# Fallback: build from source, single-architecture to shorten compile time
cmake .. -DGGML_HIP=ON \
    -DAMDGPU_TARGETS=gfx1100 \
    -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release -j$(nproc)
```

Matrix operations (attention, FFN, embedding) are executed on the AMD GPU through the HIP backend.

### 2. Single-GPU Deployment (Default — as demonstrated)

**The shipped configuration targets a single AMD GPU.** Our reference deployment — and everything shown in the demo video — runs on one **Radeon PRO W7900 (48GB, gfx1100, ROCm 7.2)** on a Radeon Cloud instance, serving all 19 roles from a single `llama-server`. This is what `start.sh` launches:

```bash
# start.sh — one server, one GPU, all roles
"$LLAMA_SERVER" -m qwen2.5-14b-instruct-q4_k_m.gguf \
    -a "Qwen2.5-14B-Instruct" \
    --port 8000 \
    -c "${CTX_SIZE:-8192}" \
    -ngl 99
```

`setup_amd_cloud.sh` additionally generates `start_llama.sh` with the fully calibrated argument set (`--host 0.0.0.0 --batch-size 512 --parallel 1 --no-webui`).

`SINGLE_GPU_MODE=true` is the **default** (`backend/config/settings.py`, `single_gpu_mode: bool = True`), and `setup_amd_cloud.sh` Step 9 pins it in `backend/.env` (`Settings`' `env_file`) — an `export` would not survive into the shell that `start.sh` uses. All roles resolve to the same endpoint through one function — `settings.resolve_inference_url()` — regardless of their declared GPU affinity. The backend prints its resolved routing on startup so it can be verified at a glance:

```
[RoleLoader] 推理路由: 单 GPU 模式 (SINGLE_GPU_MODE=true) — 全部角色 → http://localhost:8000/v1
```

**Fitting 19 roles onto one 48GB card** is what makes this work:

- **Q4_K_M quantization**: weights stay small — Qwen2.5-14B ≈ 8.99 GiB, **Qwen3-30B-A3B MoE ≈ 18 GiB** (q5_k_m ≈ 10.5 GiB, q8_0 ≈ 15.7 GiB for the 14B build)
- **GQA-aware KV budgeting**: Qwen2.5-14B has 48 layers, 8 KV heads, head_dim 128 → `2 × 48 × 8 × 128 × 2 B = 196 608 B = 0.1875 MiB per token`
- **Sequential role execution**: roles share the GPU in turn rather than competing for VRAM, so peak usage is bounded by a single active context
- **Full offload** (`-ngl 99`): every layer lives on the Radeon GPU; no CPU fallback path

VRAM budget (weights + KV + ~1.5 GiB compute buffer), as documented in `setup_amd_cloud.sh`:

| CTX | 8192 | 16384 | 32768 | 65536 |
|---|---|---|---|---|
| KV cache (GiB) | 1.5 | 3.0 | 6.0 | 12.0 |
| q4_k_m total (GiB) | ~12.0 | ~13.5 | ~16.5 | ~22.5 |
| q5_k_m total (GiB) | ~13.5 | ~15.0 | ~18.0 | ~24.0 |

The demonstrated deployment runs **Qwen3-30B-A3B MoE (Q4_K_M, ≈ 18 GiB)** on the W7900. MoE activates only ~3B params per token, so decode stays fast; with its 4 KV heads the KV cache is tiny, and weights + 8K context fit within ~19 GiB — leaving ample headroom on 48 GB. The 14B figures above are the lighter default-install baseline.
`CTX_SIZE=8192` is a conservative starting baseline, not a VRAM ceiling. Note that `llama-server` splits the context across `--parallel` slots, so `PARALLEL=1` keeps the full context available to a single session.

### 3. Multi-GPU Affinity (Optional Scale-Out)

Every role carries a `gpu_affinity` tag (`gpu0`/`gpu1`/`gpu2`) in `data/role_pool.json`, assigned by task weight — 14B for heavy reasoning (Coach, Designer, Developer), 7B for lightweight checks (Inspector, Tester, Cleaner). On a single card these tags are ignored; on a multi-GPU host they become a scale-out plan that requires no code change:

```bash
# Opt in explicitly — you must start all three servers yourself
sed -i 's|^SINGLE_GPU_MODE=.*|SINGLE_GPU_MODE=false|' backend/.env

ROCR_VISIBLE_DEVICES=0 ./llama-server -m qwen2.5-14b-q4_k_m.gguf --port 8000
ROCR_VISIBLE_DEVICES=1 ./llama-server -m qwen2.5-7b-q4_k_m.gguf  --port 8001
ROCR_VISIBLE_DEVICES=2 ./llama-server -m qwen2.5-7b-q4_k_m.gguf  --port 8002
```

The dispatcher then routes roles to different GPUs via `MULTI_GPU_ENDPOINTS`. This path is **designed and implemented but not part of the demonstrated deployment** — the hardware we deployed on has one GPU. `start.sh` warns if `SINGLE_GPU_MODE=false` is set while only `:8000` is running.

### 4. Memory Optimization

- **GGUF Q4_K_M quantization**: 14B weights ship as an ≈ 8.99 GiB file, versus a ~28 GiB FP16 footprint for the same parameter count
- **Full GPU offload** (`-ngl 99`): no layer stays on CPU, so no host↔device round-trips per token
- **No PyTorch in the inference path**: llama.cpp links directly against ROCm; the Python backend never loads a GPU framework

### 5. Local-Only Inference Guarantee

**This project performs 100% of its model inference on the local AMD Radeon GPU. There is no remote API path — not a disabled one, not a configurable one. It does not exist in the code.**

How this is enforced (auditable in three files):

| Enforcement point | File | What it does |
|---|---|---|
| Runtime hard guard | `backend/config/settings.py` → `assert_local_endpoint()` | Every inference client is constructed through this function. Any `base_url` whose host is not `localhost` / `127.0.0.1` / `::1` raises `RemoteInferenceForbidden`. |
| No client, no keys | `backend/core/llm/gateway.py` | The gateway holds exactly one client type (local llama-server). `self._mode` is `"local"` or `"none"`. There is no `cloud` mode and no API-key field to populate. |
| Config surface sealed | `backend/config/settings.py` → `Settings(extra="ignore")` | Unknown environment variables (`ZHIPU_API_KEY`, `CLOUD_API_ENABLED`, `OPENAI_API_KEY`, …) have no field to bind to and are silently discarded. They cannot re-enable anything. |

When llama.cpp is unavailable, the gateway reports `mode = "none"` and inference is simply off. Degrading to a hosted model is not an option the system possesses.

> Note on the `openai` pip dependency: it is used purely as an **OpenAI-protocol client library** talking to the local `llama-server`, which exposes an OpenAI-compatible endpoint. No request ever leaves the machine.

---

## Model & Local Deployment

### Models Used

| Model | Size | Quantization | Loaded in default (single-GPU) deploy | Purpose |
|-------|------|-------------|:---:|---------|
| **Qwen3-30B-A3B-Instruct** | 30B (≈3B active, MoE) | GGUF Q4_K_M | **Yes — demonstrated deployment** (activate with `bash switch_model.sh 30b`) | Primary reasoning, code generation — used for the demo video |
| Qwen2.5-14B-Instruct | 14B | GGUF Q4_K_M | Default install (lighter) — serves all 19 roles | Primary reasoning, code generation |
| Qwen2.5-7B-Instruct | 7B | GGUF Q4_K_M | No — multi-GPU only (`gpu1`/`gpu2`) | Secondary reasoning, lightweight tasks |
| Qwen2.5-VL-7B-Instruct | 7B | GGUF | No — multi-GPU only (`gpu1`) | Multimodal vision analysis |

The GGUF file is fetched by `setup_amd_cloud.sh` / `install.sh` into `$HOME/llama.cpp/models/`, trying ModelScope → hf-mirror → Hugging Face in order, and validating the `GGUF` magic bytes after download. `setup_amd_cloud.sh` installs **Qwen2.5-14B** by default; the demonstrated **Qwen3-30B-A3B MoE** is selected with `bash switch_model.sh 30b` (updates `backend/.env`).

On the reference W7900 deployment a single **Qwen3-30B-A3B MoE (Q4_K_M)** instance backs the entire role system for the demo. The 7B and VL entries are part of the multi-GPU scale-out plan and are not loaded in the demonstrated configuration.

### Why llama.cpp + ROCm?

- **Zero Python GPU dependencies**: llama.cpp links directly against ROCm — no PyTorch, no CUDA translation layers (the image ships vLLM preinstalled; this project deliberately does not use it)
- **GGUF quantization**: Q4_K_M keeps the 14B weights under 9 GiB on disk and in VRAM
- **OpenAI-compatible API**: drop-in local replacement for cloud APIs
- **ROCm HIP backend**: AMD GPU acceleration through native HIP kernels

### Deployment Architecture

**Default — single GPU (this is what the demo video shows):**

```
        [ rc-tunnel expose --port 80 ]   ← external access
                         |
                    +----v-----+
                    |  Nginx   |  :80
                    +----+-----+
                         |  /        -> frontend dist
                         |  /api/    -> FastAPI
                         |  /v1/     -> llama-server
            +------------+------------+
            |                         |
    +-------v--------+     +---------v-------+
    |  FastAPI:8080  |     |  Frontend Dist  |
    +-------+--------+     +-----------------+
            |
            |  settings.resolve_inference_url()
            |  SINGLE_GPU_MODE=true -> all 19 roles
            |
     +------v-------------------+
     |  llama-server  :8000     |
     |  Qwen2.5-14B Q4_K_M      |
     |  Radeon PRO W7900 / 48GB |
     +--------------------------+

     No other inference path exists. There is no cloud
     endpoint, no fallback, and no API-key field to fill.
```

**Optional — multi-GPU scale-out (`SINGLE_GPU_MODE=false`):**

```
    +-------+--------+
    |  FastAPI:8080  |
    +-------+--------+
            |  routed by role gpu_affinity
   +--------+--------+
   |        |        |
+--v--+ +--v--+ +--v--+
|GPU0 | |GPU1 | |GPU2 |
|14B  | |7B+VL| |7B   |
|:8000| |:8001| |:8002|
+-----+ +-----+ +-----+
```

---

## Environment & Deployment

### Prerequisites

| Item | Requirement |
|------|-------------|
| GPU | AMD Radeon with ROCm support — **1 GPU is sufficient** (reference: Radeon PRO W7900, gfx1100) |
| VRAM | See the VRAM budget table above. Q4_K_M @ 8K context needs ~12 GiB; the 48 GB reference card comfortably allows 32K context |
| ROCm | 7.2 required for the official prebuilt llama.cpp binary; other versions need the source-build fallback |
| OS | Ubuntu 22.04 LTS (scripts use `apt-get`) |
| Storage | ≈ 9 GiB for the Q4_K_M weights, plus llama.cpp binaries (~124 MB prebuilt) and the frontend build output |
| RAM | Not enforced by the install scripts — *TBD, no measured figure available* |

### Quick Deploy (Radeon Cloud)

```bash
ssh user@<your-radeon-cloud-ip>
git clone https://github.com/bry9107795553/MyAgent.git
cd MyAgent

bash setup_amd_cloud.sh   # 9 steps: deps → GPU check → llama.cpp → model → backend
                          #          → frontend build → nginx → backend/.env
bash start.sh             # llama-server (:8000) → FastAPI (:8080) → Nginx (:80)

curl http://localhost:8080/api/health
```

`install.sh` is an alternative one-click installer covering the same ground (no Docker — Radeon Cloud container environments do not support Docker-in-Docker).

### External Access (rc-tunnel)

Radeon Cloud instances only expose Jupyter (8888) by default; **there is no security-group rule to open port 80 and no Jupyter proxy path**. Use the platform's tunnelling tool instead. `start.sh` does this automatically at the end of its run — it detects `rc-tunnel`, installs it if missing, exposes port 80 and prints the public URL:

```bash
rc-tunnel expose --port 80
```

> The tunnel is reclaimed after ~60 s idle. Re-run the command right before a demo.

If `rc-tunnel` is unavailable, the backend can still be reached directly at `http://<instance-ip>:8080/docs`.

### Manual Deployment

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080

# Frontend
cd frontend && npm install && npm run build

# llama.cpp (source-build fallback)
git clone https://github.com/ggml-org/llama.cpp
cd llama.cpp && mkdir build && cd build
cmake .. -DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1100 -DCMAKE_BUILD_TYPE=Release
cmake --build . -j$(nproc)
```

### Service Management

```bash
bash start.sh    # Start all services
bash stop.sh     # Stop all services
tail -f /tmp/llama.log    # llama-server logs
tail -f /tmp/backend.log  # FastAPI logs
```

---

## Technical Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| L1 Foundation | llama.cpp (ROCm/HIP) + ROCm 7.2 | AMD GPU local inference |
| L1 Foundation | Nginx | Single-port reverse proxy |
| L2 Orchestration | FastAPI + WebSocket | API, dispatch, real-time messaging |
| L2 Orchestration | Pydantic + watchdog | Config validation, hot-reload |
| L3 Configuration | YAML/JSON | Per-agent directory config |
| L4 UI | Vue 3 + Vite + GridStack.js | Frontend, drag-and-drop panels |
| L4 UI | Pinia | State management (`frontend/src/stores/layout.js`) |
| Models | Qwen2.5-14B/7B (GGUF Q4_K_M) | Primary/secondary inference |
| Models | Qwen2.5-VL-7B | Multimodal vision (multi-GPU only) |

### Frontend — three views

`frontend/src/views/`:

- **`ChatView.vue`** — conversation with the Agent (WebSocket streaming)
- **`WorkbenchView.vue`** — GridStack drag-and-drop workbench showing role deliverables, rendered by `components/ModuleRenderer.vue`
- **`SkinMarketView.vue`** — skin marketplace

---

## Key Design Decisions

- **Agent = Master Config Shell**: Creating an Agent customizes the Master role's personality, role pool, and tools. All conversations go through Master → Role dispatch.
- **Roles Never Communicate Directly**: Master acts as an information firewall. Roles communicate via shared blackboard (publish/subscribe with access control).
- **Zero-Loss Memory**: Raw messages archived BEFORE compression. Archive is append-only.
- **Direct Install, No Docker**: Radeon Cloud container environments don't support Docker-in-Docker.
- **llama.cpp b10267 prebuilt (ROCm 7.2)**: matches the Radeon Cloud image; source build with `-DGGML_HIP=ON` is the fallback.
- **GPU routing pinned to disk**: `SINGLE_GPU_MODE` is written into `backend/.env`, not exported, because `start.sh` launches the backend in a separate shell.

---

## Demo Video

Recorded on the reference **Radeon PRO W7900 (48GB, ROCm 7.2)** running **Qwen3-30B-A3B MoE**, 3–5 minutes, showing the full workflow on AMD Radeon GPU. Scenario script: [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md).

> _[Video link to be inserted before submission.]_

## Competition Submission

Per the Track 2 rules, all submission materials are in English:

- **Project documentation & README** — this file (scenarios, agent architecture, core capabilities, model & local deployment, GPU inference optimization).
- **Source code** — the full repository.
- **Demo video** — 3–5 min on Radeon PRO W7900; see [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md).
- **PR** — Fork `AMD-DEV-CONTEST/Radeon-hackathon-2026-07` and open a PR titled `Track 2, <name>, MyAgent`; see [`PR_SUBMISSION.md`](PR_SUBMISSION.md).

---

## Team

| Name | Role | Email |
|------|------|-------|
| bry9107795553 | Developer & Author (solo entry) | 118060862@qq.com |

---

## License

MIT
