# Project Specification Document: MyAgent

## Track 2: Development & Local Deployment of Private AI Agents
### 2026 AMD AI DevMaster Hackathon

---

## 1. Application Scenarios

MyAgent targets three primary use cases:

### 1.1 AI-Assisted Software Development
Users describe software requirements in natural language. The system automatically assembles a 6-role development pipeline (Coach → Designer → Developer → Inspector → Tester → Cleaner) that handles the full lifecycle: requirements analysis, UI design, code implementation, architecture review, testing, and deployment. All roles run on local AMD GPU inference.

### 1.2 Knowledge Work & Research
Multi-role quality assurance for research reports, document writing, and data analysis. The Writer → Quality Checker pipeline ensures factual accuracy, while the Knowledge Retriever provides RAG-based context enrichment.

### 1.3 Offline-First Personal Assistant
Full functionality without internet connectivity. All inference runs locally via llama.cpp + ROCm. Ideal for air-gapped environments, travel, or privacy-sensitive scenarios.

---

## 2. Agent Architecture

### 2.1 4-Layer Design

```
+---------------------------------------------------+
|  L4  UI Layer                                      |
|  Vue 3 + GridStack.js + Universal Module Renderer   |
+---------------------------------------------------+
|  L3  Agent Configuration Layer                     |
|  Directory-isolated agents with hot-reload         |
+---------------------------------------------------+
|  L2  Orchestration Layer                           |
|  FastAPI + WebSocket + 15 Roles + 4-Level Memory   |
+---------------------------------------------------+
|  L1  Foundation Layer                              |
|  llama.cpp + ROCm + Nginx                         |
+---------------------------------------------------+
```

### 2.2 Master-Role Dispatch Model

The Agent is a "Master configuration shell." User creates an Agent = customizes Master's personality, role pool, and tool permissions. All conversations follow a unified dispatch chain:

```
User → Agent (Master) → Role Pool → LLM (local GPU)
```

### 2.3 Role System (15 Roles)

| Role | GPU | Model | Function |
|------|-----|-------|----------|
| Master | GPU0 | 14B | Dispatch, firewall, summarization |
| Coach | GPU0 | 14B | Requirements discovery, dev team orchestration |
| Designer | GPU0 | 14B | Design system, UI mockups |
| Developer | GPU0 | 14B | Code implementation |
| Writer | GPU0 | 14B | Reports, emails, copywriting |
| Creative | GPU0 | 14B | Brainstorming, insight extraction |
| Knowledge Retriever | GPU1 | 7B | RAG, web search |
| Translator | GPU1 | 7B | Multi-language translation |
| Visual Analyzer | GPU1 | VL-7B | Image analysis (multimodal) |
| Scheduler | GPU1 | 7B | Time management |
| Quality Checker | GPU2 | 7B | Fact-checking, logic validation |
| Inspector | GPU2 | 7B | Architecture review, code audit |
| Tester | GPU2 | 7B | Type checking, linting, unit tests |
| Deployer | GPU2 | 7B | Build, deploy, rollback |
| Cleaner | GPU2 | 7B | File system cleanup |

### 2.4 Workgroup Assembly

Complex tasks trigger automatic workgroup assembly based on keyword/semantic matching. Nine preset workgroups cover common workflows. The dispatcher supports dynamic assembly for novel task types.

---

## 3. Core Capabilities

### 3.1 Natural Language Agent Generation
Users describe desired agent behavior in natural language. The LLM generates complete agent configuration (personality, role pool, tools, knowledge base) and creates the agent directory automatically.

### 3.2 4-Level Progressive Memory
- **L0 Raw**: Complete message archive, append-only, zero data loss
- **L1 Light Summary**: Incremental summaries every 5-10 turns
- **L2 Dense Summary**: Cross-session semantic compression
- **L3 Knowledge Triples**: Entity-relation extraction for structured retrieval

Write-before-compress guarantee: raw messages are archived BEFORE compression, preventing data loss on crash.

### 3.3 Dynamic Dispatch
Keyword/semantic matching + configurable GPU affinity. Supports parallel scheduling across 3 GPU instances.

### 3.4 Project State Tracking
Cross-session project awareness via PROJECT_STATUS.md. System auto-restores context after restart.

### 3.5 Secretary Experience System
Records successful operation patterns across sessions. Injects relevant experiences into LLM context before task execution to prevent repeated trial-and-error.

---

## 4. Model Introduction & Local Deployment

### 4.1 Model Selection

| Model | Parameters | Quantization | VRAM Usage | GPU |
|-------|-----------|-------------|------------|-----|
| Qwen2.5-14B-Instruct | 14B | GGUF Q4_K_M | ~9GB | GPU0 |
| Qwen2.5-7B-Instruct | 7B | GGUF Q4_K_M | ~5GB | GPU1, GPU2 |
| Qwen2.5-VL-7B-Instruct | 7B | GGUF | ~6GB | GPU1 |

### 4.2 Inference Engine: llama.cpp

We chose llama.cpp over PyTorch-based solutions for several reasons:
- **Direct ROCm compilation**: No Python GPU dependency layers
- **GGUF quantization**: 60% VRAM reduction with minimal quality loss
- **OpenAI-compatible API**: llama-server provides `/v1/chat/completions`
- **Lower overhead**: No CUDA translation, no Python runtime overhead

### 4.3 Deployment Architecture

```
Nginx :80 → FastAPI :8080 → llama-server :8000 (GPU0, 14B)
                           → llama-server :8001 (GPU1, 7B+VL)
                           → llama-server :8002 (GPU2, 7B)

All inference endpoints are loopback-only. No egress path exists.
```

---

## 5. ROCm / AMD GPU Optimization

### 5.1 HIPBLAS Acceleration
llama.cpp compiled with `-DGGML_HIP=ON -DGGML_HIPBLAS=ON`. All matrix operations (attention, FFN, embedding) offloaded to AMD GPU via native HIP kernels.

### 5.2 Multi-GPU Parallel Inference
Three llama-server instances on separate GPUs with `ROCR_VISIBLE_DEVICES` isolation. GPU affinity assignment based on task complexity.

### 5.3 Single GPU Mode
`single_gpu_mode=true` routes all 15 roles to a single GPU instance for cloud environments with one GPU.

### 5.4 Memory Optimization
- GGUF Q4_K_M quantization: 14B model in ~9GB VRAM
- Context-aware batch sizing based on available VRAM
- No PyTorch overhead reduces VRAM fragmentation

### 5.5 Local-Only Inference Guarantee
All inference runs on the local AMD Radeon GPU via llama.cpp + ROCm. The codebase contains **no** remote/hosted model client, **no** API-key field, and **no** cloud fallback path.

Enforced by `backend/config/settings.py::assert_local_endpoint()` — every inference client is constructed through this check, and any non-loopback `base_url` raises `RemoteInferenceForbidden`. `Settings` is declared with `extra="ignore"`, so stray environment variables such as `ZHIPU_API_KEY` or `CLOUD_API_ENABLED` have no field to bind to and cannot re-enable anything.

If llama.cpp is down, the gateway reports `mode = "none"` and inference is disabled. There is no degraded remote mode.

---

## 6. Dependencies

### Python (backend/requirements.txt)
```
fastapi, uvicorn, websockets, pydantic, pydantic-settings,
openai (local OpenAI-protocol client only), httpx, pyyaml,
watchdog, python-multipart, python-dotenv, Pillow, scikit-learn
```

### Node.js (frontend/package.json)
```
vue 3, vue-router, pinia, gridstack, marked, highlight.js
```

### System
```
llama.cpp (b9859), ROCm 7.2+, Nginx, Node.js 22+, Python 3.12+
```

---

## 7. Reproducibility

### One-Command Deploy
```bash
git clone <repo-url> && cd track2_MyAgent && bash install.sh && bash start.sh
```

### Verification
```bash
curl http://localhost/api/health  # {"status":"ok","llm_available":true}
curl http://localhost:8000/v1/models  # Model list
```

### Offline Test
```bash
bash tests/offline_test.sh
```

---

## 8. Innovation Points

1. **15-Role Collaborative Architecture**: First open-source agent platform with 15 specialized roles on local GPU
2. **Natural Language Agent Generation**: Zero-code agent creation via LLM
3. **4-Level Progressive Memory**: No-truncation semantic compression with write-before-compress guarantee
4. **Secretary Experience System**: Cross-session operation pattern learning and reuse
5. **Full AMD GPU Pipeline**: llama.cpp + ROCm end-to-end, no NVIDIA dependency
6. **Directory-Level Hot-Reload**: Add/remove agents and roles without restart