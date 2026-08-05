<template>
  <div class="agent-platform">
    <!-- ===== 左栏: 系统状态 + 智能体 ===== -->
    <aside class="left-panel">
      <!-- 系统状态卡 -->
      <div class="system-card" :class="{ online: llmOnline }">
        <div class="system-status">
          <div class="status-indicator"></div>
          <div class="status-info">
            <div class="status-label">{{ llmOnline ? '在线' : '离线' }}</div>
            <div class="status-model">{{ modelName }}</div>
          </div>
        </div>
        <div class="system-stats" v-if="showSys">
          <div class="stat">
            <span class="stat-num">{{ roles.length }}</span>
            <span class="stat-label">角色</span>
          </div>
          <div class="stat">
            <span class="stat-num">{{ workgroups.length }}</span>
            <span class="stat-label">工作组</span>
          </div>
          <div class="stat">
            <span class="stat-num">{{ agents.length }}</span>
            <span class="stat-label">智能体</span>
          </div>
        </div>
        <button class="expand-btn" @click="showSys=!showSys">
          <svg :class="{rotated: showSys}" width="12" height="12" viewBox="0 0 12 12">
            <path d="M2 4l4 4 4-4" stroke="currentColor" stroke-width="1.5" fill="none"/>
          </svg>
        </button>
      </div>

      <!-- 智能体 + 新建按钮 -->
      <div class="sidebar-section">
        <div class="section-header">
          <h3>智能体</h3>
          <span class="section-badge">{{ agents.length }}</span>
          <button class="section-new-btn" @click="newConversation" title="新建对话">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
              <path d="M6 2v8M2 6h8" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>
            </svg>
          </button>
        </div>
        <div class="agent-list">
          <div v-for="a in agents" :key="a.agent_id" class="agent-card"
               :class="{ active: currentAgent===a.agent_id }"
               @click="selectAgent(a.agent_id)">
            <div class="agent-avatar">
              <svg viewBox="0 0 24 24" fill="none"><rect x="4" y="8" width="16" height="12" rx="2.5" stroke="currentColor" stroke-width="1.6"/><circle cx="9" cy="14" r="1.5" fill="currentColor"/><circle cx="15" cy="14" r="1.5" fill="currentColor"/><path d="M12 8V4M9 4h6" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M2 13h2M20 13h2" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
            </div>
            <div class="agent-info">
              <div class="agent-name">{{ a.name }}</div>
              <div class="agent-desc">{{ a.description }}</div>
            </div>
          </div>
        </div>
      </div>
    </aside>

    <!-- ===== 中栏: 对话 ===== -->
    <div class="chat-col">
      <!-- 工作组顶部横栏 -->
      <div class="workgroup-bar">
        <span class="wg-bar-label">工作组</span>
        <button v-for="wg in workgroups" :key="wg.id" class="wg-chip" @click="triggerWg(wg)" :title="wg.description">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
            <path d="M3 9h18M3 15h18M9 3v18M15 3v18" stroke="currentColor" stroke-width="1.5"/>
          </svg>
          <span class="wg-chip-name">{{ wg.name }}</span>
          <span class="wg-chip-steps">{{ wg.pipeline_steps }}步</span>
        </button>
      </div>

      <div class="chat-header">
        <div class="chat-title-area">
          <h2 class="chat-title">
            <span v-if="currentConversation">{{ currentConversation.title || '新对话' }}</span>
            <span v-else class="title-placeholder">未命名对话</span>
          </h2>
          <span v-if="messages.length" class="msg-count">{{ messages.length }} 条消息</span>
        </div>
      </div>

      <!-- 对话历史侧边面板 (已移除——历史在右侧栏) -->

      <div class="messages" ref="msgEl">
        <div v-if="messages.length===0 && !streaming" class="empty-state">
          <div class="empty-icon">💬</div>
          <h2 class="empty-title">开始你的 AI 对话</h2>
          <p class="empty-sub">选择智能体或工作组，输入消息开始</p>
          <div class="quick-pills">
            <button class="pill primary" @click="sendQuick('我想要做程序开发')">
              <span class="pill-icon">⚡</span>
              <span>程序开发</span>
            </button>
            <button class="pill" @click="sendQuick('写一份AMD GPU市场分析报告')">
              <span class="pill-icon">📊</span>
              <span>写报告</span>
            </button>
            <button class="pill" @click="sendQuick('审查代码：function add(a,b){return a+b}')">
              <span class="pill-icon">🔍</span>
              <span>代码审查</span>
            </button>
            <button class="pill" @click="sendQuick('帮我写一封工作邮件')">
              <span class="pill-icon">✉️</span>
              <span>写邮件</span>
            </button>
          </div>
        </div>

        <div v-for="(m,i) in messages" :key="i" class="msg" :class="m.role">
          <div class="msg-avatar" v-if="m.role === 'assistant'">🤖</div>
          <div class="msg-content">
            <div class="bubble" v-html="md(m.content)"></div>
            <div v-if="m.meta?.workgroup" class="msg-meta">
              <span class="meta-tag">
                <span class="meta-icon">⚙️</span>
                {{ m.meta.workgroup }}
              </span>
              <span class="meta-roles" v-if="m.meta.roles_used?.length">
                <span class="meta-roles-text">{{ m.meta.roles_used.join(' → ') }}</span>
                <span class="meta-badge">{{ m.meta.roles_used.length }} 步完成</span>
              </span>
            </div>
          </div>
        </div>

        <div v-if="streaming" class="msg assistant">
          <div class="msg-avatar">🤖</div>
          <div class="msg-content">
            <div class="bubble streaming">
              <span class="bubble-text">{{ buf }}</span>
              <span class="cursor-blink">▊</span>
            </div>
          </div>
        </div>
      </div>

      <div class="input-bar">
        <div class="input-wrap">
          <textarea
            v-model="txt"
            class="input"
            placeholder="发消息、问问题、或输入关键词触发工作组..."
            rows="1"
            @keydown.enter.exact.prevent="send"
            @input="autoResize"
            ref="inputEl"
            :disabled="streaming"
          />
          <button class="send-btn" @click="send" :disabled="streaming || !txt.trim()">
            <svg v-if="!streaming" width="18" height="18" viewBox="0 0 18 18" fill="none">
              <path d="M2 9l14-7-5 14-2-6-7-1z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
            </svg>
            <div v-else class="loading-dots">
              <span></span><span></span><span></span>
            </div>
          </button>
        </div>
        <div class="input-hint">
          <span>Enter 发送 · Shift+Enter 换行</span>
        </div>
      </div>
    </div>

    <!-- ===== 右栏: 产出区 / 对话历史 ===== -->
    <aside class="right-panel">
      <div class="rhead">
        <div class="rhead-status" v-if="pipelineActive || lastPipeline.length">
          <span v-if="pipelineActive" class="rhead-dot active"></span>
          <span v-else class="rhead-dot done"></span>
          <span class="rhead-label">{{ pipelineActive ? '执行中' : '已完成' }}</span>
        </div>
        <h3 class="rhead-title">{{ pipelineActive || lastPipeline.length ? '产出区' : '对话历史' }}</h3>
        <button v-if="!pipelineActive && !lastPipeline.length" class="rhead-new-btn" @click="newConversation">
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none"><path d="M7 2v10M2 7h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
          新建
        </button>
      </div>

      <div class="rbody" v-if="pipelineActive || lastPipeline.length">
        <div class="pipeline">
          <div v-for="(step, idx) in displaySteps" :key="idx" class="step"
               :class="{ done:step.s==='done', active:step.s==='running', fail:step.s==='fail' }"
               @click="selectedStep = idx">
            <div class="step-indicator">
              <svg v-if="step.s==='done'" width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M2 7l3 3 7-7" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
              <div v-else-if="step.s==='running'" class="pulse-dot"></div>
              <svg v-else-if="step.s==='fail'" width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M3 3l8 8M3 11l8-8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
              </svg>
              <span v-else class="step-num">{{ idx+1 }}</span>
            </div>
            <div class="step-info">
              <div class="step-role">{{ step.role }}</div>
              <div class="step-status">{{ step.s==='done'?'完成':step.s==='running'?'执行中…':step.s==='fail'?'失败':'等待' }}</div>
            </div>
          </div>
        </div>

        <div v-if="selectedStep!==null && displaySteps[selectedStep]?.output" class="step-detail">
          <div class="detail-head">
            <span class="detail-role">{{ displaySteps[selectedStep].role }}</span>
            <button v-if="hasHtmlCode(displaySteps[selectedStep].output)" class="detail-action" @click="previewHtml(displaySteps[selectedStep].output)">
              {{ showPreview ? '📄 源码' : '🌐 预览' }}
            </button>
          </div>
          <div v-if="showPreview && htmlContent" class="html-preview-frame">
            <iframe :srcdoc="htmlContent" sandbox="allow-scripts" class="preview-iframe"></iframe>
          </div>
          <div v-else class="detail-body" v-html="md(displaySteps[selectedStep].output)"></div>
        </div>
      </div>

      <!-- 对话历史（空闲时常驻） -->
      <div class="rbody conv-history" v-else>
        <div v-if="conversationList.length === 0" class="empty-r">
          <p class="empty-r-text">还没有对话记录</p>
          <p class="empty-r-sub">发送消息会自动保存</p>
        </div>
        <div v-else class="conv-list">
          <div v-for="conv in conversationList.slice(0, 100)" :key="conv.id" class="conv-item"
               :class="{active: currentConversation?.id === conv.id}"
               @click="loadConversation(conv)">
            <div class="conv-body">
              <div class="conv-title">{{ conv.title || '未命名对话' }}</div>
              <div class="conv-meta">{{ (conv.messages||[]).length || 0 }} 条 · {{ formatTime(conv.updated_at) }}</div>
            </div>
            <button class="conv-delete" @click.stop="deleteConvById(conv.id)" title="删除">
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none"><path d="M3 3l6 6M3 9l6-6" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
            </button>
          </div>
        </div>
      </div>
    </aside>
  </div>
</template>

<script setup>
import {ref,nextTick,onMounted,computed} from 'vue'
import {marked} from 'marked'

// ---- state ----
const agents=ref([]),currentAgent=ref(''),messages=ref([]),txt=ref('')
const streaming=ref(false),buf=ref(''),msgEl=ref(null),inputEl=ref(null),lastMeta=ref(null)
const llmOnline=ref(false),modelName=ref('Qwen3-30B-A3B'),showSys=ref(false)
const roles=ref([]),workgroups=ref([])

// pipeline output panel
const pipelineActive=ref(false)
const pipelineSteps=ref([])
const lastPipeline=ref([])
const selectedStep=ref(null)

const groupLabels={general:'通用',dev:'开发团队',logistics:'后勤',management:'管理'}
const roleGroups=computed(()=>{
  const g={};roles.value.forEach(r=>{const c=r.group||'general';(g[c]=g[c]||[]).push(r)});return g
})
const displaySteps = computed(() => pipelineActive.value ? pipelineSteps.value : lastPipeline.value)

function md(t){try{return marked(t||'')}catch{return t||''}}

// ---- HTML 预览 ----
const showPreview = ref(false)
const htmlContent = ref('')

function hasHtmlCode(text) {
  return /<(!DOCTYPE|html|head|body|div|script|style)/i.test(text)
}
function extractHtml(text) {
  const match = text.match(/```(?:html)?\s*\n?([\s\S]*?)```/)
  if (match) return match[1]
  if (text.trim().startsWith('<')) {
    const lines = text.split('\n')
    const start = lines.findIndex(l => l.trim().startsWith('<!') || l.trim().startsWith('<html') || l.trim().startsWith('<'))
    if (start >= 0) return lines.slice(start).join('\n')
  }
  return text
}
function previewHtml(text) {
  if (showPreview.value) {
    showPreview.value = false
    htmlContent.value = ''
  } else {
    htmlContent.value = extractHtml(text)
    showPreview.value = true
  }
}

// ---- 对话管理 ----
const currentConversation=ref(null)
const conversationList=ref([])
const STORAGE_KEY = 'myagent_conversations'

function newConversation() {
  if (currentConversation.value && messages.value.length > 0) {
    saveCurrentToStorage()
  }
  const conv = {
    id: Date.now().toString(36),
    title: '新对话 ' + new Date().toLocaleTimeString(),
    agent_id: currentAgent.value,
    messages: [],
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }
  currentConversation.value = conv
  messages.value = []
  streaming.value = false
  buf.value = ''
  saveCurrentToStorage()
  refreshConversationList()
}

function saveCurrentToStorage() {
  if (!currentConversation.value) return
  currentConversation.value.messages = [...messages.value]
  currentConversation.value.updated_at = new Date().toISOString()
  const convs = loadFromStorage()
  const idx = convs.findIndex(c => c.id === currentConversation.value.id)
  if (idx >= 0) convs[idx] = currentConversation.value
  else convs.unshift(currentConversation.value)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(convs))
}

function loadFromStorage() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
  } catch { return [] }
}

function refreshConversationList() {
  conversationList.value = loadFromStorage()
}

function loadConversation(conv) {
  if (currentConversation.value && currentConversation.value.id !== conv.id && messages.value.length > 0) {
    saveCurrentToStorage()
  }
  currentConversation.value = { ...conv }
  messages.value = [...(conv.messages || [])]
  nextTick(scroll)
}

function deleteCurrentConversation() {
  if (!currentConversation.value) return
  if (!confirm('确定删除当前对话？')) return
  const convs = loadFromStorage().filter(c => c.id !== currentConversation.value.id)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(convs))
  currentConversation.value = null
  messages.value = []
  refreshConversationList()
}

function deleteConvById(id) {
  if (!confirm('删除此对话？')) return
  const convs = loadFromStorage().filter(c => c.id !== id)
  localStorage.setItem(STORAGE_KEY, JSON.stringify(convs))
  if (currentConversation.value?.id === id) {
    currentConversation.value = null
    messages.value = []
  }
  refreshConversationList()
}

function formatTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

// ---- data ----
async function loadAgents(){try{const r=await fetch('/api/agents');const d=await r.json();agents.value=d.agents||[];if(agents.value.length&&!currentAgent.value)selectAgent(agents.value[0].agent_id)}catch{}}
async function loadSys(){try{const r=await fetch('/api/system');const d=await r.json();roles.value=d.roles||[];workgroups.value=d.workgroups||[];if(d.gpu){llmOnline.value=d.gpu.llm_available;modelName.value=d.gpu.model||modelName.value}}catch{try{const r=await fetch('/api/health');const d=await r.json();llmOnline.value=d.llm_available}catch{}}}
function selectAgent(id){currentAgent.value=id;messages.value=[];loadHistory(id)}

// ---- send ----
async function send(){
  const text=txt.value.trim()
  if(!text||!currentAgent.value||streaming.value)return
  const t=text;txt.value='';resetInputHeight();messages.value.push({role:'user',content:t});scroll()

  if(!currentConversation.value){
    currentConversation.value={
      id: Date.now().toString(36),
      title: t.length>20 ? t.slice(0,20)+'...' : t,
      agent_id: currentAgent.value,
      messages:[],
      created_at:new Date().toISOString(),
      updated_at:new Date().toISOString(),
    }
  }

  streaming.value=true;buf.value=''
  pipelineActive.value=true
  pipelineSteps.value=[{role:'匹配中…',s:'running',output:''}]
  selectedStep.value=0

  const ws=new WebSocket((location.protocol==='https:'?'wss':'ws')+'://'+location.host+'/api/agents/'+currentAgent.value+'/ws')
  ws.onopen=()=>ws.send(JSON.stringify({message:t}))
  ws.onmessage=e=>{
    const d=JSON.parse(e.data)
    if(d.type==='stream_token'){buf.value+=d.content;scroll()}
    else if(d.type==='stream_meta'){
      lastMeta.value={type:d.dispatch_type,workgroup:d.workgroup,roles_used:d.roles_used}
      if(d.roles_used?.length){
        pipelineSteps.value=d.roles_used.map((r,i)=>({role:r,s:i===0?'running':'pending',output:''}))
        selectedStep.value=0
      }
    }
    else if(d.type==='stream_end'){
      const final = buf.value
      messages.value.push({role:'assistant',content:final,meta:lastMeta.value||undefined})
      buf.value='';lastMeta.value=null;streaming.value=false;ws.close()

      saveCurrentToStorage()
      refreshConversationList()

      if(pipelineActive.value && pipelineSteps.value.length){
        try {
          const results = parsePipelineOutput(final)
          if(results.length){
            pipelineSteps.value = pipelineSteps.value.map((s,i)=>({
              ...s,s:'done',
              output:results[i]?.content||'已完成'
            }))
          } else {
            pipelineSteps.value = pipelineSteps.value.map(s=>({...s,s:'done',output:'已完成'}))
          }
        } catch {
          pipelineSteps.value = pipelineSteps.value.map(s=>({...s,s:'done',output:'已完成'}))
        }
        lastPipeline.value = [...pipelineSteps.value]
        selectedStep.value = 0
      }
      pipelineActive.value = false
    }
  }
  ws.onerror=()=>{streaming.value=false;buf.value='';pipelineActive.value=false}
}

function parsePipelineOutput(text) {
  const steps = []
  const pattern = /(?:####?\s*)?步骤\s*(\d+)\s*[:：]\s*(\S+)/g
  const matches = [...text.matchAll(pattern)]
  if(!matches.length) return []
  const segments = text.split(/(?:####?\s*)?步骤\s*\d+\s*[:：]\s*\S+/)
  matches.forEach((m,i) => {
    steps.push({num:m[1], role:m[2], content: (segments[i+1]||'').trim().slice(0,500)})
  })
  return steps
}

function sendQuick(t){txt.value=t;nextTick(()=>{send()})}
function triggerWg(wg){txt.value=(wg.trigger_keywords||[])[0]||wg.id;nextTick(()=>{send()})}
function scroll(){nextTick(()=>{if(msgEl.value)msgEl.value.scrollTop=msgEl.value.scrollHeight})}
function resetInputHeight(){if(inputEl.value)inputEl.value.style.height='auto'}
function autoResize(e){const el=e.target;el.style.height='auto';el.style.height=Math.min(el.scrollHeight,160)+'px'}

onMounted(()=>{
  loadAgents();loadSys();setInterval(loadSys,15000)
  refreshConversationList()
  const convs = loadFromStorage()
  if(convs.length>0 && !currentConversation.value){
    loadConversation(convs[0])
  }
})
</script>

<style scoped>
/* ==========================================
   设计系统 — 浅色系 + 紫蓝主调
   ========================================== */
.agent-platform {
  display: grid;
  grid-template-columns: 280px 1fr 360px;
  height: 100vh;
  background: #f0f2f5;
  color: #1a1a2e;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
  font-feature-settings: "cv11", "ss01";
  overflow: hidden;
}

/* 滚动条 */
.agent-platform ::-webkit-scrollbar { width: 6px; height: 6px; }
.agent-platform ::-webkit-scrollbar-track { background: transparent; }
.agent-platform ::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 3px; }
.agent-platform ::-webkit-scrollbar-thumb:hover { background: #9ca3af; }

/* ==========================================
   左栏
   ========================================== */
.left-panel {
  background: #fff;
  border-right: 1px solid #e5e7eb;
  overflow-y: auto;
  padding: 16px 14px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.system-card {
  position: relative;
  background: linear-gradient(135deg, #f0f4ff, #e8f5ff);
  border: 1px solid #c7d2fe;
  border-radius: 14px;
  padding: 14px;
  transition: all 0.2s;
}
.system-card:hover { border-color: #a5b4fc; }
.system-card.online { border-color: #6ee7b7; background: linear-gradient(135deg, #ecfdf5, #d1fae5); }

.system-status { display: flex; align-items: center; gap: 12px; }
.status-indicator {
  width: 10px; height: 10px; border-radius: 50%;
  background: #6b7280; box-shadow: 0 0 0 3px rgba(107,114,128,0.15);
}
.system-card.online .status-indicator {
  background: #10b981; box-shadow: 0 0 0 3px rgba(16,185,129,0.2);
  animation: pulse-glow 2s ease-in-out infinite;
}
@keyframes pulse-glow {
  0%,100% { box-shadow: 0 0 0 3px rgba(16,185,129,0.2); }
  50% { box-shadow: 0 0 0 5px rgba(16,185,129,0.1); }
}
.status-info { flex: 1; min-width: 0; }
.status-label { font-size: 11px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.5px; }
.status-model { font-size: 13px; color: #1f2937; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.system-stats {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px;
  margin-top: 12px; padding-top: 12px; border-top: 1px solid #e5e7eb;
}
.stat { text-align: center; }
.stat-num { display: block; font-size: 18px; font-weight: 600; color: #4f46e5; }
.stat-label { font-size: 10px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.5px; }

.expand-btn {
  position: absolute; top: 14px; right: 14px;
  background: none; border: none; color: #9ca3af; cursor: pointer; padding: 2px;
  transition: transform 0.2s;
}
.expand-btn svg { transition: transform 0.2s; }
.expand-btn svg.rotated { transform: rotate(180deg); }

/* 侧栏分区 */
.sidebar-section { display: flex; flex-direction: column; gap: 8px; }
.section-header {
  display: flex; align-items: center; gap: 8px;
  padding: 0 4px; cursor: pointer; user-select: none;
}
.section-header h3 {
  font-size: 11px; font-weight: 600; color: #9ca3af;
  text-transform: uppercase; letter-spacing: 1px; margin: 0;
}
.section-badge {
  font-size: 10px; color: #4f46e5; background: #eef2ff;
  padding: 1px 6px; border-radius: 8px; font-weight: 600;
}
.section-arrow { margin-left: auto; color: #9ca3af; transition: transform 0.2s; }
.section-arrow.rotated { transform: rotate(180deg); }
.section-new-btn {
  margin-left: auto; width: 24px; height: 24px; border-radius: 6px;
  background: #4f46e5; color: #fff; border: none;
  display: flex; align-items: center; justify-content: center;
  cursor: pointer; transition: all 0.15s;
}
.section-new-btn:hover { background: #6366f1; transform: scale(1.05); }

/* ==== 工作组顶部横栏 ==== */
.workgroup-bar {
  display: flex; align-items: center; gap: 6px;
  padding: 8px 24px; background: #f9fafb;
  border-bottom: 1px solid #e5e7eb; flex-shrink: 0;
  overflow-x: auto; flex-wrap: nowrap;
  scrollbar-width: thin;
}
.workgroup-bar::-webkit-scrollbar { height: 4px; }
.wg-bar-label { font-size: 11px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.5px; flex-shrink: 0; margin-right: 4px; }
.wg-chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 12px; background: #fff;
  border: 1px solid #e5e7eb; border-radius: 16px;
  font-size: 12px; color: #4b5563;
  cursor: pointer; transition: all 0.15s; flex-shrink: 0;
  white-space: nowrap;
}
.wg-chip:hover {
  background: #eef2ff; border-color: #c7d2fe; color: #4f46e5;
  transform: translateY(-1px);
}
.wg-chip svg { color: #4f46e5; flex-shrink: 0; }
.wg-chip-name { font-weight: 500; }
.wg-chip-steps { font-size: 10px; color: #9ca3af; padding: 1px 5px; background: #f3f4f6; border-radius: 8px; }

/* 智能体列表 */
.agent-list { display: flex; flex-direction: column; gap: 4px; }
.agent-card {
  display: flex; align-items: center; gap: 10px;
  padding: 10px; border-radius: 10px; cursor: pointer;
  transition: all 0.15s; border: 1px solid transparent;
}
.agent-card:hover { background: #f9fafb; }
.agent-card.active {
  background: linear-gradient(135deg, #eef2ff, #eef2ff);
  border-color: #c7d2fe;
}
.agent-avatar {
  width: 32px; height: 32px; border-radius: 8px;
  background: linear-gradient(135deg, #4f46e5, #6366f1);
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; flex-shrink: 0;
}
.agent-info { flex: 1; min-width: 0; }
.agent-name { font-size: 13px; color: #1f2937; font-weight: 500; }
.agent-desc { font-size: 11px; color: #9ca3af; margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 工作组列表 */
.workgroup-list { display: flex; flex-direction: column; gap: 6px; }
.workgroup-card {
  padding: 10px 12px; border-radius: 10px; cursor: pointer;
  background: #f9fafb;
  border: 1px solid #f3f4f6;
  transition: all 0.15s;
}
.workgroup-card:hover {
  background: #eef2ff;
  border-color: #c7d2fe;
  transform: translateX(2px);
}
.wg-name { font-size: 13px; font-weight: 500; color: #1f2937; margin-bottom: 4px; }
.wg-desc { font-size: 11px; color: #9ca3af; line-height: 1.4; margin-bottom: 8px; }
.wg-footer { display: flex; justify-content: space-between; align-items: center; }
.wg-steps {
  font-size: 10px; color: #6366f1; background: #eef2ff;
  padding: 1px 6px; border-radius: 4px; font-weight: 600;
}
.wg-kws { font-size: 10px; color: #4f46e5; }

/* ==========================================
   中栏 - 对话
   ========================================== */
.chat-col {
  display: flex; flex-direction: column; min-width: 0;
  background: #f8f9fb;
  position: relative;
}

.chat-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 24px; border-bottom: 1px solid #e5e7eb;
  background: rgba(255,255,255,0.95); backdrop-filter: blur(12px);
  flex-shrink: 0;
}
.chat-title-area { display: flex; align-items: center; gap: 12px; min-width: 0; }
.chat-title { font-size: 16px; font-weight: 600; color: #1f2937; margin: 0; }
.title-placeholder { color: #6b7280; font-weight: 500; }
.msg-count {
  font-size: 11px; color: #9ca3af; background: #f3f4f6;
  padding: 2px 8px; border-radius: 10px;
}
.chat-actions { display: flex; gap: 6px; }
.action-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 12px; font-size: 12px; font-weight: 500;
  background: #f9fafb; color: #4b5563;
  border: 1px solid #e5e7eb;
  border-radius: 8px; cursor: pointer; transition: all 0.15s;
}
.action-btn:hover:not(:disabled) {
  background: #eef2ff;
  border-color: #c7d2fe;
  color: #1f2937;
}
.action-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.action-btn.danger:hover:not(:disabled) {
  background: rgba(232,70,58,0.15);
  border-color: rgba(232,70,58,0.4);
  color: #fca5a5;
}

/* 历史面板 */
.history-panel {
  position: absolute; top: 60px; right: 20px;
  width: 320px; max-height: 480px; overflow-y: auto;
  background: rgba(15,15,26,0.98);
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  box-shadow: 0 12px 40px rgba(0,0,0,0.1);
  backdrop-filter: blur(20px);
  z-index: 100;
}
.slide-enter-active, .slide-leave-active { transition: all 0.2s ease; }
.slide-enter-from, .slide-leave-to { opacity: 0; transform: translateY(-8px); }
.history-head {
  display: flex; align-items: center; justify-content: space-between;
  padding: 14px 16px; border-bottom: 1px solid #e5e7eb;
}
.history-head h3 { font-size: 13px; font-weight: 600; color: #1f2937; margin: 0; }
.close-btn {
  width: 24px; height: 24px; background: none; border: none;
  color: #9ca3af; cursor: pointer; font-size: 18px; line-height: 1;
}
.close-btn:hover { color: #1f2937; }
.history-empty { padding: 40px 20px; text-align: center; color: #6b7280; }
.history-empty .empty-icon { font-size: 32px; margin-bottom: 8px; }
.history-item {
  padding: 12px 16px; border-bottom: 1px solid #f9fafb;
  cursor: pointer; transition: background 0.15s;
}
.history-item:hover { background: #f9fafb; }
.history-item.active {
  background: linear-gradient(90deg, #c7d2fe, transparent);
  border-left: 2px solid #4f46e5;
}
.conv-title { font-size: 13px; color: #1f2937; font-weight: 500; margin-bottom: 4px; }
.conv-meta { font-size: 11px; color: #9ca3af; }

/* 消息区 */
.messages {
  flex: 1; overflow-y: auto; padding: 24px;
  display: flex; flex-direction: column; gap: 16px; min-width: 0;
}
.messages > * { max-width: 100%; min-width: 0; }

/* 空状态 */
.empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  height: 100%; text-align: center; padding: 40px 20px;
}
.empty-icon { font-size: 64px; margin-bottom: 20px; opacity: 0.6; }
.empty-title { font-size: 22px; font-weight: 600; color: #1f2937; margin: 0 0 8px; }
.empty-sub { font-size: 14px; color: #9ca3af; margin: 0 0 32px; }
.quick-pills { display: flex; flex-wrap: wrap; gap: 10px; justify-content: center; max-width: 600px; }
.pill {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 10px 16px; font-size: 13px; color: #4b5563;
  background: #f9fafb; border: 1px solid #e5e7eb;
  border-radius: 20px; cursor: pointer; transition: all 0.15s;
}
.pill:hover {
  background: #eef2ff;
  border-color: #c7d2fe;
  color: #1f2937;
  transform: translateY(-1px);
}
.pill.primary {
  background: linear-gradient(135deg, #c7d2fe, #eef2ff);
  border-color: #c7d2fe;
}
.pill-icon { font-size: 16px; }

/* 消息气泡 */
.msg { display: flex; gap: 12px; max-width: 800px; }
.msg.user { margin-left: auto; flex-direction: row-reverse; }
.msg-avatar {
  width: 32px; height: 32px; border-radius: 8px; flex-shrink: 0;
  background: linear-gradient(135deg, #4f46e5, #6366f1);
  display: flex; align-items: center; justify-content: center;
  font-size: 16px;
}
.msg-content { min-width: 0; max-width: calc(100% - 44px); display: flex; flex-direction: column; gap: 6px; }
.bubble {
  padding: 12px 16px; border-radius: 14px; font-size: 14px; line-height: 1.65;
  word-wrap: break-word; word-break: break-word; overflow-wrap: break-word;
  white-space: pre-wrap; max-width: 100%;
}
.bubble * { max-width: 100%; }
.bubble p { margin: 0 0 8px; }
.bubble p:last-child { margin-bottom: 0; }
.bubble code {
  font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 12.5px;
  background: #f1f3f5; color: #d6336c; padding: 1px 6px; border-radius: 4px;
  border: 1px solid #e9ecef; white-space: pre-wrap; word-break: break-all;
}
.bubble pre {
  background: #f8f9fa; color: #1f2937;
  border: 1px solid #e5e7eb; border-radius: 8px;
  padding: 12px 14px; overflow-x: auto; margin: 8px 0;
  font-size: 12.5px; line-height: 1.6;
}
.bubble pre code { background: none; padding: 0; border: none; color: #1f2937; }
.bubble table { display: block; max-width: 100%; overflow-x: auto; border-collapse: collapse; }
.bubble table th, .bubble table td { border: 1px solid #e5e7eb; padding: 6px 10px; }
.bubble table th { background: #f3f4f6; font-weight: 600; color: #111827; }
.bubble ul, .bubble ol { padding-left: 20px; margin: 8px 0; }
.bubble li { margin: 4px 0; }
.bubble h1, .bubble h2, .bubble h3 { margin: 12px 0 8px; font-weight: 600; }
.bubble h1 { font-size: 18px; } .bubble h2 { font-size: 16px; } .bubble h3 { font-size: 14px; }

.msg.user .bubble {
  background: #fff;
  border: 1px solid #e5e7eb;
  color: #1f2937; border-bottom-right-radius: 4px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.02);
}
.msg.assistant .bubble {
  background: #fff;
  border: 1px solid #e5e7eb;
  color: #1f2937; border-bottom-left-radius: 4px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.02);
}
.bubble.streaming { min-height: 44px; }

.cursor-blink { color: #4f46e5; animation: blink 1s steps(2) infinite; }
@keyframes blink { 50% { opacity: 0; } }

/* 元信息 */
.msg-meta { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 0 4px; }
.meta-tag {
  display: inline-flex; align-items: center; gap: 4px;
  font-size: 11px; color: #6366f1; background: #eef2ff;
  padding: 2px 8px; border-radius: 10px; font-weight: 500;
}
.meta-roles { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; color: #9ca3af; }
.meta-roles-text { font-family: "SF Mono", Menlo, monospace; }
.meta-badge { color: #10b981; font-weight: 600; }

/* 输入栏 */
.input-bar { padding: 8px 24px 12px; flex-shrink: 0; background: #fff; border-top: 1px solid #e5e7eb; }
.input-wrap {
  display: flex; align-items: flex-end; gap: 10px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 14px; padding: 8px 8px 8px 16px;
  transition: all 0.2s;
}
.input-wrap:focus-within {
  border-color: rgba(108,92,231,0.5);
  background: #f3f4f6;
  box-shadow: 0 0 0 3px #eef2ff;
}
.input {
  flex: 1; background: none; border: none; outline: none;
  color: #1f2937; font-size: 14px; line-height: 1.5; resize: none;
  font-family: inherit; min-height: 24px; max-height: 160px;
  padding: 6px 0;
}
.input::placeholder { color: #6b7280; }
.input:disabled { opacity: 0.5; }

.send-btn {
  width: 36px; height: 36px; border-radius: 10px; flex-shrink: 0;
  background: linear-gradient(135deg, #4f46e5, #6366f1);
  border: none; color: #fff; cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.send-btn:hover:not(:disabled) {
  transform: scale(1.05);
  box-shadow: 0 4px 12px #c7d2fe;
}
.send-btn:disabled { opacity: 0.4; cursor: not-allowed; }

.loading-dots { display: flex; gap: 3px; }
.loading-dots span {
  width: 4px; height: 4px; background: #fff; border-radius: 50%;
  animation: dot-bounce 1.4s infinite ease-in-out both;
}
.loading-dots span:nth-child(2) { animation-delay: 0.16s; }
.loading-dots span:nth-child(3) { animation-delay: 0.32s; }
@keyframes dot-bounce {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
  40% { transform: scale(1); opacity: 1; }
}

.input-hint { text-align: center; font-size: 11px; color: #6b7280; margin-top: 8px; }

/* ==========================================
   右栏 - 产出区
   ========================================== */
.right-panel {
  background: linear-gradient(180deg, #ffffff 0%, #fafbfc 100%);
  border-left: 1px solid #e5e7eb;
  display: flex; flex-direction: column; min-width: 0;
}
.rhead {
  padding: 18px 20px; border-bottom: 1px solid #e5e7eb;
}
.rhead-status { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.rhead-dot { width: 8px; height: 8px; border-radius: 50%; }
.rhead-dot.idle { background: #6b7280; }
.rhead-dot.active { background: #4f46e5; animation: pulse-glow 1.5s infinite; }
.rhead-dot.done { background: #10b981; }
.rhead-label { font-size: 11px; color: #9ca3af; text-transform: uppercase; letter-spacing: 0.5px; }
.rhead-title { font-size: 15px; font-weight: 600; color: #1f2937; margin: 0; }

.rbody { flex: 1; overflow-y: auto; padding: 16px 20px; }
.rbody.empty { display: flex; flex-direction: column; align-items: center; justify-content: center; }
.empty-illustration { color: #4f46e5; opacity: 0.4; margin-bottom: 16px; }
.empty-r-text { font-size: 14px; color: #4b5563; margin: 0 0 4px; }
.empty-r-sub { font-size: 12px; color: #6b7280; margin: 0; text-align: center; }

/* 流水线 */
.pipeline { display: flex; flex-direction: column; gap: 8px; }
.step {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 12px; border-radius: 10px; cursor: pointer;
  background: #f9fafb;
  border: 1px solid #f9fafb;
  transition: all 0.15s;
}
.step:hover { background: #f3f4f6; }
.step.active {
  background: linear-gradient(90deg, #eef2ff, transparent);
  border-color: #c7d2fe;
}
.step.done .step-indicator { background: rgba(16,185,129,0.2); color: #10b981; }
.step.fail .step-indicator { background: rgba(232,70,58,0.2); color: #e8463a; }

.step-indicator {
  width: 28px; height: 28px; border-radius: 8px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  background: #f3f4f6; color: #6b7280;
  font-size: 12px; font-weight: 600;
}
.pulse-dot {
  width: 8px; height: 8px; background: #4f46e5; border-radius: 50%;
  animation: pulse-glow 1.2s ease-in-out infinite;
}
.step-info { flex: 1; min-width: 0; }
.step-role { font-size: 13px; font-weight: 500; color: #1f2937; }
.step-status { font-size: 11px; color: #9ca3af; margin-top: 2px; }
.step.active .step-role { color: #4f46e5; }
.step.active .step-status { color: #6366f1; }

/* 步骤详情 */
.step-detail { margin-top: 16px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 10px; overflow: hidden; }
.detail-head {
  padding: 10px 14px; border-bottom: 1px solid #e5e7eb;
  display: flex; align-items: center; justify-content: space-between;
}
.detail-role { font-size: 12px; font-weight: 600; color: #6366f1; }
.detail-action {
  font-size: 11px; padding: 3px 10px; border-radius: 6px;
  background: #eef2ff; color: #4b5563;
  border: 1px solid #c7d2fe; cursor: pointer; transition: all 0.15s;
}
.detail-action:hover { background: #c7d2fe; }
.detail-body { padding: 14px; font-size: 13px; line-height: 1.6; color: #4b5563; max-height: 400px; overflow-y: auto; }
.detail-body * { max-width: 100%; }
.html-preview-frame { border-top: 1px solid #e5e7eb; }
.preview-iframe { width: 100%; height: 400px; border: none; background: #fff; }

/* ==== 右侧对话历史 ==== */
.conv-history { display: flex; flex-direction: column; }
.empty-r { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; text-align: center; padding: 40px 20px; }
.empty-r-text { font-size: 14px; color: #4b5563; margin-bottom: 4px; }
.empty-r-sub { font-size: 12px; color: #6b7280; }

.rhead-new-btn {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 14px; font-size: 12px; font-weight: 500;
  background: linear-gradient(135deg, #4f46e5, #6366f1);
  color: #fff; border: none; border-radius: 8px;
  cursor: pointer; transition: all 0.15s;
}
.rhead-new-btn:hover { transform: translateY(-1px); box-shadow: 0 2px 8px rgba(108,92,231,.4); }

.conv-list { display: flex; flex-direction: column; overflow-y: auto; }
.conv-item {
  display: flex; align-items: center; padding: 12px 16px;
  border-bottom: 1px solid #f9fafb;
  cursor: pointer; transition: background 0.15s; gap: 10px;
}
.conv-item:hover { background: #f9fafb; }
.conv-item.active {
  background: linear-gradient(90deg, #eef2ff, transparent);
  border-left: 3px solid #4f46e5;
}
.conv-body { flex: 1; min-width: 0; }
.conv-title { font-size: 13px; color: #1f2937; font-weight: 500; margin-bottom: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.conv-meta { font-size: 11px; color: #9ca3af; }
.conv-delete {
  width: 22px; height: 22px; border-radius: 5px;
  background: none; border: none; color: #6b7280;
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: all 0.15s; flex-shrink: 0;
}
.conv-item:hover .conv-delete { opacity: 1; }
.conv-delete:hover { background: rgba(232,70,58,.2); color: #fca5a5; }
</style>
