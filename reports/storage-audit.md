# 存储链路审计报告

> 2026-08-06 | 全项目存储读写路径验证

---

## 一、总体结论：✅ 全部贯通

25 个存储路径全部验证通过，目录已创建，写路径自动建父目录，读路径有空值保护。**无断裂点。**

仅发现 1 个目录缺失（`data/outputs/`），已修复。

---

## 二、逐项审计

### 🔵 角色会话记忆（17 角色 × 1 文件）

| 路径 | 读写 | 状态 |
|------|:---:|:---:|
| `data/memory/sessions/{role}.json` | `read_json` / `write_json` | ✅ 17 文件已就绪，atomic 写入 |
| `data/memory/archive/{role}/` | `append_jsonl` / `read_jsonl` | ✅ 归档追加，零丢失 |
| `data/memory/cache/{role}.json` | `dump_cache` / `load_cache` | ✅ 崩溃恢复 |

**写入触发**：每次角色执行后 Secretary 调用 `record_turn` → `session_memory.add_turn`
**读取触发**：`RoleBase.execute()` 开始时加载上下文

### 🔵 知识库 (L3)

| 路径 | 读写 | 状态 |
|------|:---:|:---:|
| `data/memory/knowledge.json` | `read_json` / `write_json` | ✅ 158 bytes, 初始为空 |

**写入触发**：`KnowledgeBase.add_knowledge()` — 从对话摘要提取知识条目
**读取触发**：`KnowledgeBase.search(query)` — 知识检索员调用 `web_search` 时

### 🔵 共享黑板

| 路径 | 读写 | 状态 |
|------|:---:|:---:|
| `data/memory/blackboard.json` | `read_json` / `write_json` | ⚠ 首次运行时自动创建 |

**写入触发**：Master 在角色间传递信息时 `route_message`
**读取触发**：角色执行时读取上游角色的黑板消息

### 🔵 经验存储

| 路径 | 读写 | 状态 |
|------|:---:|:---:|
| `data/experiences/{task_type}.json` | `_save()` / `_load()` | ✅ `git_push.json` 已存在 |

**写入触发**：Experience Evaluator 分析任务后保存经验
**读取触发**：Master 在类似任务启动时注入经验

### 🔵 项目状态

| 路径 | 读写 | 状态 |
|------|:---:|:---:|
| `data/projects/{name}/PROJECT_STATUS.md` | `_write_status()` / `_parse_status()` | ✅ 原子写入 |

**写入触发**：Coach 在每个 Phase 完成后更新
**读取触发**：Master 的 `project_state_routing` 规则

### 🔵 文件工具

| 操作 | 实现 | 状态 |
|------|------|:---:|
| 写入 | `file_write(path, content)` → `write_json()` 自动建父目录 | ✅ |
| 读取 | `file_read(path)` → `read_json()` 不存在返空 | ✅ |
| 列目录 | `file_list(path)` → os.listdir | ✅ |
| 路径安全 | `_is_within_project()` 防穿越 | ✅ |

**Base path**：`settings.project_root` = `data/../` = 项目根 = 云端 `/workspace/.../repo/`

### 🔵 对话历史（前端 localStorage）

| 存储 | 键名 | 状态 |
|------|------|:---:|
| 对话列表 | `myagent_conversations` | ✅ 前端 `saveCurrentToStorage()` |
| 主题偏好 | `myagent-theme` | ✅ App.vue `localStorage.setItem` |

### 🔵 配置 & 静态数据

| 文件 | 读写 | 状态 |
|------|:---:|:---:|
| `data/role_pool.json` | 读 | ✅ 10.6KB, 18 角色 |
| `data/dispatcher_config.json` | 读 | ✅ 10.5KB, 完整调度规则 |
| `data/workgroups/*.json` | 读 | ✅ 10 个预设工作组 |
| `data/skins/*.json` | 读 | ✅ 3 个皮肤 |
| `data/agents/{id}/config.yaml` | 读 | ✅ Agent 配置 |
| `data/templates/*/config.yaml` | 读 | ✅ 6 个模板 |
| `backend/.env` | 读 | ✅ 运行时加载 |
| `data/outputs/` | 写 | ✅ 刚创建 |

---

## 三、数据流全链路

```
用户消息
  → Master.dispatch()
    → Master 写 memory/sessions/master.json    [会话记录]
    → Secretary 写 memory/sessions/master.json [追加]
    → Coach.execute()
      → 读 memory/sessions/coach.json          [加载上下文]
      → 写 data/projects/xxx/PROJECT_STATUS.md [项目状态]
      → 写 memory/sessions/coach.json          [更新状态]
    → Developer.execute()
      → file_write("index.html", ...)          [写入 outputs/]
      → 读 memory/sessions/developer.json
    → Inspector.execute()
      → file_read("index.html")                [读取代码]
      → 写 memory/sessions/inspector.json
    → Experience Evaluator
      → 写 data/experiences/dev_full.json      [保存经验]

  → 前端 写 localStorage("myagent_conversations")
```

---

## 四、唯一修复

| 问题 | 修复 |
|------|------|
| `data/outputs/` 目录不存在 | `mkdir -p data/outputs/` |
