# MyAgent 项目状态报告
## 2026-08-05 21:40

---

## 一、项目是什么

**MyAgent** — 基于 AMD Radeon GPU + ROCm 的私有 AI Agent 平台，参加 2026 AMD AI DevMaster 黑客松赛道二。

- 后端：FastAPI + WebSocket，18 个角色编排系统
- 前端：Vue 3 + Vite
- 推理：llama.cpp + Qwen2.5-14B Q4_K_M GGUF
- 部署：Radeon Cloud · W7900 48GB · ROCm 7.2

---

## 二、已完成的改造（代码层面）

全部 commit 在本地 Git 仓库 `D:\MyAgent-main`，未 push 到 GitHub。

| 改造 | 说明 | 状态 |
|------|------|:---:|
| **Plan A — prompt 精简** | 18 份角色 prompt 从 38,190 字压到 15,317 字 (−60%) | ✅ 已提交 |
| **Plan C — 记忆系统** | 经验效用评分 + 知识保质期 TTL + 经验评估员角色 | ✅ 已提交 |
| **P0 单卡模式修复** | `single_gpu_mode` 默认 True，三层防御，防止多卡路由炸 | ✅ 已提交 |
| **工具调用闭环** | `file_write`/`file_read` 等工具真落盘，developer 角色可用 | ✅ 已提交 |
| **云端 Nginx 修复** | 301 重定向 bug + rc-tunnel 端口限制绕过 | ✅ 已部署 |
| **/api/system 端点** | 返回 18 角色 + 10 工作组 + GPU 状态 | ✅ 已部署 |
| **前端阅览面板** | BrowserView.vue — 文件浏览器 + 项目 + 工作组 | ✅ 已部署 |
| **错误信息修复** | master.py "没有合适角色" → "角色执行失败" | ✅ 已部署 |

---

## 三、云端当前状态

- **公网地址**：https://rc-83305f57d63fc9d3.radeon.firstdg.ai
- **隧道**：rc-tunnel (PID 8192)，空闲 60 秒回收
- **三服务**：llama-server :8000 / FastAPI :8080 / Nginx :8088
- **后端**：/api/health ✅ / /api/system ✅ (18 角色 10 工作组) / /api/agents ✅
- **Nginx**：/api/ 通用代理已配好，端口 8088 ✅

---

## 四、就差一步！ChatView.vue 三栏界面

**问题**：前端构建用的是旧的两栏 ChatView，没有三栏（左面板 + 对话 + 产出区）。

**根因**：我写了三栏的 ChatView.vue 但推送过程一直失败——Python heredoc bash 感叹号转义问题。

**修法（三选一）**：

### 方法 1（推荐）：JupyterLab 上传
1. 打开 Radeon Cloud JupyterLab
2. 左侧文件浏览器双击 `frontend` → `src` → `views`
3. 把本地 `D:\MyAgent-main\frontend\src\views\ChatView.vue` 拖进去覆盖
4. 终端跑：
```bash
cd /workspace/template-repos/template-2603/repo/frontend && rm -rf dist && npx vite build && cp -r dist/* /var/www/myagent/
```

### 方法 2：Python 写入（不用上传）
```bash
cd /workspace/template-repos/template-2603/repo && python3 << 'PYEOF'
# 先写模板部分（无感叹号）
tpl='<template><div class="ap"><aside class="lp"><div class="sb" :class="{on: llm}" @click="ss=!ss"><span class="sd"></span><span class="st">{{llm?mn:"离线"}}</span></div><div v-if="ss" class="su">{{roles.length}}角色 {{wgs.length}}组</div><div class="se"><div class="sh">智能体</div><div v-for="a in ag" :key="a.agent_id" :class="[ai,{ac:cur===a.agent_id}]" @click="sel(a.agent_id)"><span>🤖</span><span>{{a.name}}</span></div></div><div class="se"><div class="sh" @click="wo=!wo">工作组 {{wo?"▴":"▾"}}</div><div v-if="wo" v-for="w in wgs" :key="w.id" class="wr" @click="tw(w)">{{w.name}}<span class="ws">{{w.pipeline_steps}}步</span></div></div><div class="se" style="flex:1"><div class="sh" @click="ro=!ro">角色 ({{roles.length}})</div><div v-if="ro" v-for="(g,k) in rg" :key="k"><div class="gl">{{gl[k]||k}}</div><div v-for="r in g" :key="r.id" class="rr"><span class="rd" :class="g-+r.gpu_affinity"></span>{{r.name}}</div></div></div></aside><div class="cm"><div class="ms" ref="me"><div v-if="ms.length===0&&!st" class="em"><div class="ei">💬</div><div class="et">MyAgent</div><div class="ps"><span class="p" @click="sq(\'我想要做程序开发\')">程序开发</span><span class="p" @click="sq(\'审查代码\')">代码审查</span></div></div><div v-for="(m,i) in ms" :key="i" :class="[mg,m.role]"><div class="bb" v-html="md(m.content)"></div></div><div v-if="st" class="mg assistant"><div class="bb">{{bf}}<span class="cr">|</span></div></div></div><div class="ib"><input v-model="tx" class="in" @keyup.enter="sn" :disabled="st" placeholder="输入消息..."/><button class="bt" @click="sn" :disabled="st||!tx">发送</button></div></div><aside class="rp"><div class="rh"><span class="rb" :class="pl?\'act\':\'idle\'">{{pl?"执行中":"就绪"}}</span>产出区</div><div class="rb2"><div v-for="(s,i) in ds" :key="i" :class="[stp,{dn:s.s===1,ac:s.s===2,fa:s.s===3}]" @click="sel2=i"><span class="sd2">{{s.s===1?"V":s.s===2?"O":s.s===3?"X":i+1}}</span><span>{{s.role}}</span></div></div><div v-if="sel2!=null&&ds[sel2]&&ds[sel2].out" class="sd3"><div class="dh">{{ds[sel2].role}}产出</div><div class="db" v-html="md(ds[sel2].out||\'\')"></div></div></aside></div></template>\n'
open('frontend/src/views/ChatView.vue','w').write(tpl)
print('template written',len(tpl))
PYEOF
```

然后构建：
```bash
cd /workspace/template-repos/template-2603/repo/frontend && rm -rf dist && npx vite build && cp -r dist/* /var/www/myagent/
```

### 方法 3：如果上面都失败
用本地 Chạy`D:\MyAgent-main\frontend\src\views\ChatView.vue` 上传**整个 frontend 目录到正确的 views 路径**。确认 `wc -l src/views/ChatView.vue` 返回 300+ 行而非 200 行。

---

## 五、三栏界面建好后长什么样

```
┌──────────┬──────────────────────┬───────────┐
│ 🟢 在线   │  💬 MyAgent          │ 就绪 产出区│
│          │                      │           │
│ 智能体    │ [程序开发][代码审查]  │ ① coach   │
│ 🤖通用助手│                      │ ② designer│
│          │ 用户: 想要做程序开发   │ ③ develop │
│ 工作组 ▴  │ [dev_full 完整开发]   │ ...       │
│ 完整开发 9步│ coach→designer→...  │           │
│ 代码审查 5步│ ✓ 10步完成          │ 点击看产出 │
│ ...      │                      │           │
│ 角色(18)▾ │ [输入...]     [发送]  │           │
└──────────┴──────────────────────┴───────────┘
```

---

## 六、还没做的（留给下个对话）

### 比赛截止前优先级：
1. 🔴 **A/B 测速** — CLOUD_BENCHMARK 表是空的，对应 20 分速度分。需在云端跑 30 次 dev_full，采集 prompt_tokens / TTFT 数据
2. 🔴 **演示视频** — 3-5 分钟，必交项
3. 🟡 **PPT / 架构图**
4. 🟡 **Git push** — 5+ commits 在本地
5. 🟡 **英文 README 最后的 Team 信息** — 还是占位符

### 后续改进（非紧急）：
- Plan B：裁掉 6 个非编制角色让流水线更干净
- Secretary 孤儿文件修复
- dispatcher_config 里的 experience_evaluator 补上了但需重启生效

---

## 七、云端常用命令速查

```bash
# 重启全部
cd /workspace/template-repos/template-2603/repo && bash stop.sh && bash start.sh

# 重建前端
cd /workspace/template-repos/template-2603/repo/frontend && rm -rf dist && npx vite build && cp -r dist/* /var/www/myagent/

# 重开隧道（换 URL）
rc-tunnel stop && sleep 2 && nohup rc-tunnel expose --port 8088 > /tmp/rc-tunnel.log 2>&1 & sleep 3 && cat /tmp/rc-tunnel.log

# 检查后端
curl http://localhost:8080/api/system
curl http://localhost:8080/api/health

# 看日志
tail -f /tmp/backend.log
tail -f /tmp/llama.log
```
