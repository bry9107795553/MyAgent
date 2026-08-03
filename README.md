# MyAgent — Private AI Agent Platform with AMD Radeon GPU + ROCm

**Track 2: Development & Local Deployment of Private AI Agents**
**2026 AMD AI DevMaster Hackathon**

A fully local, privacy-first AI agent platform powered by AMD Radeon GPUs and ROCm. All inference runs on local GPU via llama.cpp — zero cloud dependency, works offline, and no user data ever leaves the machine.

---

## Application Scenarios

MyAgent is designed for users who need a capable AI assistant without sacrificing data privacy:

- **Software Development**: Full development lifecycle from requirements analysis to deployment, orchestrated by 15 specialized AI roles (Coach, Designer, Developer, Inspector, Tester, Deployer)
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
|  FastAPI + WebSocket + Dispatcher + 15 Roles        |
|  + 4-Level Progressive Memory + Shared Blackboard  |
|  Master Dispatch · Role Collaboration · Agent Gen  |
+---------------------------------------------------+
|  L1  Foundation Layer                               |
|  llama.cpp + ROCm + Nginx                          |
|  Local Inference · GPU Acceleration · Single Port  |
+---------------------------------------------------+
```

### 15-Role System

The Master role acts as a **firewall and dispatcher** — all requests go through it, and roles never communicate directly.

| Group | Role | GPU | Model | Capability |
|-------|------|-----|-------|------------|
| General | Master | GPU0 | 14B | Dispatch / Firewall / Summarization |
| General | Knowledge Retriever | GPU1 | 7B | RAG / Web Search |
| General | Writer | GPU0 | 14B | Reports / Emails / Copywriting |
| General | Quality Checker | GPU2 | 7B | Fact-checking / Logic Validation |
| General | Scheduler | GPU1 | 7B | Time Management |
| General | Creative | GPU0 | 14B | Brainstorming / Insight Extraction |
| General | Translator | GPU1 | 7B | Multi-language Translation |
| General | Visual Analyzer | GPU1 | VL-7B | Image Analysis (Multimodal) |
| Development | Coach | GPU0 | 14B | Requirements / Dev Team Orchestration |
| Development | Designer | GPU0 | 14B | Design System / Multi-page Mockups |
| Development | Developer | GPU0 | 14B | Code Implementation |
| Development | Inspector | GPU2 | 7B | Architecture Review / Code Audit |
| Development | Tester | GPU2 | 7B | Type Checking / Linting / Unit Tests |
| Development | Deployer | GPU2 | 7B | Build / Deploy / Rollback |
| Operations | Cleaner | GPU2 | 7B | File System Cleanup |

### 9 Preset Workgroups

| Workgroup | Trigger Keywords | Pipeline |
|-----------|-----------------|----------|
| `dev_full` | "develop", "build", "create" | Coach → Designer → Developer → Inspector → Tester → Cleaner |
| `report_writing` | "write report", "draft article" | Writer → Quality Checker |
| `research_investigation` | "research", "investigate" | Knowledge Retriever → Writer → Quality Checker |
| `dev_code_review` | "review", "audit code" | Inspector |
| `dev_design_only` | "design", "UI", "mockup" | Coach → Designer |
| `dev_tech_debt` | "tech debt", "refactor" | Inspector → Cleaner |
| `translation_task` | "translate" | Translator → Quality Checker |
| `schedule_planning` | "schedule", "reminder" | Scheduler |
| `visual_analysis_task` | "analyze image" | Visual Analyzer → Writer |

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
Keyword/semantic matching + dynamic workgroup assembly. GPU-affinity-aware parallel scheduling across 3 GPU instances.

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

### 2. Multi-GPU Parallel Inference

Three llama-server instances run on separate GPUs with `ROCR_VISIBLE_DEVICES` isolation:

```bash
ROCR_VISIBLE_DEVICES=0 ./llama-server -m qwen2.5-14b-q4_k_m.gguf --port 8000
ROCR_VISIBLE_DEVICES=1 ./llama-server -m qwen2.5-7b-q4_k_m.gguf --port 8001
ROCR_VISIBLE_DEVICES=2 ./llama-server -m qwen2.5-7b-q4_k_m.gguf --port 8002
```

Roles are assigned GPU affinity based on task complexity — 14B for heavy reasoning, 7B for lightweight checks.

### 3. Single GPU Mode

For environments with only one AMD GPU (e.g., cloud instances), `single_gpu_mode=true` routes all 15 roles to a single llama-server instance, sharing the GPU sequentially.

### 4. Memory Optimization

- **GGUF Q4_K_M quantization**: 14B model fits in ~9GB VRAM instead of ~28GB FP16
- **Context-aware batch sizing**: Dynamically adjusts `--ctx-size` based on available VRAM
- **No PyTorch overhead**: llama.cpp eliminates Python/CUDA runtime overhead, reducing VRAM fragmentation

### 5. Cloud API Fallback

When local GPU is unavailable, the system automatically falls back to Zhipu AI GLM-4 cloud API, ensuring zero downtime.

---

## Model & Local Deployment

### Models Used

| Model | Size | Quantization | GPU | Purpose |
|-------|------|-------------|-----|---------|
| Qwen2.5-14B-Instruct | 14B | GGUF Q4_K_M | GPU0 | Primary reasoning, code generation |
| Qwen2.5-7B-Instruct | 7B | GGUF Q4_K_M | GPU1/GPU2 | Secondary reasoning, lightweight tasks |
| Qwen2.5-VL-7B-Instruct | 7B | GGUF | GPU1 | Multimodal vision analysis |

### Why llama.cpp + ROCm?

- **Zero Python GPU dependencies**: llama.cpp compiles directly against ROCm — no PyTorch, no CUDA translation layers
- **GGUF quantization**: Q4_K_M reduces VRAM by ~60% with minimal quality loss
- **OpenAI-compatible API**: Drop-in local replacement for cloud APIs
- **ROCm HIPBLAS backend**: Full AMD GPU acceleration through native HIP kernels

### Deployment Architecture

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
   +--------+--------+--------+
   |        |        |        |
+--v--+ +--v--+ +--v--+      |
|GPU0 | |GPU1 | |GPU2 |      |
|14B  | |7B+VL| |7B   |      |
|:8000| |:8001| |:8002|      |
+-----+ +-----+ +-----+      |
                             |
                    +--------v--------+
                    |  Cloud API       |
                    |  Fallback Only   |
                    +-----------------+
```

---

## Environment & Deployment

### Prerequisites

| Item | Requirement |
|------|-------------|
| GPU | AMD Radeon with ROCm 6.x+ support |
| VRAM | ≥ 48GB (3-GPU); ≥ 16GB (single GPU mode) |
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
| [Team Member 1] | [Role] | [Email] |

---

## License

MIT