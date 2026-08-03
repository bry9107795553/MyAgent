<template>
  <div class="chat-view">
    <!-- 左侧 Agent 选择栏 -->
    <aside class="agent-sidebar">
      <div class="sidebar-header">
        <span class="sidebar-title">Agents</span>
        <button class="btn-add" @click="showCreate = !showCreate">+</button>
      </div>
      <div class="agent-list">
        <div
          v-for="agent in agents"
          :key="agent.agent_id"
          class="agent-item"
          :class="{ active: currentAgent === agent.agent_id }"
          @click="selectAgent(agent.agent_id)"
        >
          <div class="agent-name">{{ agent.name }}</div>
          <div class="agent-desc">{{ agent.description }}</div>
        </div>
      </div>
      <div v-if="showCreate" class="create-form">
        <input v-model="newAgent.id" placeholder="Agent ID (英文)" class="input" />
        <input v-model="newAgent.name" placeholder="名称" class="input" />
        <input v-model="newAgent.desc" placeholder="描述" class="input" />
        <textarea v-model="newAgent.prompt" placeholder="系统提示词" class="input textarea"></textarea>
        <button class="btn-create" @click="createAgent">创建</button>
      </div>
    </aside>

    <!-- 中间对话区 -->
    <div class="chat-main">
      <div class="messages" ref="messagesEl">
        <div
          v-for="(msg, i) in messages"
          :key="i"
          class="message"
          :class="msg.role"
        >
          <!-- 角色调度标签 -->
          <div v-if="msg.role === 'assistant' && msg.meta" class="msg-roles">
            <span class="role-pill master">
              <svg width="10" height="10" viewBox="0 0 12 12" fill="none"><circle cx="6" cy="6" r="4" stroke="currentColor" stroke-width="1.2"/><path d="M4 6h4" stroke="currentColor" stroke-width="1"/></svg>
              Master · 调度中心
            </span>
            <span v-if="msg.meta.workgroup" class="role-arrow">→ 已委派至工作组</span>
            <span
              v-for="role in (msg.meta.roles_used || [])"
              :key="role"
              class="role-pill member"
            >{{ role }}</span>
          </div>
          <div class="msg-content" v-html="renderMarkdown(msg.content)"></div>
        </div>
        <div v-if="streaming" class="message assistant">
          <div class="msg-content streaming-cursor" v-html="renderMarkdown(streamBuffer)"></div>
        </div>
      </div>
      <div class="input-bar">
        <div class="input-wrapper">
          <input
            v-model="inputText"
            class="chat-input"
            placeholder="输入消息..."
            @keyup.enter="sendMessage"
            :disabled="streaming"
          />
          <button class="btn-send" @click="sendMessage" :disabled="streaming || !inputText">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M2 7l4-5 4 5M6 2v9" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
          </button>
        </div>
      </div>
    </div>

    <!-- 右侧信息面板 -->
    <div class="right-panel" v-if="currentAgent">
      <div class="panel-tabs">
        <span :class="{ active: activePanelTab === 'preview' }" @click="activePanelTab = 'preview'">预览</span>
        <span :class="{ active: activePanelTab === 'slot' }" @click="activePanelTab = 'slot'">槽位</span>
        <span :class="{ active: activePanelTab === 'artifact' }" @click="activePanelTab = 'artifact'; loadArtifacts()">产物</span>
        <span :class="{ active: activePanelTab === 'history' }" @click="activePanelTab = 'history'">历史</span>
      </div>

      <!-- 预览 -->
      <div v-if="activePanelTab === 'preview'" class="panel-content">
        <div class="panel-section">
          <div class="ps-label">项目状态</div>
          <div class="project-card" v-if="projectStatus">
            <div class="pc-header">
              <span class="pc-name">{{ projectStatus.name }}</span>
              <span class="pc-phase">{{ projectStatus.phase }}</span>
            </div>
            <div class="pc-progress-bar">
              <div class="pc-progress-fill" :style="{ width: projectStatus.progress + '%' }"></div>
            </div>
            <div class="pc-meta">
              <span>{{ projectStatus.completed }}/{{ projectStatus.total }} 模块完成</span>
              <span>{{ projectStatus.progress }}%</span>
            </div>
          </div>
          <div v-else class="panel-empty">暂无项目</div>
        </div>
        <div class="panel-section">
          <div class="ps-label">活跃角色</div>
          <div class="role-list" v-if="activeRoles.length > 0">
            <div v-for="r in activeRoles" :key="r.name" class="role-row">
              <div class="role-avatar" :style="{ background: r.color }">{{ r.name[0] }}</div>
              <div>
                <div class="role-row-name">{{ r.name }}</div>
                <div class="role-row-status">{{ r.status }}</div>
              </div>
            </div>
          </div>
          <div v-else class="panel-empty">等待调度</div>
        </div>
      </div>

      <!-- 槽位 -->
      <div v-if="activePanelTab === 'slot'" class="panel-content">
        <div class="panel-empty">槽位管理 — 开发中</div>
      </div>

      <!-- 产物 -->
      <div v-if="activePanelTab === 'artifact'" class="panel-content">
        <div class="panel-section">
          <div class="ps-label">项目产物</div>
          <div v-if="artifacts.length === 0" class="panel-empty">暂无产物</div>
          <div v-else class="artifact-list">
            <div v-for="a in artifacts" :key="a.id" class="artifact-card">
              <div class="ac-header">
                <svg v-if="a.type === '代码'" width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M3 3l10 5-10 5V3z" stroke="#6366f1" stroke-width="1.5" stroke-linejoin="round"/></svg>
                <svg v-else-if="a.type === '图片'" width="12" height="12" viewBox="0 0 16 16" fill="none"><rect x="2" y="3" width="12" height="10" rx="1.5" stroke="#db2777" stroke-width="1.2"/></svg>
                <svg v-else width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M2 4h12M2 8h12M2 12h8" stroke="#7c3aed" stroke-width="1.5" stroke-linecap="round"/></svg>
                <span class="ac-name">{{ a.name }}</span>
                <span class="ac-type">{{ a.type }}</span>
              </div>
              <div class="ac-actions">
                <span v-if="a.previewable" @click="previewArtifact(a)" class="ac-action">预览</span>
                <a :href="`/api/projects/${projectName}/artifacts/${a.id}/download`" class="ac-action" download>下载</a>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 历史 -->
      <div v-if="activePanelTab === 'history'" class="panel-content">
        <div class="panel-empty">对话历史 — 开发中</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, computed } from 'vue'
import { marked } from 'marked'

const agents = ref([])
const currentAgent = ref('')
const messages = ref([])
const inputText = ref('')
const streaming = ref(false)
const streamBuffer = ref('')
const messagesEl = ref(null)
const showCreate = ref(false)
const newAgent = ref({ id: '', name: '', desc: '', prompt: '' })
const lastMessageMeta = ref(null)
const activePanelTab = ref('preview')
const projectStatus = ref(null)
const activeRoles = ref([])
const artifacts = ref([])
const projectName = ref('')

function renderMarkdown(text) {
  try {
    return marked(text)
  } catch {
    return text
  }
}

async function loadAgents() {
  const res = await fetch('/api/agents')
  const data = await res.json()
  agents.value = data.agents || []
  if (agents.value.length > 0 && !currentAgent.value) {
    selectAgent(agents.value[0].agent_id)
  }
}

function selectAgent(agentId) {
  currentAgent.value = agentId
  messages.value = []
  loadHistory(agentId)
}

async function loadHistory(agentId) {
  try {
    const res = await fetch(`/api/agents/${agentId}/history`)
    const data = await res.json()
    messages.value = data.history || []
    scrollToBottom()
  } catch { /* ignore */ }
}

async function sendMessage() {
  if (!inputText.value || !currentAgent.value) return

  const text = inputText.value
  inputText.value = ''

  messages.value.push({ role: 'user', content: text })
  scrollToBottom()

  streaming.value = true
  streamBuffer.value = ''

  const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${protocol}://${location.host}/api/agents/${currentAgent.value}/ws`)
  ws.onopen = () => {
    ws.send(JSON.stringify({ message: text }))
  }
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.type === 'stream_token') {
      // 过滤可能的 meta JSON 泄露（防御性处理）
      if (!streamBuffer.value && data.content.startsWith('{"type":"meta"')) return
      streamBuffer.value += data.content
      scrollToBottom()
    } else if (data.type === 'stream_end') {
      const meta = lastMessageMeta.value
      messages.value.push({
        role: 'assistant',
        content: streamBuffer.value,
        meta: meta || undefined,
      })
      streamBuffer.value = ''
      lastMessageMeta.value = null
      streaming.value = false
      ws.close()
      // 尝试提取项目名
      detectProjectName(text)
    } else if (data.type === 'stream_meta') {
      lastMessageMeta.value = {
        type: data.dispatch_type,
        workgroup: data.workgroup,
        roles_used: data.roles_used,
      }
      // 更新活跃角色
      if (data.roles_used?.length > 0) {
        const roleColors = {
          'Coach': 'linear-gradient(135deg, #7c3aed, #a78bfa)',
          'Designer': 'linear-gradient(135deg, #db2777, #f472b6)',
          'Developer': 'linear-gradient(135deg, #2563eb, #60a5fa)',
          'Tester': 'linear-gradient(135deg, #059669, #34d399)',
          'Secretary': 'linear-gradient(135deg, #d97706, #fbbf24)',
          'Deployer': 'linear-gradient(135deg, #dc2626, #f87171)',
        }
        activeRoles.value = data.roles_used.map(r => ({
          name: r,
          status: '工作中',
          color: roleColors[r] || 'linear-gradient(135deg, #6366f1, #8b5cf6)',
        }))
      }
    }
  }
  ws.onerror = () => {
    streaming.value = false
    streamBuffer.value = ''
  }
}

function detectProjectName(userMessage) {
  // 简单提取项目名
  const match = userMessage.match(/设计|创建|开发|写|做.*?([\u4e00-\u9fa5]{2,6}(?:网站|网页|应用|系统|App|项目|平台|工具|页面))/)
  if (match) {
    projectName.value = match[1]
    loadProjectStatus()
  }
}

async function loadProjectStatus() {
  if (!projectName.value) return
  try {
    const res = await fetch(`/api/projects/${encodeURIComponent(projectName.value)}`)
    if (res.ok) {
      const data = await res.json()
      projectStatus.value = {
        name: data.name || projectName.value,
        phase: data.current_phase || 'Phase 1',
        progress: Math.round((data.modules?.completed?.length || 0) / Math.max(data.modules?.total || 5, 1) * 100),
        completed: data.modules?.completed?.length || 0,
        total: data.modules?.total || 5,
      }
    }
  } catch { /* ignore */ }
}

async function loadArtifacts() {
  if (!projectName.value) return
  try {
    const res = await fetch(`/api/projects/${encodeURIComponent(projectName.value)}/artifacts`)
    if (res.ok) {
      const data = await res.json()
      artifacts.value = data.artifacts || []
    }
  } catch { /* ignore */ }
}

async function previewArtifact(artifact) {
  try {
    const res = await fetch(`/api/projects/${encodeURIComponent(projectName.value)}/artifacts/${artifact.id}/preview`)
    if (res.ok) {
      const data = await res.json()
      // 在消息区显示预览
      messages.value.push({
        role: 'assistant',
        content: `**📄 ${data.name}**\n\n\`\`\`\n${data.content.slice(0, 2000)}\n\`\`\``,
        meta: null,
      })
      activePanelTab.value = 'preview'
      scrollToBottom()
    }
  } catch { /* ignore */ }
}

async function createAgent() {
  if (!newAgent.value.id || !newAgent.value.name) return
  await fetch('/api/agents', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      agent_id: newAgent.value.id,
      name: newAgent.value.name,
      description: newAgent.value.desc,
      system_prompt: newAgent.value.prompt,
    }),
  })
  showCreate.value = false
  newAgent.value = { id: '', name: '', desc: '', prompt: '' }
  await loadAgents()
}

function scrollToBottom() {
  nextTick(() => {
    if (messagesEl.value) {
      messagesEl.value.scrollTop = messagesEl.value.scrollHeight
    }
  })
}

onMounted(() => {
  loadAgents()
})
</script>

<style scoped>
.chat-view {
  display: flex;
  height: 100%;
}

/* ===== 左侧栏 ===== */
.agent-sidebar {
  width: 200px;
  background: var(--sidebar-bg);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
}

.sidebar-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 1px;
}

.btn-add {
  width: 22px;
  height: 22px;
  border: none;
  border-radius: 6px;
  background: var(--brand-soft);
  color: var(--brand);
  cursor: pointer;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.btn-add:hover {
  background: #ddd6fe;
}

.agent-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px;
}

.agent-item {
  padding: 8px;
  border-radius: var(--radius);
  cursor: pointer;
  margin-bottom: 2px;
  transition: background 0.15s;
  position: relative;
}

.agent-item:hover {
  background: var(--sidebar-active);
}

.agent-item.active {
  background: var(--sidebar-active);
}

.agent-item.active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 6px;
  bottom: 6px;
  width: 3px;
  background: linear-gradient(180deg, #6366f1, #8b5cf6);
  border-radius: 0 3px 3px 0;
}

.agent-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
}

.agent-item.active .agent-name {
  color: var(--brand-dark);
}

.agent-desc {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

.create-form {
  padding: 12px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.input {
  padding: 6px 8px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-size: 12px;
  outline: none;
}

.input:focus {
  border-color: var(--brand);
}

.textarea {
  resize: vertical;
  min-height: 50px;
  font-family: inherit;
}

.btn-create {
  padding: 6px;
  background: var(--brand);
  border: none;
  border-radius: 6px;
  color: white;
  font-size: 12px;
  cursor: pointer;
}

.btn-create:hover {
  background: var(--brand-dark);
}

/* ===== 中间对话区 ===== */
.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--surface-muted);
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.message {
  margin-bottom: 16px;
  max-width: 80%;
}

.message.user {
  margin-left: auto;
}

.msg-roles {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}

.role-pill {
  display: flex;
  align-items: center;
  gap: 3px;
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 10px;
  font-weight: 500;
}

.role-pill.master {
  background: var(--brand-soft);
  color: var(--brand-dark);
  border: 1px solid #c7d2fe;
}

.role-pill.member {
  background: #ede9fe;
  color: #7c3aed;
}

.role-arrow {
  font-size: 10px;
  color: var(--text-muted);
}

.msg-content {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px;
  line-height: 1.6;
}

.message.user .msg-content {
  background: var(--brand);
  color: #fff;
  border-radius: 14px 14px 4px 14px;
  box-shadow: 0 2px 8px rgba(99,102,241,0.2);
}

.message.assistant .msg-content {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 4px 14px 14px 14px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}

.message.assistant .msg-content :deep(pre) {
  background: #1e1e2e;
  color: #cdd6f4;
  padding: 10px;
  border-radius: 6px;
  font-size: 12px;
  overflow-x: auto;
  margin: 8px 0;
}

.message.assistant .msg-content :deep(code) {
  font-family: var(--font-mono);
  font-size: 12px;
}

.streaming-cursor::after {
  content: '▊';
  animation: blink 1s infinite;
  color: var(--brand);
}

@keyframes blink {
  50% { opacity: 0; }
}

/* ===== 输入栏 ===== */
.input-bar {
  padding: 10px 16px;
  border-top: 1px solid var(--border);
  background: var(--surface);
}

.input-wrapper {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--surface-muted);
  border-radius: var(--radius-card);
  border: 1px solid var(--border);
  padding: 3px 3px 3px 14px;
  transition: border-color 0.2s;
}

.input-wrapper:focus-within {
  border-color: var(--brand);
}

.chat-input {
  flex: 1;
  border: none;
  background: none;
  font-size: 13px;
  color: var(--text);
  outline: none;
  padding: 6px 0;
}

.btn-send {
  width: 32px;
  height: 32px;
  border-radius: var(--radius);
  border: none;
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: #fff;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 6px rgba(99,102,241,0.3);
  transition: opacity 0.2s;
}

.btn-send:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  box-shadow: none;
}

/* ===== 右侧面板 ===== */
.right-panel {
  width: 260px;
  background: var(--surface);
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.panel-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
}

.panel-tabs span {
  flex: 1;
  text-align: center;
  padding: 8px 0;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
}

.panel-tabs span:hover {
  color: var(--text);
}

.panel-tabs span.active {
  color: var(--brand);
  border-bottom-color: var(--brand);
  font-weight: 500;
}

.panel-content {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.panel-section {
  margin-bottom: 16px;
}

.ps-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.panel-empty {
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
  padding: 20px 0;
}

/* 项目状态卡片 */
.project-card {
  background: var(--surface-muted);
  border-radius: var(--radius);
  padding: 10px;
}

.pc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.pc-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
}

.pc-phase {
  padding: 1px 6px;
  border-radius: var(--radius-full);
  font-size: 10px;
  font-weight: 500;
  background: #fef3c7;
  color: #d97706;
}

.pc-progress-bar {
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  margin-bottom: 6px;
  overflow: hidden;
}

.pc-progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #6366f1, #8b5cf6);
  border-radius: 2px;
  transition: width 0.3s;
}

.pc-meta {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: var(--text-muted);
}

/* 活跃角色 */
.role-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.role-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  border-radius: var(--radius);
}

.role-row:hover {
  background: var(--surface-muted);
}

.role-avatar {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 10px;
  color: #fff;
  font-weight: 600;
}

.role-row-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
}

.role-row-status {
  font-size: 10px;
  color: var(--text-muted);
}

/* 产物列表 */
.artifact-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.artifact-card {
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.ac-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
}

.ac-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text);
}

.ac-type {
  margin-left: auto;
  padding: 1px 5px;
  border-radius: var(--radius-full);
  font-size: 9px;
  font-weight: 500;
  background: var(--brand-soft);
  color: var(--brand-dark);
}

.ac-actions {
  display: flex;
  gap: 8px;
  padding: 4px 10px;
}

.ac-action {
  font-size: 10px;
  color: var(--brand);
  cursor: pointer;
  text-decoration: none;
}

.ac-action:hover {
  text-decoration: underline;
}
</style>