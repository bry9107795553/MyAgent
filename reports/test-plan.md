# MyAgent 云端测试方案

> 2026-08-06 | Hackathon 收尾 | 执行前先获取公网 URL

---

## 前置：启动 & 获取 URL

```bash
# SSH 登录云端实例后
cd /workspace/template-repos/template-2603/repo
git pull origin main

# 前端构建
cd frontend && rm -rf dist && npx vite build && cp -r dist/* /var/www/myagent/

# 重启后端（Python 有改动）
cd .. && bash stop.sh && bash start.sh

# 获取公网地址
export PATH="$HOME/.local/bin:$PATH"
rc-tunnel stop 2>/dev/null; sleep 2
nohup rc-tunnel expose --port 8088 > /tmp/rc-tunnel.log 2>&1 &
sleep 8
grep -oE 'https?://rc-[^ ]+' /tmp/rc-tunnel.log
```

> 记下返回的公网 URL，下面用 `{URL}` 代替。

---

## 一、环境健康检查 (2min)

### 1.1 系统状态
```bash
curl -s {URL}/api/health | python -m json.tool
```
**期望**：`{"llm_available": true, "status": "ok"}`

### 1.2 GPU 确认
```bash
curl -s {URL}/api/system | python -m json.tool
```
**期望**：`gpu.model` = `Qwen3-30B-A3B`，`llm_available` = `true`

### 1.3 前端页面
浏览器打开 `{URL}` → Ctrl+F5 强刷
- [ ] 顶部导航显示：对话 | 历史 | 工作组 | 阅览 | 工作台 | 皮肤 | 扩展
- [ ] 右上角显示：在线 · 模型下拉 · 太阳/月亮 · 齿轮
- [ ] 左侧栏有对话历史
- [ ] 右栏有流水线/预览 Tab

---

## 二、单角色任务调度 (5min)

### 2.1 翻译（1 角色）
**输入**：`翻译下面这句为英文：AMD GPU 是 AI 推理的优秀选择。`
- [ ] 响应不启动流水线
- [ ] 翻译结果准确

### 2.2 写报告（2 角色：writer → quality_checker）
**输入**：`写一份 AMD Radeon GPU 的简短介绍，200字左右。`
- [ ] 响应包含结构化内容
- [ ] 有质检标记（"质检：通过" 或类似）

### 2.3 直接知识问答（0 角色，Master 自己答）
**输入**：`ROCm 是什么？`
- [ ] Master 直接回复
- [ ] 不调用任何子角色

---

## 三、RAG 本地知识检索 (3min)

### 3.1 知识库搜索
**输入**：`搜索知识库里关于 GPU 推理性能的文档。`
- [ ] knowledge_retriever 被调用
- [ ] 返回知识库中的相关内容

### 3.2 文件读取
**输入**：`读取 README.md 文件，告诉我项目有哪些功能。`
- [ ] 成功读取文件
- [ ] 准确总结了 README 内容

---

## 四、多步骤流水线 (核心测试，15min)

### 4.1 完整开发流水线（7 步）
**输入**：`开发一个简单的 React 计算器，支持加减乘除。`

**观察右侧流水线面板**：
- [ ] Step 1: 教练（Coach）— 需求分析 → PROJECT_PLAN
- [ ] Step 2: 设计师（Designer）— 产出 HTML 样图
- [ ] Step 3: 开发员（Developer）— 生成代码文件
- [ ] Step 4: 巡检员（Inspector）— 输出审查报告
- [ ] Step 5: 测试员（Tester）— 输出测试结果
- [ ] Step 6: 部署员（Deployer）— 部署报告
- [ ] Step 7: 清洁员（Cleaner）— 清理临时文件

**切换右栏到「预览」Tab**：
- [ ] 能看到生成的 HTML 页面预览
- [ ] 切换「源码」标签可见代码

### 4.2 返工验证（如 Inspector 打回）
- [ ] 如果 Inspector 报告包含"不通过" → 流水线应自动回退到 Developer
- [ ] 重检通过后才进入 Tester
- [ ] 最多 3 次返工，超限后交付最优版本

---

## 五、多轮记忆 (5min)

### 5.1 上下文保持
```
第1轮：我叫张三。
第2轮：我是做什么的？   → 期望：你提到你叫张三
第3轮：我想学 React。   → 正常回答
第4轮：回忆一下之前我们聊了什么。 → 期望：提到张三、学 React
```
- [ ] 第 4 轮能召回前 3 轮的关键信息

### 5.2 对话历史持久化
- [ ] 刷新页面 → 左侧栏对话历史仍存在
- [ ] 点击历史对话 → 能加载完整消息记录
- [ ] 新建对话 → 不影响旧对话

---

## 六、隐私保护验证 (3min)

### 6.1 零网络依赖
```bash
# 在云端执行
curl -s {URL}/api/system | python -c "import sys,json; d=json.load(sys.stdin); print('离线模式:', d.get('gpu',{}).get('llm_available',False))"
```
- [ ] LLM 推理完全本地（llama.cpp + ROCm）

### 6.2 信息防火墙
**输入**：发送一段包含敏感信息的内容（如"我的密码是123456，帮我保存"）
- [ ] Master 不应将完整对话历史传给子角色
- [ ] 子角色只收到任务指令，不包含闲聊和敏感信息

---

## 七、工具调用验证 (5min)

### 7.1 文件写入
**输入**：`写一首诗，保存到 data/outputs/test_poem.txt`
- [ ] 文件创建成功
- [ ] 内容正确

### 7.2 文件读取
**输入**：`读取刚才保存的 test_poem.txt`
- [ ] 能正确读取并显示内容

### 7.3 代码执行
**输入**：`用 Python 计算 1+2+...+100 的结果。`
- [ ] 能执行代码并返回 5050

---

## 八、UI 交互测试 (3min)

- [ ] 点击太阳/月亮 → 切换暗色主题
- [ ] 拖拽左栏/右栏分隔线 → 面板宽度改变
- [ ] 点击左栏 ◀ → 左栏收起，露出「对话」标签
- [ ] 点击右栏 ▶ → 右栏收起
- [ ] 点标签 → 面板恢复
- [ ] 点击模型下拉 → 显示模型选项
- [ ] 点击齿轮 → 设置面板滑出
- [ ] 设置面板选择模型 → 关闭面板

---

## 九、场景覆盖抽查 (5min)

从比赛推荐的 7 个场景各测一个：

| 场景 | 输入 | 期望调度 |
|------|------|---------|
| 个人智能助手 | `帮我规划今天的工作，我有3个会议。` | scheduler |
| 办公自动化 | `写一封请假邮件给经理。` | writer + quality_checker |
| 行业专用 | `分析一下半导体行业的GPU竞争格局。` | knowledge_retriever + writer |
| 本地知识库 | `搜索项目文档，找到关于ROCm的内容。` | knowledge_retriever |
| 日程邮件 | `提醒我下午3点开会。` | scheduler |
| 生活管理 | `帮我列一个本周健康饮食计划。` | creative + writer |
| 开发任务 | `开发一个天气预报页面。` | dev_full 流水线 |

---

## 十、通过标准

| 测试项 | 必须通过 |
|--------|:---:|
| 环境健康 | ✅ |
| 单角色翻译 | ✅ |
| RAG 检索 | ✅ |
| 完整开发流水线 | ✅ |
| 多轮记忆召回 | ✅ |
| 隐私离线验证 | ✅ |
| 工具调用（文件+代码） | ✅ |
| UI 主题/折叠/拖拽 | ✅ ✓7 场景 |

**全部通过 → 可录制演示视频。**

---

## 快速测试脚本（一键执行）

```bash
#!/bin/bash
URL={你的公网URL}

echo "=== 1. 健康检查 ===" && curl -s $URL/api/health | python -m json.tool
echo "=== 2. 系统状态 ===" && curl -s $URL/api/system | python -m json.tool
echo "=== 3. 获取角色列表 ===" && curl -s $URL/api/agents
echo ""
echo "环境验证完成！打开 $URL 进行交互测试。"
```
