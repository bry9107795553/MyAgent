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

18 roles are declared in `data/role_pool.json` and dispatched by Master; the Secretary is an always-on background role implemented in `backend/core/agent/orchestrator.py` (it observes every turn rather than being dispatched).

The **GPU column is the affinity tag** used for optional multi-GPU scale-out. In the default single-GPU deployment all roles run on the one physical GPU — see [Single-GPU Deployment](#2-single-gpu-deployment-default--as-demonstrated).

| Group | Role | GPU Affinity | Model Class | Capability |
|-------|------|--------------|-------------|------------|
| General | Master | GPU0 | 14B | Dispatch / Firewall / Summarization |
| General | Knowledge Retriever | GPU1 | 7B | RAG / Web Search |
| General | Writer | GPU0 | 14B | Reports / Emails / Copywriting |
| General | Quality Checker | GPU2 | 7B | Fact-checking / Logic Validation |
| General | Scheduler | GPU1 | 7B | Time Management |
| General | Creative | GPU0 | 14B | Brainstorming / Insight Extraction |
| General | Translator | GPU1 | 7B | Multi-language Translation |
| General | Visual Analyzer | GPU1 | VL-7B | Image Analysis (Multimodal) — see note |
| Development | Coach | GPU0 | 14B | Requirements / Dev Team Orchestration |
| Development | Designer | GPU0 | 14B | Design System / Multi-page Mockups |
| Development | Developer | GPU0 | 14B | Code Implementation |
| Development | Inspector | GPU2 | 7B | Architecture Review / Code Audit |
| Development | Tester | GPU2 | 7B | Type Checking / Linting / Unit Tests |
| Development | Deployer | GPU2 | 7B | Build / Deploy / Rollback |
| Development | Handoff Receiver | GPU0 | 14B | Existing-project Takeover / Impact Assessment |
| Operations | Cleaner | GPU2 | 7B | File System Cleanup |
| Management | HR Manager | GPU2 | 7B | Role Audit / Prompt Optimization |
| Management | Experience Evaluator | GPU2 | 7B | Experience Scoring / Memory Pruning |
| Core | Secretary *(always-on)* | GPU0 | 14B | Turn Recording / Experience Injection / Summarization |

> **Note on Visual Analyzer**: multimodal analysis requires the Qwen2.5-VL-7B weights, which are only loaded in the multi-GPU configuration. On the single-GPU deployment the role remains dispatchable and answers as a text role, but true image understanding is unavailable — the backend prints an explicit degradation warning at startup rather than failing silently.

### 10 Preset Workgroups

| Workgroup | Trigger Keywords | Pipeline |
|-----------|-----------------|----------|
| `dev_full` | "develop", "build", "create" | Coach → Designer → Coach → Developer → Inspector → Tester → Deployer → Cleaner |
| `dev_modification` | existing project + change request | Handoff Receiver → Inspector → Designer → Developer → Inspector → Tester → Deployer → Cleaner |
| `report_writing` | "write report", "draft article" | Knowledge Retriever → Writer → Quality Checker → Writer |
| `research_investigation` | "research", "investigate" | Knowledge Retriever → Creative → Quality Checker |
| `dev_code_review` | "review", "audit code" | Inspector → Developer → Tester → Cleaner |
| `dev_design_only` | "design", "UI", "mockup" | Coach → Designer → Quality Checker |
| `dev_tech_debt` | "tech debt", "refactor" | Inspector → Developer → Tester → Cleaner |
| `translation_task` | "translate" | Translator → Quality Checker → Translator |
| `schedule_planning` | "schedule", "reminder" | Scheduler → Creative → Quality Checker |
| `visual_analysis_task` | "analyze image" | Visual Analyzer → Writer |

Development pipelines additionally append an **Experience Evaluator** step at completion (dispatcher rule `experience_eval_hook`), which scores the experiences injected during the run and prunes stale memory.

---

## Core Capabilities

### 1. Natural Language Agent Generation
Describe your needs in plain language, and the AI auto-generates a complete Agent configuration (personality, role pool, tools, knowledge base). Zero coding required.

### 2. 4-Level Progressive Memory
- **L0 (Raw)**: Complete message archive, append-only, zero data loss
- **L1 (Light Summary)**: Incremental summaries every 5-10 turns for context injection
- **L2 (Dense Summary)**: Cross-session semantic compression for long-term recall
- **L3 (Knowledge Triples)**: Entity-relation extraction for structured knowledge retrieval

No truncation — only semantic compression. Write-before-compress guarantee prevents data loss.

### 3. Dynamic Dispatch System
Keyword/semantic matching + dynamic workgroup assembly. On the default single-GPU deployment roles execute sequentially on one llama-server; the same GPU-affinity metadata enables parallel scheduling across multiple GPUs when more than one card is available.

### 4. Project State Tracking
Cross-session project awareness via `PROJECT_STATUS.md`. The Coach role maintains structured progress tracking, and the system auto-restores context after restart.

### 5. Directory-Level Isolation
Agents and roles are independent folders. Add/remove = add/remove folders. Watchdog-based hot-reload — no system restart required.

### 6. Secretary Experience System
Records successful operation patterns across sessions. When the same task type is encountered, relevant experiences are injected into LLM context — preventing repeated trial-and-error.

---

## ROCm / AMD GPU Optimization

### 1. llama.cpp HIPBLAS Acceleration

The project uses **llama.cpp compiled with `-DGGML_HIP=ON -DGGML_HIPBLAS=ON`** for native ROCm acceleration:

```bash
cmake .. -DGGML_HIP=ON -DGGML_HIPBLAS=ON \
    -DCMAKE_C_COMPILER=gcc -DCMAKE_CXX_COMPILER=g++ \
    -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release -j$(nproc)
```

All matrix operations (attention, FFN, embedding) are offloaded to AMD GPU via HIPBLAS, achieving near-CUDA parity on Radeon hardware.

### 2. Single-GPU Deployment (Default — as demonstrated)

**The shipped configuration targets a single AMD GPU.** Our reference deployment — and everything shown in the demo video — runs on one **Radeon PRO W7900 (48GB, gfx1100, ROCm 7.2)** on a Radeon Cloud instance, serving all 19 roles from a single `llama-server`:

```bash
# Started by setup_amd_cloud.sh — one server, one GPU, all roles
./llama-server -m qwen2.5-14b-instruct-q4_k_m.gguf \
    -a Qwen2.5-14B-Instruct --port 8000 \
    -ngl 99 --ctx-size 8192 --parallel 1
```

`SINGLE_GPU_MODE=true` is the **default** (`backend/config/settings.py`), and `setup_amd_cloud.sh` additionally pins it in `backend/.env`. All roles resolve to the same endpoint through one function — `settings.resolve_inference_url()` — regardless of their declared GPU affinity. No environment variable needs to be set by hand; the backend prints its resolved routing on startup so it can be verified at a glance:

```
[RoleLoader] 推理路由: 单 GPU 模式 (SINGLE_GPU_MODE=true) — 全部角色 → http://localhost:8000/v1
```

**Fitting 19 roles onto one 48GB card** is what makes this work:

- **Q4_K_M quantization**: 14B weights occupy ~9GB instead of ~28GB at FP16
- **GQA-aware KV budgeting**: Qwen2.5-14B uses only 8 KV heads, so KV cache costs ~0.1875 MiB/token — even a 32K context stays under ~18GB total
- **Sequential role execution**: roles share the GPU in turn rather than competing for VRAM, so peak usage is bounded by a single active context
- **Full offload** (`-ngl 99`): every layer lives on the Radeon GPU; no CPU fallback path

### 3. Multi-GPU Affinity (Optional Scale-Out)

Every role carries a `gpu_affinity` tag (`gpu0`/`gpu1`/`gpu2`) in `data/role_pool.json`, assigned by task weight — 14B for heavy reasoning (Coach, Designer, Developer), 7B for lightweight checks (Inspector, Tester, Cleaner). On a single card these tags are simply ignored; on a multi-GPU host they become a scale-out plan that requires no code change:

```bash
# Opt in explicitly — you must start all three servers yourself
sed -i 's|^SINGLE_GPU_MODE=.*|SINGLE_GPU_MODE=false|' backend/.env

ROCR_VISIBLE_DEVICES=0 ./llama-server -m qwen2.5-14b-q4_k_m.gguf --port 8000
ROCR_VISIBLE_DEVICES=1 ./llama-server -m qwen2.5-7b-q4_k_m.gguf  --port 8001
ROCR_VISIBLE_DEVICES=2 ./llama-server -m qwen2.5-7b-q4_k_m.gguf  --port 8002
```

The dispatcher then executes roles on different GPUs in parallel while serializing same-GPU roles. This path is **designed and implemented but not part of the demonstrated deployment** — the hardware we deployed on has one GPU.

### 4. Memory Optimization

- **GGUF Q4_K_M quantization**: 14B model fits in ~9GB VRAM instead of ~28GB FP16
- **Context-aware batch sizing**: Dynamically adjusts `--ctx-size` based on available VRAM
- **No PyTorch overhead**: llama.cpp eliminates Python/CUDA runtime overhead, reducing VRAM fragmentation

### 5. Local-Only Inference Guarantee

**This project performs 100% of its model inference on the local AMD Radeon GPU. There is no remote API path — not a disabled one, not a configurable one. It does not exist in the code.**

How this is enforced (auditable in three files):

| Enforcement point | File | What it does |
|---|---|---|
| Runtime hard guard | `backend/config/settings.py` → `assert_local_endpoint()` | Every inference client is constructed through this function. Any `base_url` whose host is not `localhost` / `127.0.0.1` / `::1` raises `RemoteInferenceForbidden` and the service refuses to start. |
| No client, no keys | `backend/core/llm/gateway.py` | The gateway holds exactly one client type (local llama-server). Modes are `local` or `none`. There is no `cloud` mode and no API-key field to populate. |
| Config surface sealed | `backend/config/settings.py` → `Settings(extra="ignore")` | Unknown environment variables (`ZHIPU_API_KEY`, `CLOUD_API_ENABLED`, `OPENAI_API_KEY`, …) have no field to bind to and are silently discarded. They cannot re-enable anything. |

When llama.cpp is unavailable, the gateway reports `mode = "none"` and inference is simply off. Degrading to a hosted model is not an option the system possesses.

> Note on the `openai` pip dependency: it is used purely as an **OpenAI-protocol client library** talking to the local `llama-server`, which exposes an OpenAI-compatible endpoint. No request ever leaves the machine.

---

## Model & Local Deployment

### Models Used

| Model | Size | Quantization | Loaded in default (single-GPU) deploy | Purpose |
|-------|------|-------------|:---:|---------|
| Qwen2.5-14B-Instruct | 14B | GGUF Q4_K_M | **Yes** — serves all 19 roles | Primary reasoning, code generation |
| Qwen2.5-7B-Instruct | 7B | GGUF Q4_K_M | No — multi-GPU only (`gpu1`/`gpu2`) | Secondary reasoning, lightweight tasks |
| Qwen2.5-VL-7B-Instruct | 7B | GGUF | No — multi-GPU only (`gpu1`) | Multimodal vision analysis |

On the reference W7900 deployment a single Qwen2.5-14B-Instruct Q4_K_M instance backs the entire role system. The 7B and VL entries are part of the multi-GPU scale-out plan and are not loaded in the demonstrated configuration.

### Why llama.cpp + ROCm?

- **Zero Python GPU dependencies**: llama.cpp compiles directly against ROCm — no PyTorch, no CUDA translation layers
- **GGUF quantization**: Q4_K_M reduces VRAM by ~60% with minimal quality loss
- **OpenAI-compatible API**: Drop-in local replacement for cloud APIs
- **ROCm HIPBLAS backend**: Full AMD GPU acceleration through native HIP kernels

### Deployment Architecture

**Default — single GPU (this is what the demo video shows):**

```
                    +----------+
                    |  Nginx   |  :80
                    +----+-----+
                         |
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
| GPU | AMD Radeon with ROCm 6.x+ support — **1 GPU is sufficient** (reference: Radeon PRO W7900) |
| VRAM | ≥ 16GB for 14B Q4_K_M @ 8K context; 48GB (reference card) comfortably allows 32K context |
| RAM | ≥ 64GB |
| Storage | ≥ 100GB SSD |
| OS | Ubuntu 22.04 LTS |
| ROCm | Pre-installed (Radeon Cloud instances come with ROCm 7.2) |

### Quick Deploy (Radeon Cloud)

```bash
ssh user@<your-radeon-cloud-ip>
git clone <this-repo-url>
cd track2_MyAgent
bash install.sh    # One-click install
bash start.sh      # Start all services
curl http://localhost/api/health
```

### Manual Deployment

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080

# Frontend
cd frontend && npm install && npm run build

# llama.cpp
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp && mkdir build && cd build
cmake .. -DGGML_HIP=ON -DGGML_HIPBLAS=ON -DCMAKE_BUILD_TYPE=Release
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
| L1 Foundation | llama.cpp + ROCm 7.2 | AMD GPU local inference |
| L1 Foundation | Nginx | Single-port reverse proxy |
| L2 Orchestration | FastAPI + WebSocket | API, dispatch, real-time messaging |
| L2 Orchestration | Pydantic + watchdog | Config validation, hot-reload |
| L3 Configuration | YAML/JSON | Per-agent directory config |
| L4 UI | Vue 3 + Vite + GridStack.js | Frontend, drag-and-drop panels |
| L4 UI | Pinia | State management |
| Models | Qwen2.5-14B/7B (GGUF Q4_K_M) | Primary/secondary inference |
| Models | Qwen2.5-VL-7B | Multimodal vision |

---

## Key Design Decisions

- **Agent = Master Config Shell**: Creating an Agent customizes the Master role's personality, role pool, and tools. All conversations go through Master → Role dispatch.
- **Roles Never Communicate Directly**: Master acts as an information firewall. Roles communicate via shared blackboard (publish/subscribe with access control).
- **Zero-Loss Memory**: Raw messages archived BEFORE compression. Archive is immutable.
- **Direct Install, No Docker**: Radeon Cloud container environments don't support Docker-in-Docker.
- **llama.cpp b9859**: Compatible with ROCm 7.2.

---

## Demo Video

[Link to demo video — 3-5 minutes, demonstrating full workflow on AMD Radeon GPU]

---

## Team

| Name | Role | Email |
|------|------|-------|
| bry9107795553 | Developer & Author (solo entry) | 118060862@qq.com |

---

## License

MIT