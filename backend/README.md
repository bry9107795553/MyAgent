# MyAgent — 个人智能助手

2026 AMD AI DevMaster 黑客松 · 赛道二 · 私有 AI Agent 开发与本地部署

基于 AMD Radeon GPU + ROCm 的全本地化私有 AI Agent 平台。核心推理在本地 GPU 上执行，断网可用，所有数据不离开用户机器。

## 核心特性

- **15 角色协作** — 主控按需调度 15 个专业角色（教练、设计师、开发、巡检等），简单任务单角色、复杂任务自动组装工作组
- **Agent = 主控配置壳** — 用户创建 Agent 本质是定制主控的默认人格、可用角色和工具权限，所有对话统一走主控 → 角色调度链路
- **自然语言生成 Agent** — 描述需求，AI 自动生成完整配置并创建 Agent 目录，零代码
- **4 级渐进式记忆** — L0 原文 → L1 轻度摘要 → L2 稠密摘要 → L3 知识三元组，不裁剪只压缩，零数据丢失
- **动态调度系统** — 预设 9 个工作组 + 关键词/语义匹配 + 动态组装，支持 GPU 亲和性并行调度
- **项目状态追踪** — 跨会话项目进度感知，教练维护 PROJECT_STATUS.md，系统重启后自动恢复上下文
- **目录级隔离** — Agent 和角色都是独立文件夹，增删 = 增删文件夹，watchdog 热加载
- **断网可用** — 核心功能全部依赖本地 llama.cpp，断网后对话、Agent 生成、布局编排均可使用

## 快速部署（Radeon Cloud）

```bash
# 1. SSH 登录 Radeon Cloud 实例
ssh user@<your-radeon-cloud-ip>

# 2. 克隆代码
git clone https://github.com/bry9107795553/MyAgent.git
cd MyAgent/myagent

# 3. 一键安装（自动安装所有依赖 + 下载 llama.cpp + GGUF 模型）
bash install.sh

# 4. 启动服务
bash start.sh

# 5. 验证
curl http://localhost/api/health

# 6. 浏览器访问
# http://<your-radeon-cloud-ip>
```

**注意：** Radeon Cloud 实例本身是容器环境，不支持 Docker-in-Docker，因此采用直接安装方式。仓库不包含 Dockerfile 或 docker-compose.yml。

## 前置条件

| 项目 | 要求 |
|------|------|
| GPU | AMD Radeon（支持 ROCm 6.x） |
| 显存 | ≥ 48GB（推荐 W7900D 或 MI300X） |
| 内存 | ≥ 64GB |
| 存储 | ≥ 100GB SSD |
| 系统 | Ubuntu 22.04 LTS |
| ROCm | 已预装（Radeon Cloud 实例通常已预装） |

## 本地开发

```bash
# 后端
cd myagent/backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# 前端（另开终端）
cd myagent/frontend
npm install
npm run dev
```

## 系统架构

```
┌───────────────────────────────────────────────────┐
│  L4 UI 视图层                                      │
│  Vue 3 + GridStack.js + 通用模块渲染器              │
│  · 对话界面 · 工作台编排 · 皮肤仓库                  │
├───────────────────────────────────────────────────┤
│  L3 Agent 配置层（目录隔离 · 主控配置壳）            │
│  data/agents/{agent_id}/                           │
│  · config.yaml → 主控人格、角色池、工具权限           │
│  · prompt.txt  → 覆盖主控默认系统提示词               │
│  · knowledge/  → 知识库 · ui_layout.json → 面板布局  │
├───────────────────────────────────────────────────┤
│  L2 编排层（始终运行 · 用户不可见）                   │
│  FastAPI + WebSocket + 调度器 + 15 角色 + 4 级记忆   │
│  · 主控调度 · 角色协作 · Agent 生成 · 皮肤管理        │
├───────────────────────────────────────────────────┤
│  L1 基座层                                          │
│  llama.cpp + ROCm + Nginx                          │
│  · 本地推理 · GPU 加速 · 单端口暴露                  │
└───────────────────────────────────────────────────┘
```

### 15 角色系统

| 分组 | 角色 | GPU | 模型 | 核心能力 |
|------|------|-----|------|---------|
| 通用 | 主控 (master) | GPU0 | 14B | 调度 / 防火墙 / 汇总 |
| 通用 | 知识检索 (knowledge_retriever) | GPU1 | 7B | RAG / 联网搜索 |
| 通用 | 写作 (writer) | GPU0 | 14B | 报告 / 邮件 / 文案 |
| 通用 | 质检 (quality_checker) | GPU2 | 7B | 事实核查 / 逻辑验证 |
| 通用 | 日程 (scheduler) | GPU1 | 7B | 时间管理 / 冲突检测 |
| 通用 | 创意 (creative) | GPU0 | 14B | 头脑风暴 / 洞察提炼 |
| 通用 | 翻译 (translator) | GPU1 | 7B | 多语言翻译 |
| 通用 | 视觉分析 (visual_analyzer) | GPU1 | VL-7B | 图片分析（多模态） |
| 开发 | 教练 (coach) | GPU0 | 14B | 需求发现 / 教学 / 调度开发团队 |
| 开发 | 设计师 (designer) | GPU0 | 14B | 设计系统 / 多页面样图 |
| 开发 | 开发 (developer) | GPU0 | 14B | 代码实现 / 技术债管理 |
| 开发 | 巡检 (inspector) | GPU2 | 7B | 架构审查 / 技术债识别 |
| 开发 | 测试 (tester) | GPU2 | 7B | tsc / eslint / vitest |
| 开发 | 部署 (deployer) | GPU2 | 7B | 构建 / 部署 / 回滚 |
| 后勤 | 清洁员 (cleaner) | GPU2 | 7B | 文件系统清理 |

每个角色遵循统一的七段式提示词框架：身份 → 职责 → 边界 → 输出 → 标准 → 记忆 → 工具。

### 9 个预设工作组

| 工作组 | 触发关键词 | 流水线 |
|--------|-----------|--------|
| report_writing | 写报告、写文章、写文档 | writer → quality_checker |
| translation_task | 翻译、translate | translator → quality_checker |
| dev_full | 开发、做一个、帮我写一个 | coach → designer → developer → inspector → tester → cleaner |
| dev_design_only | 设计、UI、界面 | coach → designer |
| dev_code_review | 审查、review、检查代码 | inspector |
| dev_tech_debt | 技术债、重构、清理代码 | inspector → cleaner |
| research_investigation | 调研、调查、研究 | knowledge_retriever → writer → quality_checker |
| schedule_planning | 日程、安排、提醒 | scheduler |
| visual_analysis_task | 分析图片、看看这张图 | visual_analyzer → writer |

## 目录结构

```
MyAgent/
├── docs/                          # 项目文档
│   ├── development-plan.md        # 开发规划
│   ├── architecture.md            # 架构详解
│   └── deployment-guide.md        # 部署指南
├── competition-plan/              # 参赛方案 (HTML)
├── PROPOSAL.md                    # 方案书（完整设计文档）
├── myagent/                       # 项目主体
│   ├── backend/                   # FastAPI 后端
│   │   ├── main.py                # 入口，生命周期管理
│   │   ├── config/                # 配置管理
│   │   │   ├── settings.py        # 全局配置 (Pydantic Settings)
│   │   │   └── models.yaml        # 模型配置档案
│   │   ├── core/                  # 核心引擎
│   │   │   ├── agent/             # Agent 管理
│   │   │   │   ├── base.py        # Agent 基类
│   │   │   │   ├── registry.py    # 注册表 + watchdog
│   │   │   │   ├── lifecycle.py   # 生命周期管理
│   │   │   │   ├── agent_schemas.py   # Pydantic 配置校验
│   │   │   │   └── agent_generator.py # LLM 驱动 Agent 生成
│   │   │   ├── llm/               # LLM 网关
│   │   │   │   └── gateway.py     # llama.cpp 连接 + 调用
│   │   │   ├── memory/            # 4 级记忆系统
│   │   │   │   ├── store.py       # JSON 原子读写
│   │   │   │   ├── working_memory.py  # 工作记忆
│   │   │   │   ├── session_memory.py  # 会话记忆
│   │   │   │   ├── archive.py     # 零损失归档
│   │   │   │   ├── compressor.py  # 压缩管线
│   │   │   │   ├── knowledge_base.py  # 知识图谱
│   │   │   │   ├── blackboard.py  # 共享黑板
│   │   │   │   └── exporter.py    # 对话导出 + 脱敏
│   │   │   ├── role/              # 角色系统
│   │   │   │   ├── role_base.py   # 角色基类
│   │   │   │   ├── loader.py      # 角色加载 + 七段式提示词
│   │   │   │   └── master.py      # 主控调度器
│   │   │   ├── project/           # 项目状态追踪
│   │   │   │   └── project_status.py
│   │   │   ├── module_engine/     # 模块生成引擎
│   │   │   ├── skin/              # 皮肤系统
│   │   │   └── tools/             # 工具系统
│   │   ├── api/routes/            # API 路由
│   │   ├── bus.py                 # WebSocket 消息总线
│   │   └── requirements.txt       # Python 依赖
│   ├── frontend/                  # Vue 3 前端
│   │   ├── src/
│   │   │   ├── views/             # ChatView, WorkbenchView, SkinMarketView
│   │   │   ├── components/        # ModuleRenderer
│   │   │   └── stores/            # Pinia 状态管理
│   │   ├── package.json
│   │   └── vite.config.js
│   ├── data/                      # 运行时数据
│   │   ├── role_pool.json         # 15 角色定义
│   │   ├── dispatcher_config.json # 调度器配置
│   │   ├── agents/                # Agent 目录（种子：general_assistant）
│   │   ├── templates/             # 6 种 Agent 模板
│   │   ├── workgroups/            # 9 个预设工作组
│   │   ├── skins/                 # 3 套皮肤配置
│   │   └── memory/                # 记忆存储（archive/cache/sessions）
│   ├── tests/                     # 测试脚本
│   │   └── offline_test.sh        # 离线测试
│   ├── nginx.conf                 # Nginx 反向代理
│   ├── install.sh                 # 一键安装脚本
│   ├── start.sh                   # 启动脚本
│   └── stop.sh                    # 停止脚本
└── notebooks/                     # Jupyter notebooks
```

## 服务管理

```bash
# 安装（首次）
bash install.sh

# 启动
bash start.sh

# 停止
bash stop.sh

# 查看日志
tail -f /tmp/llama.log      # llama-server
tail -f /tmp/backend.log    # FastAPI

# 离线测试
bash tests/offline_test.sh
```

### 验证部署

| 检查项 | 命令 | 预期结果 |
|--------|------|---------|
| 健康检查 | `curl http://localhost/api/health` | `{"status":"ok","llm_available":true}` |
| 模型可用 | `curl http://localhost:8000/v1/models` | 返回模型列表 |
| 对话测试 | `curl -X POST http://localhost/v1/chat/completions ...` | 正常回复 |
| 前端访问 | 浏览器打开 `http://<IP>` | MyAgent 界面 |

## 技术栈

| 层 | 技术 | 说明 |
|---|---|---|
| L1 基座 | llama.cpp + ROCm 7.2 | AMD GPU 本地推理，Qwen2.5-14B/7B GGUF |
| L1 基座 | Nginx | 单端口反向代理，80 端口统一访问 |
| L2 编排 | FastAPI | API + WebSocket + Agent 调度 |
| L2 编排 | Pydantic | 配置校验 + 数据模型 |
| L2 编排 | watchdog | Agent 目录热加载 |
| L3 实例 | YAML/JSON 配置 | 每个 Agent 独立目录，配置即 Agent |
| L4 UI | Vue 3 + Vite | 前端框架 |
| L4 UI | GridStack.js | 面板拖拽编排 |
| L4 UI | Pinia | 状态管理 |
| 模型 | Qwen2.5-14B-Instruct (GGUF q4_k_m) | 主推理模型，GPU0 |
| 模型 | Qwen2.5-7B (GGUF q4_k_m) | 辅推理模型，GPU1/GPU2 |
| 模型 | Qwen2.5-VL-7B | 多模态视觉模型，GPU1 |

## 关键设计决策

- **Agent = 主控配置壳**：用户创建 Agent 本质是定制主控的默认人格和可用角色，所有对话统一走主控 → 角色调度链路
- **角色永不直接通信**：主控作为信息防火墙，角色间通过黑板发布/订阅，禁止直连
- **记忆零损失**：压缩前先归档原始消息，压缩管线只用于 LLM 上下文注入
- **直接安装，不用 Docker**：Radeon Cloud 容器环境不支持 Docker-in-Docker
- **llama.cpp 版本 b9859**：兼容 ROCm 7.2，预编译二进制零编译部署

## License

MIT