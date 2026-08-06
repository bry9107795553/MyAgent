<template>
  <div class="main">
    <!-- 左栏：对话历史 -->
    <aside class="sidebar" :class="{ collapsed: sidebarCollapsed }" ref="sidebarEl">
      <div class="panel-tab-hint" v-if="sidebarCollapsed" @click="sidebarCollapsed = false">对话</div>
      <div class="sidebar-header">
        <span class="sidebar-label">对话</span>
        <button class="sidebar-new" @click="newConversation">
          <svg width="12" height="12" viewBox="0 0 14 14" fill="none"><path d="M7 2v10M2 7h10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
        </button>
      </div>
      <div class="conv-list" v-if="!sidebarCollapsed">
        <div v-for="conv in conversationList.slice(0, 100)" :key="conv.id" class="conv-item" :class="{active: currentConversation?.id === conv.id}" @click="loadConversation(conv)">
          <div class="conv-icon"><svg viewBox="0 0 24 24" fill="none" width="12" height="12"><path d="M21 11.5a8.38 8.38 0 01-.9 3.8 8.5 8.5 0 01-7.6 4.7 8.38 8.38 0 01-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 01-.9-3.8 8.5 8.5 0 014.7-7.6 8.38 8.38 0 013.8-.9h.5a8.48 8.48 0 018 8v.5z" stroke="currentColor" stroke-width="1.6"/></svg></div>
          <div class="conv-body"><div class="conv-title">{{ conv.title || '未命名对话' }}</div><div class="conv-meta">{{ (conv.messages||[]).length }} 条 · {{ formatTime(conv.updated_at) }}</div></div>
          <button class="conv-delete" @click.stop="deleteConvById(conv.id)"><svg width="11" height="11" viewBox="0 0 12 12" fill="none"><path d="M3 3l6 6M3 9l6-6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg></button>
        </div>
      </div>
    </aside>

    <!-- 拖拽手柄 -->
    <div class="drag-handle" ref="dragLeft" @mousedown="startDrag('left', $event)">
      <button class="drag-collapse" @click="sidebarCollapsed = true" v-if="!sidebarCollapsed">
        <svg viewBox="0 0 24 24" fill="none" width="8" height="8"><path d="M15 18l-6-6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
    </div>

    <!-- 对话区 -->
    <div class="chat-col">
      <div class="messages" ref="msgEl">
        <div class="msg-wrap">
          <div v-if="messages.length===0 && !streaming" class="empty">
            <div class="empty-glow">
              <svg viewBox="0 0 24 24" fill="none" width="24" height="24"><path d="M12 2L2 7l10 5 10-5-10-5z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>
            </div>
            <div class="empty-title">开始对话</div>
            <div class="empty-sub">输入消息，或从「工作组」选择自动化流水线</div>
            <div class="quick-actions">
              <button class="qa-btn primary" @click="sendQuick('我想要做程序开发')"><svg viewBox="0 0 24 24" fill="none" width="12" height="12"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>程序开发</button>
              <button class="qa-btn" @click="sendQuick('写一份AMD GPU市场分析报告')"><svg viewBox="0 0 24 24" fill="none" width="12" height="12"><line x1="18" y1="20" x2="18" y2="10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><line x1="12" y1="20" x2="12" y2="4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><line x1="6" y1="20" x2="6" y2="14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>写报告</button>
              <button class="qa-btn" @click="sendQuick('审查代码：function add(a,b){return a+b}')"><svg viewBox="0 0 24 24" fill="none" width="12" height="12"><circle cx="11" cy="11" r="8" stroke="currentColor" stroke-width="1.8"/><path d="M21 21l-4.35-4.35" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>代码审查</button>
              <button class="qa-btn" @click="sendQuick('帮我写一封工作邮件')"><svg viewBox="0 0 24 24" fill="none" width="12" height="12"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/><polyline points="22,6 12,13 2,6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>写邮件</button>
            </div>
          </div>

          <div v-for="(m,i) in messages" :key="i" class="msg" :class="m.role">
            <div class="msg-avatar" v-if="m.role === 'assistant'"><svg viewBox="0 0 24 24" fill="none" width="14" height="14"><rect x="4" y="8" width="16" height="12" rx="3" stroke="currentColor" stroke-width="1.6"/><circle cx="9" cy="14" r="1.4" fill="currentColor"/><circle cx="15" cy="14" r="1.4" fill="currentColor"/><path d="M12 8V4M9 4h6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></div>
            <div class="msg-content">
              <div class="msg-text" v-html="smartMd(m.content)"></div>
              <div v-if="m.meta?.workgroup" class="msg-meta"><span class="meta-tag">{{ m.meta.workgroup }}</span><span class="meta-badge" v-if="m.meta.roles_used?.length">{{ m.meta.roles_used.length }} 步</span></div>
            </div>
            <div class="msg-avatar avatar-user" v-if="m.role === 'user'">U</div>
          </div>

          <div v-if="streaming" class="msg assistant">
            <div class="msg-avatar"><svg viewBox="0 0 24 24" fill="none" width="14" height="14"><rect x="4" y="8" width="16" height="12" rx="3" stroke="currentColor" stroke-width="1.6"/><circle cx="9" cy="14" r="1.4" fill="currentColor"/><circle cx="15" cy="14" r="1.4" fill="currentColor"/><path d="M12 8V4M9 4h6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg></div>
            <div class="msg-content"><div class="msg-text streaming-text">{{ buf }}<span class="cursor-blink">▊</span></div></div>
          </div>
        </div>
      </div>

      <div class="input-area">
        <div class="input-box">
          <textarea v-model="txt" placeholder="发消息或输入关键词触发工作组..." rows="1" @keydown.enter.exact.prevent="send" @input="autoResize" ref="inputEl" :disabled="streaming"/>
          <button class="send-btn" @click="send" :disabled="streaming || !txt.trim()">
            <svg v-if="!streaming" width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M2 8l12-5-4 12-2-5-6-2z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>
            <div v-else class="loading-dots"><span></span><span></span><span></span></div>
          </button>
        </div>
        <div class="input-hint">Enter 发送 · Shift+Enter 换行 — 说「开发XX」触发完整流水线</div>
      </div>
    </div>

    <!-- 拖拽手柄 -->
    <div class="drag-handle" ref="dragRight" @mousedown="startDrag('right', $event)">
      <button class="drag-collapse" @click="inspectorCollapsed = true" v-if="!inspectorCollapsed">
        <svg viewBox="0 0 24 24" fill="none" width="8" height="8"><path d="M9 18l6-6-6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
    </div>

    <!-- 右栏 -->
    <aside class="inspector" :class="{ collapsed: inspectorCollapsed }" ref="inspectorEl">
      <div class="panel-tab-hint" v-if="inspectorCollapsed" @click="inspectorCollapsed = false">面板</div>
      <div class="inspector-tabs">
        <button class="inspector-tab" :class="{ active: rightTab === 'pipeline' }" @click="rightTab = 'pipeline'">流水线</button>
        <button class="inspector-tab" :class="{ active: rightTab === 'preview' }" @click="rightTab = 'preview'">预览</button>
      </div>
      <div class="inspector-body">
        <!-- Tab: 流水线 -->
        <div class="tab-panel" :class="{ active: rightTab === 'pipeline' }">
          <div class="inspector-pipeline">
            <div class="inspector-pipeline-header">
              <span class="inspector-pipeline-title">{{ pipelineActive ? '执行中' : '空闲' }}</span>
            </div>
            <div class="steps">
              <div v-for="(step, idx) in displaySteps" :key="idx" class="step" :class="{ done: step.s === 'done', active: step.s === 'running' }" @click="selectedStep = idx">
                <div class="step-dot">{{ step.s === 'done' ? '✓' : idx + 1 }}</div>
                <div class="step-info"><div class="step-name">{{ step.role }}</div><div class="step-status">{{ step.s === 'done' ? '已完成' : step.s === 'running' ? '执行中…' : '等待' }}</div></div>
              </div>
            </div>
          </div>
        </div>
        <!-- Tab: 预览 -->
        <div class="tab-panel" :class="{ active: rightTab === 'preview' }">
          <div class="preview-header">
            <span class="preview-title">产物预览</span>
            <div class="preview-tabs">
              <button class="preview-tab" :class="{active: previewMode === 'web'}" @click="previewMode = 'web'">页面</button>
              <button class="preview-tab" :class="{active: previewMode === 'code'}" @click="previewMode = 'code'">源码</button>
            </div>
          </div>
          <div class="preview-body">
            <iframe v-if="previewMode === 'web' && htmlContent" class="preview-iframe" :srcdoc="htmlContent" sandbox="allow-scripts"/>
            <div v-else-if="previewMode === 'web'" class="preview-empty"><div class="preview-empty-icon">⊞</div>产物将在此预览<br><span style="font-size:11px;margin-top:4px">HTML / 报告 / 图片</span></div>
            <pre v-else class="preview-code">{{ htmlContent || '暂无源码' }}</pre>
          </div>
        </div>
      </div>
    </aside>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted, computed } from 'vue'
import { marked } from 'marked'

const agents = ref([]), currentAgent = ref(''), messages = ref([]), txt = ref('')
const streaming = ref(false), buf = ref(''), msgEl = ref(null), inputEl = ref(null), lastMeta = ref(null)
const llmOnline = ref(false), modelName = ref('Qwen3-30B-A3B'), roles = ref([]), workgroups = ref([])
const pipelineActive = ref(false), pipelineSteps = ref([]), lastPipeline = ref([]), selectedStep = ref(null)
const displaySteps = computed(() => pipelineActive.value ? pipelineSteps.value : lastPipeline.value)

// 面板状态
const sidebarCollapsed = ref(false)
const inspectorCollapsed = ref(false)
const rightTab = ref('pipeline')
const previewMode = ref('web')
const htmlContent = ref('')

// 拖拽
const sidebarEl = ref(null), inspectorEl = ref(null)
function startDrag(side, e) {
  if (side === 'left' && sidebarCollapsed.value) return
  const el = side === 'left' ? sidebarEl.value : inspectorEl.value
  const main = document.querySelector('.main')
  document.body.style.cursor = 'col-resize'
  document.body.style.userSelect = 'none'
  const mousemove = (ev) => {
    const rect = main.getBoundingClientRect()
    const w = side === 'left' ? ev.clientX - rect.left : rect.right - ev.clientX
    const minW = side === 'left' ? 160 : 200
    const maxW = side === 'left' ? 420 : 500
    el.style.width = Math.max(minW, Math.min(maxW, w)) + 'px'
  }
  const mouseup = () => { document.body.style.cursor = ''; document.body.style.userSelect = ''; document.removeEventListener('mousemove', mousemove); document.removeEventListener('mouseup', mouseup) }
  document.addEventListener('mousemove', mousemove)
  document.addEventListener('mouseup', mouseup)
}

function md(t) { try { return marked(t || '') } catch { return t || '' } }

function smartMd(t) {
  if (!t) return ''
  // 思维链折叠处理
  t = t.replace(/<thinking>([\s\S]*?)<\/thinking>/g, (_, think) => {
    const short = think.slice(0, 120).replace(/\n/g, ' ') + '...'
    return `<details class="think-chain"><summary>思考过程 · ${short}</summary><div class="think-content">${marked(think)}</div></details>`
  })
  // 检测是否以 HTML 代码为主（占内容的 60% 以上是 HTML）
  const htmlRatio = (t.match(/<\/?[a-z][\s\S]*?>/gi) || []).length / Math.max(t.length, 1)
  if (htmlRatio > 0.3 && t.length > 200) {
    const truncated = t.replace(/```html[\s\S]*?```/gi, (m) => {
      const lines = m.split('\n')
      const first = lines.slice(0, 5).join('\n')
      return `<div class="code-fold" data-full="${encodeURIComponent(m)}">${marked(first)}<button class="code-expand-btn" onclick="this.closest('.code-fold').classList.add('open');this.remove()">展开全部 (${lines.length} 行)</button></div>`
    })
    return marked(truncated)
  }
  // 文件路径高亮
  let text = t.replace(/([\w./-]+\.[\w]{2,4})(\s|$|[,;:])/g, (m, p, e) =>
    /\.(py|js|ts|vue|json|yaml|yml|md|html|css|scss|sh|txt|xml)$/.test(p)
      ? `<code class="file-path">${p}</code>${e}` : m
  )
  return marked(text)
}

// 代码块折叠初始化
function initCodeFolding() {
  nextTick(() => {
    const msgEl = document.querySelector('.messages')
    if (!msgEl) return
    msgEl.querySelectorAll('pre').forEach(pre => {
      if (pre.classList.contains('code-folded')) return
      const lines = pre.textContent.split('\n').length
      if (lines > 15 && pre.closest('.msg-text')) {
        pre.classList.add('code-folded')
        pre.style.maxHeight = '180px'
        pre.style.overflow = 'hidden'
        pre.style.position = 'relative'
        const btn = document.createElement('button')
        btn.className = 'code-expand-btn'
        btn.textContent = `展开全部 (${lines} 行) ▼`
        btn.onclick = () => {
          pre.style.maxHeight = 'none'
          pre.classList.remove('code-folded')
          btn.remove()
        }
        pre.appendChild(btn)
      }
    })
  })
}

// ---- HTML 预览 ----
function hasHtmlCode(text) {
  // 严格判断：必须存在 HTML 代码块或以 <!DOCTYPE/<html> 开头的片段
  return /```(?:html)?\s*[\s\S]*?```/.test(text) ||
         /<!DOCTYPE\s+html/i.test(text) ||
         /<html[\s>]/i.test(text)
}
function extractHtml(text) {
  // 优先匹配 ```html 代码块
  const m = text.match(/```html\s*\n?([\s\S]*?)```/i)
  if (m && m[1].trim().length > 50) return m[1]
  // 次优：任何代码块里包含 <html 或 <!DOCTYPE
  const blocks = [...text.matchAll(/```(\w*)\n?([\s\S]*?)```/g)]
  for (const b of blocks) {
    if (/<(!DOCTYPE|html|head|body)[\s\S]*<\/\s*html\s*>/i.test(b[2])) return b[2]
  }
  return null
}

// ---- 对话管理 ----
const currentConversation = ref(null), conversationList = ref([]), STORAGE_KEY = 'myagent_conversations'
function newConversation() {
  if (currentConversation.value && messages.value.length > 0) saveCurrentToStorage()
  const conv = { id: Date.now().toString(36), title: '新对话 ' + new Date().toLocaleTimeString(), agent_id: currentAgent.value, messages: [], created_at: new Date().toISOString(), updated_at: new Date().toISOString() }
  currentConversation.value = conv; messages.value = []; streaming.value = false; buf.value = ''
  saveCurrentToStorage(); refreshConversationList(); nextTick(scroll)
}
function saveCurrentToStorage() {
  if (!currentConversation.value) return
  currentConversation.value.messages = [...messages.value]
  currentConversation.value.updated_at = new Date().toISOString()
  const convs = loadFromStorage(); const idx = convs.findIndex(c => c.id === currentConversation.value.id)
  if (idx >= 0) convs[idx] = currentConversation.value; else convs.unshift(currentConversation.value)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(convs))
}
function loadFromStorage() { try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]') } catch { return [] } }
function refreshConversationList() { conversationList.value = loadFromStorage() }
function loadConversation(conv) {
  if (currentConversation.value && currentConversation.value.id !== conv.id && messages.value.length > 0) saveCurrentToStorage()
  currentConversation.value = { ...conv }; messages.value = [...(conv.messages || [])]; nextTick(scroll)
}
function deleteConvById(id) {
  if (!confirm('删除此对话？')) return
  const convs = loadFromStorage().filter(c => c.id !== id)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(convs))
  if (currentConversation.value?.id === id) { currentConversation.value = null; messages.value = [] }
  refreshConversationList()
}
function formatTime(iso) { if (!iso) return ''; const d = new Date(iso); return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' }) }

// ---- 数据加载 ----
async function loadAgents() { try { const r = await fetch('/api/agents'); const d = await r.json(); agents.value = d.agents || []; if (agents.value.length && !currentAgent.value) selectAgent(agents.value[0].agent_id) } catch {} }
async function loadSys() { try { const r = await fetch('/api/system'); const d = await r.json(); roles.value = d.roles || []; workgroups.value = d.workgroups || []; if (d.gpu) { llmOnline.value = d.gpu.llm_available; modelName.value = d.gpu.model || modelName.value } } catch { try { const r = await fetch('/api/health'); const d = await r.json(); llmOnline.value = d.llm_available } catch {} } }
function selectAgent(id) { currentAgent.value = id; messages.value = [] }

// ---- 发送 ----
async function send() {
  const text = txt.value.trim()
  if (!text || !currentAgent.value || streaming.value) return
  const t = text; txt.value = ''; resetInputHeight()
  messages.value.push({ role: 'user', content: t }); scroll()

  if (!currentConversation.value) {
    currentConversation.value = { id: Date.now().toString(36), title: t.length > 20 ? t.slice(0, 20) + '...' : t, agent_id: currentAgent.value, messages: [], created_at: new Date().toISOString(), updated_at: new Date().toISOString() }
  }
  streaming.value = true; buf.value = ''
  pipelineActive.value = true
  pipelineSteps.value = [{ role: '匹配中…', s: 'running', output: '' }]
  selectedStep.value = 0; rightTab.value = 'pipeline'

  const ws = new WebSocket((location.protocol === 'https:' ? 'wss' : 'ws') + '://' + location.host + '/api/agents/' + currentAgent.value + '/ws')
  ws.onopen = () => ws.send(JSON.stringify({ message: t }))
  ws.onmessage = e => {
    const d = JSON.parse(e.data)
    if (d.type === 'stream_token') {
      const raw = d.content
      // 检测流水线进度标记 __PIPE__step/total role done|error
      const pipeRegex = /__PIPE__\d+\/\d+\s+\S+\s+(?:done|error)/g
      const hasPipe = pipeRegex.test(raw)
      if (hasPipe) {
        const matches = [...raw.matchAll(/__PIPE__(\d+)\/(\d+)\s+(\S+)\s+(done|error)/g)]
        for (const m of matches) {
          const step = parseInt(m[1]), total = parseInt(m[2]), role = m[3], st = m[4]
          if (pipelineSteps.value.length === 0 || pipelineSteps.value.length !== total) {
            pipelineSteps.value = Array.from({ length: total }, (_, i) => ({ role: `步骤${i+1}`, s: 'pending', output: '' }))
          }
          pipelineSteps.value[step - 1] = { role, s: st === 'error' ? 'error' : 'done', output: '' }
          if (st === 'done') scroll()
        }
        // 滤掉完整的 __PIPE__ 标记（含角色名+状态），不显示在对话里
        const clean = raw.replace(/__PIPE__\d+\/\d+\s+\S+\s+(?:done|error)/g, '').trim()
        if (clean) { buf.value += clean; scroll() }
      } else {
        buf.value += raw; scroll()
      }
    }
    else if (d.type === 'stream_meta') {
      lastMeta.value = { type: d.dispatch_type, workgroup: d.workgroup, roles_used: d.roles_used }
      if (d.roles_used?.length) { pipelineSteps.value = d.roles_used.map((r, i) => ({ role: r, s: i === 0 ? 'running' : 'pending', output: '' })); selectedStep.value = 0 }
    }
    else if (d.type === 'stream_end') {
      const final = buf.value
      messages.value.push({ role: 'assistant', content: final, meta: lastMeta.value || undefined })
      buf.value = ''; lastMeta.value = null; streaming.value = false; ws.close()
      saveCurrentToStorage(); refreshConversationList()
      if (pipelineActive.value && pipelineSteps.value.length) {
        try {
          const results = parsePipelineOutput(final)
          for (let i = 0; i < pipelineSteps.value.length; i++) {
            if (pipelineSteps.value[i].s === 'pending') {
              pipelineSteps.value[i].s = 'done'
            }
            if (results[i]?.content && !pipelineSteps.value[i].output) {
              pipelineSteps.value[i].output = results[i].content
            }
          }
        } catch { pipelineSteps.value = pipelineSteps.value.map(s => ({ ...s, s: s.s === 'pending' ? 'done' : s.s, output: s.output || '已完成' })) }
        lastPipeline.value = [...pipelineSteps.value]; selectedStep.value = 0
      }
      pipelineActive.value = false
      if (hasHtmlCode(final)) {
        const html = extractHtml(final)
        if (html) { htmlContent.value = html; rightTab.value = 'preview' }
      }
    }
  }
  ws.onerror = () => { streaming.value = false; buf.value = ''; pipelineActive.value = false }
}
function parsePipelineOutput(text) {
  const steps = []
  const pattern = /(?:####?\s*)?步骤\s*(\d+)\s*[:：]\s*(\S+)/g
  const matches = [...text.matchAll(pattern)]
  if (!matches.length) return []
  const segments = text.split(/(?:####?\s*)?步骤\s*\d+\s*[:：]\s*\S+/)
  matches.forEach((m, i) => { steps.push({ num: m[1], role: m[2], content: (segments[i + 1] || '').trim().slice(0, 500) }) })
  return steps
}
function sendQuick(t) { txt.value = t; nextTick(() => { send() }) }
function scroll() { nextTick(() => { if (msgEl.value) { msgEl.value.scrollTop = msgEl.value.scrollHeight; initCodeFolding() } }) }
function resetInputHeight() { if (inputEl.value) inputEl.value.style.height = 'auto' }
function autoResize(e) { const el = e.target; el.style.height = 'auto'; el.style.height = Math.min(el.scrollHeight, 160) + 'px' }

onMounted(() => {
  loadAgents(); loadSys(); setInterval(loadSys, 15000)
  refreshConversationList()
  const convs = loadFromStorage()
  if (convs.length > 0 && !currentConversation.value) loadConversation(convs[0])
  initCodeFolding()
})
</script>

<style scoped>
/* ===== 主布局 ===== */
.main { display: flex; flex: 1; height: 100%; overflow: hidden; background: var(--bg-root); }

/* ===== 左栏 ===== */
.sidebar {
  width: 260px; flex-shrink: 0; background: var(--bg-surface);
  display: flex; flex-direction: column; padding: 12px;
  transition: margin-left 0.25s ease; position: relative; z-index: 1; overflow-y: auto;
}
.sidebar.collapsed { margin-left: -260px; box-shadow: 2px 0 8px rgba(0,0,0,0.06); }
.sidebar-header { display: flex; align-items: center; justify-content: space-between; padding: 6px 6px 12px; }
.sidebar-label { font-size: 11px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.8px; }
.sidebar-new { width: 26px; height: 26px; border-radius: 6px; background: none; color: var(--text-tertiary); border: 1px solid var(--border); display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.15s; }
.sidebar-new:hover { background: var(--bg-hover); color: var(--text-primary); border-color: var(--accent); }

.conv-list { display: flex; flex-direction: column; gap: 2px; }
.conv-item { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px; cursor: pointer; transition: all 0.12s; border: 1px solid transparent; }
.conv-item:hover { background: var(--bg-hover); }
.conv-item.active { background: var(--bg-active); border-color: rgba(91,93,240,0.12); }
.conv-icon { width: 28px; height: 28px; border-radius: 8px; flex-shrink: 0; background: rgba(91,93,240,0.08); display: flex; align-items: center; justify-content: center; color: var(--accent); }
.conv-body { flex: 1; min-width: 0; }
.conv-title { font-size: 13px; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-bottom: 2px; }
.conv-meta { font-size: 11px; color: var(--text-tertiary); }
.conv-delete { width: 20px; height: 20px; border-radius: 4px; background: none; border: none; color: var(--text-tertiary); cursor: pointer; display: flex; align-items: center; justify-content: center; opacity: 0; transition: all 0.12s; flex-shrink: 0; }
.conv-item:hover .conv-delete { opacity: 0.6; }
.conv-delete:hover { background: var(--bg-hover); color: var(--danger); opacity: 1; }

/* 折叠提示片 */
.panel-tab-hint { position: absolute; top: 50%; transform: translateY(-50%); width: 22px; height: 48px; background: var(--bg-surface); border: 1px solid var(--border); cursor: pointer; display: flex; align-items: center; justify-content: center; box-shadow: var(--shadow-card); writing-mode: vertical-rl; font-size: 10px; font-weight: 600; color: var(--text-tertiary); letter-spacing: 1px; z-index: 0; transition: all 0.15s; }
.sidebar .panel-tab-hint { right: -22px; border-radius: 0 7px 7px 0; border-left: none; }
.panel-tab-hint:hover { color: var(--accent); background: rgba(91,93,240,0.06); }

/* ===== 拖拽手柄 ===== */
.drag-handle { width: 5px; flex-shrink: 0; cursor: col-resize; background: transparent; position: relative; z-index: 5; display: flex; align-items: center; justify-content: center; transition: background 0.15s; }
.drag-handle:hover, .drag-handle:active { background: var(--accent); }
.drag-handle::after { content: ''; position: absolute; inset: 0; left: -4px; right: -4px; }
.drag-collapse { position: absolute; top: 50%; transform: translateY(-50%); width: 18px; height: 18px; border-radius: 5px; background: var(--bg-surface); border: 1px solid var(--border); display: flex; align-items: center; justify-content: center; cursor: pointer; z-index: 10; color: var(--text-tertiary); opacity: 0; transition: all 0.15s; padding: 0; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.drag-handle:hover .drag-collapse { opacity: 1; }
.drag-collapse:hover { background: rgba(91,93,240,0.06); border-color: var(--accent); color: var(--accent); }

/* ===== 对话区 ===== */
.chat-col { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.messages { flex: 1; overflow-y: auto; padding: 24px 0 16px; }
.msg-wrap { max-width: 720px; margin: 0 auto; padding: 0 24px; display: flex; flex-direction: column; gap: 2px; }

.empty { display: flex; flex-direction: column; align-items: center; justify-content: center; min-height: 320px; text-align: center; gap: 12px; }
.empty-glow { width: 56px; height: 56px; border-radius: 18px; background: rgba(91,93,240,0.1); display: flex; align-items: center; justify-content: center; margin-bottom: 4px; }
.empty-title { font-size: 18px; font-weight: 600; }
.empty-sub { font-size: 13px; color: var(--text-tertiary); margin-bottom: 12px; }
.quick-actions { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; max-width: 440px; }
.qa-btn { display: inline-flex; align-items: center; gap: 6px; padding: 8px 14px; font-size: 12px; color: var(--text-secondary); background: var(--bg-surface); border: 1px solid var(--border); border-radius: 16px; cursor: pointer; transition: all 0.15s; box-shadow: 0 1px 2px rgba(0,0,0,0.02); }
.qa-btn:hover { border-color: var(--accent); color: var(--accent); }
.qa-btn.primary { border-color: rgba(91,93,240,0.2); color: var(--accent); font-weight: 500; background: rgba(91,93,240,0.04); }

/* 消息 */
.msg { display: flex; gap: 10px; align-items: flex-start; padding: 6px 0; }
.msg.user { flex-direction: row; justify-content: flex-end; }
.msg.assistant { padding-top: 10px; }
.msg-avatar { width: 26px; height: 26px; border-radius: 7px; flex-shrink: 0; display: flex; align-items: center; justify-content: center; font-size: 13px; margin-top: 2px; }
.msg.assistant .msg-avatar { background: rgba(91,93,240,0.08); border: 1px solid rgba(91,93,240,0.12); }
.avatar-user { background: rgba(91,93,240,0.08); border: 1px solid rgba(91,93,240,0.15); font-size: 11px; font-weight: 600; color: var(--accent); }
.msg-content { min-width: 0; max-width: 85%; display: flex; flex-direction: column; }
.msg.user .msg-content { align-items: flex-end; }

/* AI 消息 — 纯文字 */
.msg-text { font-size: 14px; line-height: 1.65; color: var(--text-primary); }
.msg.assistant .msg-text { padding: 0; }
.msg.assistant .msg-text p { margin: 0 0 8px; }
.msg.assistant .msg-text p:last-child { margin: 0; }

/* 用户消息 — 微妙气泡 */
.msg.user .msg-text { padding: 9px 14px; background: rgba(91,93,240,0.06); border: 1px solid rgba(91,93,240,0.12); border-radius: 12px; border-top-right-radius: 4px; }
.msg.user .msg-text p { margin: 0; }
.msg-text strong { font-weight: 600; }
.msg-text code { font-family: "SF Mono", monospace; font-size: 12px; background: var(--bg-hover); color: #d6336c; padding: 1px 6px; border-radius: 4px; }
.msg-text pre { background: #1e293b; color: #e2e8f0; border-radius: 8px; padding: 14px 16px; overflow-x: auto; margin: 8px 0; font-size: 12.5px; line-height: 1.6; }
.msg-text pre code { background: none; padding: 0; color: inherit; font-size: inherit; }
.streaming-text { white-space: pre-wrap; }
.cursor-blink { color: var(--accent); animation: blink 1s steps(2) infinite; }
@keyframes blink { 50% { opacity: 0; } }

.msg-meta { display: flex; align-items: center; gap: 8px; padding: 0 4px; margin-top: 2px; }
.meta-tag { font-size: 11px; color: var(--accent); background: rgba(91,93,240,0.06); padding: 2px 8px; border-radius: 8px; font-weight: 500; }
.meta-badge { font-size: 10px; color: var(--success); font-weight: 600; }

/* 输入 */
.input-area { padding: 0 24px 14px; flex-shrink: 0; }
.input-box { display: flex; align-items: flex-end; gap: 8px; background: var(--bg-surface); border: 1.5px solid var(--border); border-radius: 16px; padding: 10px 14px; transition: all 0.25s; box-shadow: var(--shadow-card); max-width: 720px; margin: 0 auto; }
.input-box:focus-within { border-color: var(--accent); box-shadow: 0 0 0 4px rgba(91,93,240,0.1); }
.input-box textarea { flex: 1; border: none; outline: none; resize: none; font-family: inherit; font-size: 14px; color: var(--text-primary); line-height: 1.5; max-height: 140px; padding: 4px 0; background: none; min-height: 24px; }
.input-box textarea::placeholder { color: var(--text-tertiary); }
.send-btn { width: 34px; height: 34px; border-radius: 9px; flex-shrink: 0; background: var(--accent); border: none; color: #fff; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.15s; }
.send-btn:hover:not(:disabled) { background: var(--accent-hover); transform: scale(1.04); }
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.loading-dots { display: flex; gap: 3px; }
.loading-dots span { width: 4px; height: 4px; background: #fff; border-radius: 50%; animation: dot-bounce 1.4s infinite ease-in-out both; }
.loading-dots span:nth-child(2) { animation-delay: 0.16s; }
.loading-dots span:nth-child(3) { animation-delay: 0.32s; }
@keyframes dot-bounce { 0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; } 40% { transform: scale(1); opacity: 1; } }
.input-hint { text-align: center; font-size: 10px; color: var(--text-tertiary); margin-top: 8px; }

/* ===== 右栏 ===== */
.inspector { width: 340px; flex-shrink: 0; background: var(--bg-surface); display: flex; flex-direction: column; overflow: hidden; transition: margin-right 0.25s ease; position: relative; z-index: 1; }
.inspector.collapsed { margin-right: -340px; box-shadow: -2px 0 8px rgba(0,0,0,0.06); }
.inspector .panel-tab-hint { left: -22px; border-radius: 7px 0 0 7px; border-right: none; }

.inspector-tabs { display: flex; padding: 12px 16px 0; gap: 2px; border-bottom: 1px solid var(--border-light); flex-shrink: 0; }
.inspector-tab { padding: 7px 16px; font-size: 12px; font-weight: 600; color: var(--text-tertiary); border: none; background: none; cursor: pointer; transition: all 0.15s; border-bottom: 2px solid transparent; margin-bottom: -1px; font-family: inherit; }
.inspector-tab:hover { color: var(--text-secondary); }
.inspector-tab.active { color: var(--accent); border-bottom-color: var(--accent); }
.inspector-body { flex: 1; overflow: hidden; display: flex; flex-direction: column; }

.tab-panel { display: none; flex: 1; flex-direction: column; overflow: hidden; }
.tab-panel.active { display: flex; }

.inspector-pipeline { padding: 12px 16px; overflow-y: auto; }
.inspector-pipeline-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.inspector-pipeline-title { font-size: 12px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.5px; }

.steps { display: flex; flex-direction: column; gap: 2px; }
.step { display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 7px; cursor: pointer; border: 1px solid transparent; transition: all 0.12s; }
.step:hover { background: var(--bg-hover); }
.step.active { background: var(--bg-active); border-color: rgba(91,93,240,0.12); }
.step-dot { width: 22px; height: 22px; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 600; background: var(--bg-hover); color: var(--text-tertiary); flex-shrink: 0; }
.step.done .step-dot { background: var(--success-bg); color: var(--success); }
.step.active .step-dot { background: rgba(91,93,240,0.1); color: var(--accent); animation: pulse-glow 2s infinite; }
@keyframes pulse-glow { 0%,100% { box-shadow: 0 0 0 0 rgba(91,93,240,0.2); } 50% { box-shadow: 0 0 0 5px rgba(91,93,240,0); } }
.step-name { font-size: 12px; font-weight: 500; }
.step-status { font-size: 10px; color: var(--text-tertiary); }

.preview-header { display: flex; align-items: center; justify-content: space-between; padding: 10px 16px; border-bottom: 1px solid var(--border-light); flex-shrink: 0; }
.preview-title { font-size: 12px; font-weight: 600; }
.preview-tabs { display: flex; gap: 2px; }
.preview-tab { padding: 3px 9px; border-radius: 5px; font-size: 10px; color: var(--text-tertiary); cursor: pointer; border: none; background: none; transition: all 0.15s; font-weight: 500; }
.preview-tab.active { color: var(--accent); background: rgba(91,93,240,0.06); }
.preview-body { flex: 1; overflow: hidden; background: #f8f8f6; }
.preview-iframe { width: 100%; height: 100%; border: none; background: #fff; }
.preview-empty { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; color: var(--text-tertiary); font-size: 13px; text-align: center; padding: 20px; }
.preview-code { width: 100%; height: 100%; padding: 16px; overflow-y: auto; font-family: "SF Mono", monospace; font-size: 12px; line-height: 1.7; color: var(--text-secondary); white-space: pre-wrap; background: #fafaf9; margin: 0; }

/* 代码块折叠 */
.code-folded { position: relative; }
.code-folded::after {
  content: ''; position: absolute; bottom: 0; left: 0; right: 0; height: 60px;
  background: linear-gradient(transparent, #1e293b);
}
.code-expand-btn {
  position: absolute; bottom: 6px; left: 50%; transform: translateX(-50%);
  padding: 3px 14px; font-size: 10px; font-weight: 600;
  background: rgba(91,93,240,0.15); color: #a5b4fc;
  border: 1px solid rgba(91,93,240,0.3); border-radius: 12px;
  cursor: pointer; z-index: 2; font-family: inherit;
  transition: all 0.15s; white-space: nowrap;
}
.code-expand-btn:hover { background: rgba(91,93,240,0.3); color: #fff; }
.file-path { background: var(--bg-hover); color: var(--accent); padding: 1px 6px; border-radius: 4px; font-size: 12px; cursor: default; }

/* 思维链 */
.think-chain { margin: 6px 0; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.think-chain summary {
  padding: 6px 14px; font-size: 11px; color: var(--text-tertiary);
  background: var(--bg-hover); cursor: pointer; font-style: italic;
  list-style: none; display: flex; align-items: center; gap: 6px;
}
.think-chain summary::before { content: '↓ 展开'; font-style: normal; font-weight: 600; color: var(--accent); font-size: 10px; }
.think-chain[open] summary::before { content: '↑ 收起'; }
.think-chain summary:hover { background: rgba(91,93,240,0.06); }
.think-content { padding: 10px 14px; font-size: 12px; line-height: 1.6; color: var(--text-secondary); }

::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-thumb { background: #d4d4d8; border-radius: 3px; }
</style>
