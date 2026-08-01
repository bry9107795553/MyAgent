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
      <!-- 创建 Agent -->
      <div v-if="showCreate" class="create-form">
        <input v-model="newAgent.id" placeholder="Agent ID (英文)" class="input" />
        <input v-model="newAgent.name" placeholder="名称" class="input" />
        <input v-model="newAgent.desc" placeholder="描述" class="input" />
        <textarea v-model="newAgent.prompt" placeholder="系统提示词" class="input textarea"></textarea>
        <button class="btn-create" @click="createAgent">创建</button>
      </div>
    </aside>

    <!-- 右侧对话区 -->
    <div class="chat-main">
      <div class="messages" ref="messagesEl">
        <div
          v-for="(msg, i) in messages"
          :key="i"
          class="message"
          :class="msg.role"
        >
          <div class="msg-content" v-html="renderMarkdown(msg.content)"></div>
          <div v-if="msg.role === 'assistant' && msg.meta?.type === 'workgroup'" class="msg-meta">
            <span class="workgroup-tag" :title="'使用角色: ' + (msg.meta.roles_used || []).join(', ')">
              {{ msg.meta.workgroup }}
            </span>
          </div>
        </div>
        <div v-if="streaming" class="message assistant">
          <div class="msg-content streaming-cursor">{{ streamBuffer }}</div>
        </div>
      </div>
      <div class="input-bar">
        <input
          v-model="inputText"
          class="chat-input"
          placeholder="输入消息..."
          @keyup.enter="sendMessage"
          :disabled="streaming"
        />
        <button class="btn-send" @click="sendMessage" :disabled="streaming || !inputText">
          {{ streaming ? '生成中...' : '发送' }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
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
const lastMessageMeta = ref(null)  // 最近一次调度的元数据

// Markdown 渲染
function renderMarkdown(text) {
  try {
    return marked(text)
  } catch {
    return text
  }
}

// 加载 Agent 列表
async function loadAgents() {
  const res = await fetch('/api/agents')
  const data = await res.json()
  agents.value = data.agents || []
  if (agents.value.length > 0 && !currentAgent.value) {
    selectAgent(agents.value[0].agent_id)
  }
}

// 选择 Agent
function selectAgent(agentId) {
  currentAgent.value = agentId
  messages.value = []
  loadHistory(agentId)
}

// 加载对话历史
async function loadHistory(agentId) {
  try {
    const res = await fetch(`/api/agents/${agentId}/history`)
    const data = await res.json()
    messages.value = data.history || []
    scrollToBottom()
  } catch {
    // 忽略错误
  }
}

// 发送消息 (WebSocket 流式)
async function sendMessage() {
  if (!inputText.value || !currentAgent.value) return

  const text = inputText.value
  inputText.value = ''

  // 显示用户消息
  messages.value.push({ role: 'user', content: text })
  scrollToBottom()

  // 流式接收
  streaming.value = true
  streamBuffer.value = ''

  const ws = new WebSocket(`ws://${location.host}/api/agents/${currentAgent.value}/ws`)
  ws.onopen = () => {
    ws.send(JSON.stringify({ message: text }))
  }
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.type === 'stream_start') {
      // 开始
    } else if (data.type === 'stream_token') {
      streamBuffer.value += data.content
      scrollToBottom()
    } else if (data.type === 'stream_end') {
      // 将元数据附加到本条消息
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
    } else if (data.type === 'stream_meta') {
      // 接收调度元数据 (type, workgroup, roles_used)
      lastMessageMeta.value = {
        type: data.dispatch_type,
        workgroup: data.workgroup,
        roles_used: data.roles_used,
      }
    }
  }
  ws.onerror = () => {
    streaming.value = false
    streamBuffer.value = ''
  }
}

// 创建 Agent
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

// 滚动到底部
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

.agent-sidebar {
  width: 260px;
  background: var(--bg-1);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px;
  border-bottom: 1px solid var(--border);
}

.sidebar-title {
  font-size: 13px;
  color: var(--text-2);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.btn-add {
  width: 24px;
  height: 24px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--text-2);
  cursor: pointer;
  font-size: 16px;
  line-height: 1;
}

.btn-add:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.agent-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.agent-item {
  padding: 10px 12px;
  border-radius: 8px;
  cursor: pointer;
  margin-bottom: 4px;
  transition: background 0.2s;
}

.agent-item:hover {
  background: rgba(255,255,255,0.04);
}

.agent-item.active {
  background: rgba(108,92,231,0.12);
}

.agent-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-0);
}

.agent-desc {
  font-size: 12px;
  color: var(--text-2);
  margin-top: 2px;
}

.create-form {
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.input {
  padding: 8px 10px;
  background: var(--bg-0);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text-0);
  font-size: 13px;
  outline: none;
}

.input:focus {
  border-color: var(--accent);
}

.textarea {
  resize: vertical;
  min-height: 60px;
}

.btn-create {
  padding: 8px;
  background: var(--accent);
  border: none;
  border-radius: 6px;
  color: white;
  font-size: 13px;
  cursor: pointer;
}

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.messages {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}

.message {
  margin-bottom: 16px;
  max-width: 80%;
}

.message.user {
  margin-left: auto;
}

.msg-content {
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.6;
}

.message.user .msg-content {
  background: var(--accent);
  color: white;
}

.message.assistant .msg-content {
  background: var(--bg-1);
  border: 1px solid var(--border);
}

.msg-meta {
  margin-top: 4px;
  padding-left: 12px;
}

.workgroup-tag {
  display: inline-block;
  padding: 2px 8px;
  background: rgba(108, 92, 231, 0.12);
  border: 1px solid rgba(108, 92, 231, 0.25);
  border-radius: 10px;
  font-size: 11px;
  color: var(--accent);
  cursor: default;
}

.streaming-cursor::after {
  content: '▊';
  animation: blink 1s infinite;
}

@keyframes blink {
  50% { opacity: 0; }
}

.input-bar {
  display: flex;
  gap: 8px;
  padding: 16px 24px;
  border-top: 1px solid var(--border);
}

.chat-input {
  flex: 1;
  padding: 10px 14px;
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-0);
  font-size: 14px;
  outline: none;
}

.chat-input:focus {
  border-color: var(--accent);
}

.btn-send {
  padding: 10px 20px;
  background: var(--accent);
  border: none;
  border-radius: 8px;
  color: white;
  font-size: 14px;
  cursor: pointer;
  transition: opacity 0.2s;
}

.btn-send:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
