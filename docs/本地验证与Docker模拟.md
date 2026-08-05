# 本地验证与 Docker 模拟环境

> 目的：在**没有 AMD GPU** 的开发机上把 MyAgent 完整跑通、抓出部署期 bug，
> 避免"带 bug 上云 → 云实例卡死 → 反复重来"的死循环。
>
> 核心思路：用一个**假推理端点** `mock_llm.py` 顶替 llama.cpp，
> 它实现了 llama-server 对外的那套 OpenAI 兼容接口（含流式与 function calling），
> 因此后端、角色调度、工具闭环、WebSocket、前端全都能按真实链路跑。
> 只有"模型输出质量"和"GPU 性能"这两件事需要真机验证。

---

## 一、组件与端口

| 组件 | 端口 | 说明 |
| --- | --- | --- |
| `mock_llm.py` | 8000 | 假推理端点，纯 Python 标准库，无第三方依赖 |
| 后端 FastAPI | 8080 | 真实部署端口；本地若被占用可用 `PORT` 环境变量改 |
| 前端 | 80 / 5173 | Docker 用 Nginx :80；本地开发用 Vite :5173 |

后端通过 `http://localhost:8000/v1` 连推理端点，这个地址是**硬约束**：
`backend/config/settings.py` 的 `assert_local_endpoint()` 会拒绝任何非
`localhost / 127.0.0.1 / ::1` 的推理地址并直接抛异常（赛道合规要求的代码级执行点）。

### `mock_llm.py` 实现的接口

- `GET  /v1/models` — 返回 `Qwen2.5-14B-Instruct`，用于后端启动探活
- `POST /v1/chat/completions`
  - `stream: false` → 整段 JSON 返回
  - `stream: true`  → SSE 分块（`data: {json}\n\n`，以 `data: [DONE]` 结束）
  - 当请求带 `tools` 且用户文本命中触发词（写文件 / 落盘 / 生成文件 / file_write 等）
    时返回一个 `file_write` 的 `tool_calls`，用来验证工具闭环
- `GET  /health` — 容器健康检查用
- `api_key` 一律忽略（后端传的是 `EMPTY`）

---

## 二、本地直接运行（不用 Docker）

### 1. 建虚拟环境装依赖

```bash
cd <项目根>
python -m venv backend/venv
# Windows Git Bash
./backend/venv/Scripts/python.exe -m ensurepip --upgrade
./backend/venv/Scripts/python.exe -m pip install -r backend/requirements.txt --disable-pip-version-check
```

> ⚠ 不要执行 `pip install --upgrade pip`。在部分受限环境下升级会把 venv 里的
> `pip.exe` 弄坏（报 `No module named pip`），只能删掉 venv 重建。
> `ensurepip --upgrade` 是安全的替代做法。

### 2. 起假推理端点

```bash
./backend/venv/Scripts/python.exe mock_llm.py
# 另开一个终端验证
curl http://127.0.0.1:8000/v1/models
```

### 3. 起后端

```bash
cd backend
PORT=8088 ../backend/venv/Scripts/python.exe main.py     # 8080 被占用时换端口
curl http://127.0.0.1:8088/api/health
# 期望 {"status":"ok","llm_available":true,...}
```

> 若 `llm_available` 为 `false`，先确认 8000 端口真的在监听。
> 后端支持推理端点**后到**（见第五节 BUG-5），端点起来后再请求一次
> `/api/health` 即可自动恢复，**不需要重启后端**。

### 4. 构建前端

```bash
cd frontend
npm install
npm run build      # 产物在 frontend/dist，后端会自动托管
```

后端启动时若检测到 `frontend/dist` 存在，会 mount `/assets` 并做 SPA fallback，
所以直接访问 `http://127.0.0.1:8088/` 就能打开完整页面，无需另起 Nginx。

前端开发模式（热更新）走 Vite：`npm run dev`，
`vite.config.js` 已配好 `/api → 8080`、`/v1 → 8000` 的代理。

### 5. 跑端到端自检

```bash
./backend/venv/Scripts/python.exe ws_client.py --host 127.0.0.1 --port 8088
```

`ws_client.py` 会依次验证 6 组共 20 项：

| 组 | 验证内容 |
| --- | --- |
| 0 | `/api/health` 可达、`llm_available` 为真 |
| 1 | WS 流式对话：`stream_start` / `stream_token` / `stream_meta` / `stream_end` 四类帧齐全，回复非空，记忆落盘 |
| 2 | 工具闭环：触发 `file_write`，`data/projects/mock_tool_output.md` 真实写入且 mtime 更新；`stream_meta` 带回工作组与角色列表 |
| 3 | `GET /{agent}/history` 回读一致 |
| 4 | 角色切换与记忆隔离：新建第二个 Agent 立即可对话，两者 `chat_history.json` 互不污染 |
| 5 | 异常输入：空消息体不会打挂 WS 连接 |

最近一次本地执行结果：**20/20 通过**。

---

## 三、Docker 模拟环境

### 运行

```bash
docker compose up --build
# 打开 http://localhost
docker compose down
```

### 产物清单

| 文件 | 作用 |
| --- | --- |
| `backend/Dockerfile` | 后端镜像（python:3.11-slim + requirements） |
| `frontend/Dockerfile` | 前端镜像（node:20-alpine 构建 → nginx:alpine 托管） |
| `frontend/nginx.conf` | **容器内**反代配置，指向 `backend:8080` |
| `docker-compose.yml` | 三服务编排 + 健康检查 |
| `.dockerignore` / `frontend/.dockerignore` | 排除 venv、node_modules，避免上下文膨胀 |

> 仓库根目录原有的 `nginx.conf` 是**裸机部署**用的（`install.sh` 复制到
> `/etc/nginx/nginx.conf`，反代 `127.0.0.1:8080`），与 `frontend/nginx.conf` 互不冲突，
> 两个文件都保留。

### ⚠ 关键设计：推理容器为什么要 `network_mode: "service:backend"`

因为 `assert_local_endpoint()` 只认 localhost，后端**不能**用
`http://mock-llm:8000/v1` 这种 compose 服务名去连推理。
所以让推理容器加入后端的网络命名空间，两者共享同一个 `localhost`：

```yaml
mock-llm:
  network_mode: "service:backend"
```

这不是妥协，而是**与真实部署拓扑一致**——AMD 云实例上 llama-server 与后端本来就同机，
都走 localhost。换真 GPU 时这一行原样照抄即可，后端代码零改动。

副作用：推理容器没有独立网络别名，它的端口映射要写在 `backend` 服务的 `ports` 里
（compose 文件中已这么处理，`8000:8000` 挂在 backend 下）。

### 启动顺序

`mock-llm` 依赖 backend 的网络命名空间，所以 **backend 必然先起**，
此时推理端点尚未监听。这正好是真实部署的常态（llama-server 加载 14B GGUF
要几十秒到几分钟）。后端已实现推理端点后到时的惰性重探（BUG-5 修复），
因此这个顺序是安全的，无需 `depends_on: service_healthy` 兜底。

### 换成真实 GPU 推理

把 `mock-llm` 服务整段替换为 ROCm llama.cpp（`docker-compose.yml` 末尾有完整注释模板），
要点：

1. `network_mode: "service:backend"` 照抄
2. 挂载 `/dev/kfd` 与 `/dev/dri`，`group_add: [video]`
3. `--alias Qwen2.5-14B-Instruct` 必须等于后端 `LLAMA_MODEL`，否则请求 404
4. **必须带 `--jinja`**（或等效 chat template），否则不返回 `tool_calls`，
   角色系统的工具闭环会静默退化成纯文本回复
5. 裸机部署仍推荐用仓库自带的 `setup_amd_cloud.sh` / `start.sh`，
   本 compose 只是无 GPU 环境的等价模拟，**不替代**它们（这两个脚本未做任何改动）

---

## 四、本次验证修复的 Bug

以下都是**真实代码缺陷**，已直接改代码修复并复测通过。

### BUG-1 调度元数据 JSON 泄漏进对话正文

- **现象**：每条回复开头都出现一串裸 JSON
  `{"type": "meta", "workgroup": null, "roles_used": []}`，用户直接看到。
- **原因**：`BaseAgent.chat_stream()` 把元数据 `json.dumps` 后当作普通 token `yield`，
  消息总线不加区分地包成 `stream_token` 帧，前端全部拼进正文。
- **修复**：`backend/core/agent/base.py` —— 删除两处 meta token 的 yield，
  生成器只吐纯文本；元数据改由 WS 层以独立 `stream_meta` 帧下发。

### BUG-2 `stream_meta` 帧永远送不到前端

- **现象**：前端"调度信息"区域恒为空。
- **原因**：`agent_routes.py` 在 `stream_to_agent()` 返回**之后**才发 `stream_meta`，
  而该方法内部最后一步已经发了 `stream_end`；前端收到 `stream_end` 立刻 `ws.close()`，
  元数据帧到达时连接已关闭。
- **修复**：
  - `backend/core/bus.py` —— `stream_to_agent()` 新增可选 `meta_provider` 参数，
    在 `stream_end` **之前**下发 `stream_meta`
  - `backend/api/routes/agent_routes.py` —— 改为传 `meta_provider=lambda: agent.last_dispatch_info`

### BUG-3 新建 Agent 后立即对话 WebSocket 403

- **现象**：`POST /api/agents` 返回 200，紧接着连 WS 被拒（403），必须重启后端才能用。
- **原因**：注册依赖 watchdog 的目录创建事件，而 `on_created` 里判断
  `(dir/"config.yaml").exists()` —— 目录创建事件早于 `config.yaml` 写盘，
  判定为 False 后**静默跳过**注册。容器环境里 inotify 常被禁用，问题更严重。
- **修复**：
  - `backend/core/agent/registry.py` —— 新增 `register_when_ready()`，
    目录事件后最多轮询等待 5 秒直到 `config.yaml` 落盘再注册
  - `backend/api/routes/agent_routes.py` —— 创建接口里**显式注册**，不再只靠热加载；
    删除接口里改为**先注销后删目录**（注销会 `save_memory()`，目录先删会写盘失败）

### BUG-4 运行期新建的 Agent 拿不到角色系统

- **现象**：新建的 Agent 能对话，但不走 17 角色调度、不会调用工具，
  等同于退化成裸 LLM 问答。
- **原因**：`main.py` 只在启动时遍历"当时已注册"的 Agent 调 `bind_master()`，
  之后新注册的 Agent 没有任何绑定入口。
- **修复**：
  - `backend/core/agent/registry.py` —— 注册表持有 master 引用，新增 `set_master()`，
    并在 `register()` 里自动绑定
  - `backend/main.py` —— 用 `agent_registry.set_master(master)` 替换原来的 for 循环

### BUG-5 推理端点晚于后端启动时，后端永久判死（部署致命）

- **现象**：`/api/health` 一直 `llm_available: false`，`POST /chat` 一直 503，
  即使推理服务后来已经正常，也必须**重启后端**才能恢复。
- **原因**：`LLMGateway.init()` 探测 3 次失败后把 `_available` 固化为 `False`，
  此后没有任何重探路径。
- **为什么致命**：AMD 云实例上 llama-server 加载 14B GGUF 到显存需要几十秒甚至数分钟，
  必然晚于后端就绪；docker compose 同时拉起服务时也必然踩中。
  这正是"上云后服务看起来挂了"的典型成因。
- **修复**：`backend/core/llm/gateway.py` 新增 `ensure_available()`，
  带 10 秒节流的惰性重探；`main.py` 的 `/api/health`、
  `agent_routes.py` 的 `/chat` 与 `/generate` 三处改用它。
- **验证**：故意先起后端、12 秒后才起推理端点，
  `llm_available` 由 `false` 自动变 `true`，全程未重启后端。

### BUG-6 流式模式下工作组与角色信息恒为空

- **现象**：`stream_meta` 里 `workgroup` 永远 `null`、`roles_used` 永远 `[]`，
  即便后端日志显示明明命中了 `dev_full` 的 10 步流水线。演示时前端无法展示调度过程。
- **原因**：`MasterRole.dispatch_stream()` 知道命中了哪个工作组，但没往外暴露；
  `BaseAgent.chat_stream()` 直接硬编码 `{"type": "dispatched", "workgroup": None, "roles_used": []}`。
- **修复**：
  - `backend/core/role/master.py` —— `dispatch_stream()` 记录本轮调度到
    `_last_stream_dispatch`，新增 `last_stream_dispatch` 属性
  - `backend/core/agent/base.py` —— 改为读取该属性
- **修复后实测**：`dispatch=workgroup workgroup=完整开发工作组
  roles=['coach','designer','developer','inspector','tester','deployer','cleaner','experience_evaluator']`

---

## 五、环境类问题（只记录，未改代码）

| 问题 | 说明 | 影响 |
| --- | --- | --- |
| 8080 端口被本机 LM Studio 占用 | 请求被转发到 LM Studio，返回 `LM Studio API token is required` | 本地验证改用 `PORT=8088`；云实例上无此冲突 |
| `pip install --upgrade pip` 破坏 venv | 受限环境下回收站不可用导致升级中断，`pip.exe` 损坏 | 改用 `ensurepip --upgrade`，已写入本文档步骤 |
| `vite build` 清理 `dist/` 失败 | 沙箱拦截删除操作，报 `trash operation ... Unknown` | 构建前先手动删除 `frontend/dist`；标准 Docker 环境无此问题 |
| 单卡模式下 `visual_analyzer` 无专用模型 | 启动日志有告警，该角色仍可路由但视觉能力不可用 | 符合预期，非缺陷 |

---

## 六、必须上真 GPU 才能验证的部分

本地假端点覆盖了**协议与链路**，但下列内容无法在无 GPU 环境证伪：

1. **ROCm / llama.cpp 能否成功加载 Qwen2.5-14B-Instruct**
   —— 显存是否够、`--n-gpu-layers` 该给多少、量化档位（Q4_K_M 等）选择。
2. **真实模型是否稳定返回 `tool_calls`**
   —— 假端点是"命中关键词就必定返回工具调用"，真模型受 chat template 和
   prompt 质量影响很大。必须确认 `--jinja` 已生效，否则工具闭环静默失效。
3. **17 角色 / 10 步工作组流水线的端到端耗时**
   —— 每步都要一次 14B 推理，`CLOUD_BENCHMARK.md` 的测速数据只能上真机补。
4. **长上下文与并发下的显存表现**
   —— `--ctx-size` 上限、多 WS 连接并发时是否 OOM。
5. **`setup_amd_cloud.sh` / `start.sh` 在真实云镜像上的可执行性**
   —— 本次验证**未改动**这两个脚本，其中的驱动检测、ROCm 安装分支无法本地触发。
6. **模型输出质量本身**
   —— 假端点返回的是占位文本，角色提示词的实际效果必须真机评估。

---

## 七、变更文件清单

**新增**

- `mock_llm.py` — 假推理端点
- `ws_client.py` — WebSocket 端到端自检脚本
- `backend/Dockerfile`
- `frontend/Dockerfile`
- `frontend/nginx.conf`
- `docker-compose.yml`
- `.dockerignore`、`frontend/.dockerignore`
- `docs/本地验证与Docker模拟.md`（本文件）

**修改（bug 修复）**

- `backend/core/agent/base.py` — BUG-1、BUG-6
- `backend/core/bus.py` — BUG-2
- `backend/api/routes/agent_routes.py` — BUG-2、BUG-3、BUG-5
- `backend/core/agent/registry.py` — BUG-3、BUG-4
- `backend/main.py` — BUG-4、BUG-5
- `backend/core/role/master.py` — BUG-6
- `backend/core/llm/gateway.py` — BUG-5

**未改动（真实部署逻辑保持原样）**

- `setup_amd_cloud.sh`、`start.sh`、`stop.sh`、`install.sh`、根目录 `nginx.conf`
