<template>
  <div class="module-renderer" :class="['tpl-' + config.template, 'layout-' + config.layout]">
    <!-- 模块头部 -->
    <div class="module-header">
      <span class="module-icon">{{ getIcon(config.icon) }}</span>
      <span class="module-title">{{ config.name }}</span>
      <div class="module-actions" v-if="editing">
        <button class="btn-action" @click="$emit('remove')" title="移除">×</button>
      </div>
    </div>

    <!-- 模块内容区 — 根据 template 渲染不同 UI -->
    <div class="module-body">
      <!-- 对话界面 -->
      <template v-if="config.template === 'chat_view'">
        <div class="mini-chat">
          <div class="mini-chat-messages" ref="chatScrollEl">
            <div v-for="(msg, i) in localData.messages || []" :key="i"
                 class="mini-msg" :class="msg.role">
              {{ msg.content }}
            </div>
          </div>
          <div class="mini-chat-input">
            <input v-model="chatInput" placeholder="输入消息..."
                   @keyup.enter="sendMiniChat" :disabled="chatStreaming" />
            <button @click="sendMiniChat" :disabled="chatStreaming || !chatInput">发送</button>
          </div>
        </div>
      </template>

      <!-- 看板任务 -->
      <template v-else-if="config.template === 'kanban_task'">
        <div class="kanban-board">
          <div v-for="col in kanbanColumns" :key="col" class="kanban-col">
            <div class="kanban-col-header">{{ col }} ({{ getKanbanItems(col).length }})</div>
            <div class="kanban-items">
              <div v-for="item in getKanbanItems(col)" :key="item.id" class="kanban-item"
                   :class="'priority-' + (item.priority || '中')">
                <div class="kanban-item-title">{{ item.title }}</div>
                <div class="kanban-item-meta" v-if="item.due_date">{{ item.due_date }}</div>
              </div>
            </div>
            <button class="kanban-add" @click="addKanbanItem(col)">+ 添加</button>
          </div>
        </div>
      </template>

      <!-- 笔记/书签/代码片段/版本历史/文件浏览 (sidebar_list 布局) -->
      <template v-else-if="config.layout === 'sidebar_list'">
        <div class="sidebar-list-layout">
          <div class="sll-sidebar">
            <input v-model="searchQuery" class="sll-search" placeholder="搜索..." />
            <div class="sll-list">
              <div v-for="item in filteredItems" :key="item.id"
                   class="sll-item" :class="{active: selectedItem === item.id}"
                   @click="selectItem(item.id)">
                <div class="sll-item-title">{{ item.title || item.name || item.filename || '#' + item.id }}</div>
                <div class="sll-item-meta" v-if="item.category || item.language">{{ item.category || item.language }}</div>
              </div>
            </div>
            <button class="sll-add" @click="addNewItem">+ 新建</button>
          </div>
          <div class="sll-detail">
            <div v-if="currentItem">
              <div v-for="field in config.fields" :key="field.name" class="field-row">
                <label class="field-label">{{ field.label }}</label>
                <component :is="getFieldComponent(field.type)"
                           v-model="currentItem[field.name]"
                           :options="field.options"
                           :placeholder="field.placeholder || ''"
                           class="field-input" />
              </div>
            </div>
            <div v-else class="empty-state">选择或新建一项</div>
          </div>
        </div>
      </template>

      <!-- Markdown 编辑器 -->
      <template v-else-if="config.template === 'markdown_editor'">
        <div class="md-editor-layout">
          <div class="md-editor-pane">
            <input v-model="currentItem.title" class="md-title-input" placeholder="标题..." />
            <textarea v-model="currentItem.content" class="md-textarea"
                      placeholder="输入 Markdown..." @input="updateMdPreview"></textarea>
          </div>
          <div class="md-preview-pane" v-html="mdPreviewHtml"></div>
        </div>
      </template>

      <!-- 代码编辑器 -->
      <template v-else-if="config.template === 'code_editor'">
        <div class="code-editor-layout">
          <div class="code-toolbar">
            <input v-model="currentItem.filename" class="code-filename" placeholder="文件名..." />
            <select v-model="currentItem.language" class="code-lang">
              <option v-for="lang in getLangOptions()" :key="lang" :value="lang">{{ lang }}</option>
            </select>
          </div>
          <textarea v-model="currentItem.content" class="code-textarea"
                    :class="'lang-' + (currentItem.language || 'python')"
                    spellcheck="false" placeholder="输入代码..."></textarea>
        </div>
      </template>

      <!-- 双栏对比/对照翻译/Git diff -->
      <template v-else-if="['dual_column_compare', 'bilingual_compare', 'git_diff'].includes(config.template)">
        <div class="dual-pane-layout">
          <div class="dual-pane">
            <div class="dual-pane-header">{{ dualLeftLabel }}</div>
            <textarea v-model="currentItem[dualLeftField]"
                      class="dual-textarea" spellcheck="false"></textarea>
          </div>
          <div class="dual-pane">
            <div class="dual-pane-header">{{ dualRightLabel }}</div>
            <textarea v-model="currentItem[dualRightField]"
                      class="dual-textarea" spellcheck="false"></textarea>
          </div>
        </div>
      </template>

      <!-- 翻译面板 -->
      <template v-else-if="config.template === 'translation_panel'">
        <div class="translate-layout">
          <div class="translate-controls">
            <select v-model="currentItem.source_lang" class="translate-select">
              <option v-for="opt in getSourceLangOptions()" :key="opt" :value="opt">{{ opt }}</option>
            </select>
            <span class="translate-arrow">→</span>
            <select v-model="currentItem.target_lang" class="translate-select">
              <option v-for="opt in getTargetLangOptions()" :key="opt" :value="opt">{{ opt }}</option>
            </select>
          </div>
          <textarea v-model="currentItem.source_text" class="translate-source"
                    placeholder="输入要翻译的文本..."></textarea>
          <div class="translate-result">{{ currentItem.translated_text || '译文将显示在这里' }}</div>
        </div>
      </template>

      <!-- 日历日程 -->
      <template v-else-if="config.template === 'calendar_schedule'">
        <div class="calendar-layout">
          <div class="calendar-header">
            <button @click="prevMonth">‹</button>
            <span>{{ calendarYear }}年 {{ calendarMonth + 1 }}月</span>
            <button @click="nextMonth">›</button>
          </div>
          <div class="calendar-grid">
            <div v-for="day in calendarDays" :key="day.key" class="calendar-day"
                 :class="{today: day.isToday, hasEvent: day.events.length > 0}">
              <span class="day-num">{{ day.num }}</span>
              <div v-for="event in day.events.slice(0, 2)" :key="event.id" class="day-event">{{ event.title }}</div>
            </div>
          </div>
        </div>
      </template>

      <!-- 番茄钟 -->
      <template v-else-if="config.template === 'timer_pomodoro'">
        <div class="pomodoro-layout">
          <div class="pomodoro-timer" :class="{working: pomoRunning, break: pomoOnBreak}">
            {{ formatTime(pomoRemaining) }}
          </div>
          <div class="pomodoro-status">{{ pomoStatusText }}</div>
          <div class="pomodoro-controls">
            <button @click="togglePomodoro" class="pomo-btn">{{ pomoRunning ? '暂停' : '开始' }}</button>
            <button @click="resetPomodoro" class="pomo-btn">重置</button>
          </div>
          <div class="pomodoro-cycles">完成 {{ pomoCompletedCycles }} 轮</div>
        </div>
      </template>

      <!-- 内嵌浏览器 -->
      <template v-else-if="config.template === 'embedded_browser'">
        <div class="browser-layout">
          <div class="browser-toolbar">
            <input v-model="currentItem.url" class="browser-url" placeholder="https://..."
                   @keyup.enter="navigateBrowser" />
            <button @click="navigateBrowser">前往</button>
          </div>
          <iframe :src="browserUrl" class="browser-frame" v-if="browserUrl"
                  sandbox="allow-scripts allow-same-origin"></iframe>
          <div v-else class="browser-empty">输入网址开始浏览</div>
        </div>
      </template>

      <!-- 图片查看器 -->
      <template v-else-if="config.template === 'image_viewer'">
        <div class="image-viewer-layout">
          <div class="iv-grid">
            <div v-for="img in localData.images || []" :key="img.id" class="iv-thumb"
                 @click="previewImage = img">
              <img :src="img.url" :alt="img.title" />
            </div>
          </div>
          <button class="iv-add" @click="addImage">+ 添加图片</button>
        </div>
      </template>

      <!-- 终端面板 -->
      <template v-else-if="config.template === 'terminal_panel'">
        <div class="terminal-layout">
          <div class="terminal-output" ref="terminalEl">
            <div v-for="(line, i) in terminalLines" :key="i" class="terminal-line">{{ line }}</div>
          </div>
          <div class="terminal-input">
            <span class="terminal-prompt">$</span>
            <input v-model="terminalInput" class="terminal-cmd"
                   @keyup.enter="execTerminal" placeholder="输入命令..." />
          </div>
        </div>
      </template>

      <!-- 数据仪表盘 -->
      <template v-else-if="config.template === 'data_dashboard'">
        <div class="dashboard-layout">
          <div class="dashboard-stats">
            <div v-for="stat in localData.stats || defaultStats" :key="stat.label" class="stat-card">
              <div class="stat-value">{{ stat.value }}</div>
              <div class="stat-label">{{ stat.label }}</div>
            </div>
          </div>
          <div class="dashboard-chart">
            <div class="chart-placeholder">图表区域 ({{ currentItem.chart_type || '折线图' }})</div>
          </div>
        </div>
      </template>

      <!-- 时间线浏览 -->
      <template v-else-if="config.template === 'timeline_browse'">
        <div class="timeline-layout">
          <div v-for="event in localData.events || []" :key="event.id" class="timeline-item">
            <div class="timeline-time">{{ event.timestamp }}</div>
            <div class="timeline-dot"></div>
            <div class="timeline-content">
              <div class="timeline-event">{{ event.event }}</div>
              <div class="timeline-details" v-if="event.details">{{ event.details }}</div>
            </div>
          </div>
        </div>
      </template>

      <!-- 全局搜索 -->
      <template v-else-if="config.template === 'global_search'">
        <div class="search-layout">
          <input v-model="searchQuery" class="search-input" placeholder="全局搜索..."
                 @keyup.enter="doGlobalSearch" />
          <select v-model="currentItem.scope" class="search-scope">
            <option v-for="opt in ['全部', '笔记', '对话', '任务', '文件']" :key="opt" :value="opt">{{ opt }}</option>
          </select>
          <div class="search-results">
            <div v-for="result in searchResults" :key="result.id" class="search-result-item">
              <div class="result-title">{{ result.title }}</div>
              <div class="result-snippet">{{ result.snippet }}</div>
            </div>
          </div>
        </div>
      </template>

      <!-- 画板白板 -->
      <template v-else-if="config.template === 'canvas_whiteboard'">
        <div class="canvas-layout">
          <div class="canvas-toolbar">
            <button v-for="t in ['画笔', '矩形', '圆形', '文字', '橡皮擦']" :key="t"
                    @click="canvasTool = t" :class="{active: canvasTool === t}">{{ t }}</button>
            <input type="color" v-model="canvasColor" class="canvas-color" />
            <button @click="clearCanvas">清空</button>
          </div>
          <canvas ref="canvasEl" class="canvas-area" @mousedown="startDraw" @mousemove="draw" @mouseup="stopDraw"></canvas>
        </div>
      </template>

      <!-- 调色板 -->
      <template v-else-if="config.template === 'color_palette'">
        <div class="palette-layout">
          <input type="color" v-model="currentItem.color" class="palette-picker" />
          <div class="palette-info">
            <div class="palette-hex">{{ currentItem.color }}</div>
            <input v-model="currentItem.name" class="palette-name" placeholder="颜色名称" />
          </div>
          <div class="palette-grid">
            <div v-for="c in localData.colors || defaultColors" :key="c"
                 class="palette-swatch" :style="{background: c}"
                 @click="currentItem.color = c"></div>
          </div>
        </div>
      </template>

      <!-- 树形大纲 -->
      <template v-else-if="config.template === 'tree_outline'">
        <div class="tree-layout">
          <div v-for="node in treeData" :key="node.id" class="tree-node"
               :style="{marginLeft: (node.level * 20) + 'px'}">
            <span class="tree-toggle" @click="node.expanded = !node.expanded">{{ node.expanded ? '▼' : '▶' }}</span>
            <span class="tree-title">{{ node.title }}</span>
          </div>
        </div>
      </template>

      <!-- API 测试器 -->
      <template v-else-if="config.template === 'api_tester'">
        <div class="api-layout">
          <div class="api-request">
            <div class="api-row">
              <select v-model="currentItem.method" class="api-method">
                <option v-for="m in ['GET', 'POST', 'PUT', 'DELETE', 'PATCH']" :key="m">{{ m }}</option>
              </select>
              <input v-model="currentItem.url" class="api-url" placeholder="https://api.example.com/..." />
              <button @click="sendApiRequest" class="api-send">发送</button>
            </div>
            <textarea v-model="currentItem.body" class="api-body" placeholder='{"key": "value"}' spellcheck="false"></textarea>
          </div>
          <div class="api-response">
            <div class="api-status">状态: {{ currentItem.status_code || '-' }}</div>
            <pre class="api-result">{{ currentItem.response || '响应将显示在这里' }}</pre>
          </div>
        </div>
      </template>

      <!-- 通用表单/兜底渲染 -->
      <template v-else>
        <div class="generic-form">
          <div v-for="field in config.fields" :key="field.name" class="field-row">
            <label class="field-label">
              {{ field.label }}
              <span v-if="field.required" class="required">*</span>
            </label>
            <component :is="getFieldComponent(field.type)"
                       v-model="currentItem[field.name]"
                       :options="field.options"
                       :placeholder="field.placeholder || ''"
                       class="field-input" />
          </div>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, nextTick } from 'vue'
import { marked } from 'marked'

const props = defineProps({
  config: { type: Object, required: true },
  editing: { type: Boolean, default: false },
})

const emit = defineEmits(['remove', 'update'])

// ===== 通用状态 =====
const localData = ref({})
const currentItem = ref({})
const selectedItem = ref(null)
const searchQuery = ref('')
const storageKey = computed(() => `myagent_module_${props.config.module_id}`)

// ===== 数据持久化 =====
function loadData() {
  try {
    const raw = localStorage.getItem(storageKey.value)
    if (raw) {
      const data = JSON.parse(raw)
      localData.value = data
      // 初始化当前项
      if (data.items && data.items.length > 0) {
        currentItem.value = data.items[0]
        selectedItem.value = data.items[0].id
      } else {
        currentItem.value = {}
      }
    } else {
      localData.value = { items: [], messages: [], images: [], events: [], stats: [], colors: [] }
      currentItem.value = {}
    }
  } catch {
    localData.value = { items: [] }
    currentItem.value = {}
  }
}

function saveData() {
  // 确保 currentItem 的变更同步到 items 列表
  if (localData.value.items && selectedItem.value) {
    const idx = localData.value.items.findIndex(i => i.id === selectedItem.value)
    if (idx >= 0) {
      localData.value.items[idx] = { ...currentItem.value }
    }
  }
  localStorage.setItem(storageKey.value, JSON.stringify(localData.value))
}

// 监听 currentItem 变化自动保存
watch(currentItem, () => saveData(), { deep: true })
watch(localData, () => saveData(), { deep: true })

// ===== 通用字段组件映射 =====
function getFieldComponent(type) {
  const map = {
    string: 'input',
    text: 'textarea',
    markdown: 'textarea',
    number: 'input',
    datetime: 'input',
    enum: 'select',
    boolean: 'input',
    image: 'input',
    url: 'input',
    tags: 'input',
    code: 'textarea',
    json: 'textarea',
  }
  return map[type] || 'input'
}

// ===== 图标映射 =====
function getIcon(name) {
  const icons = {
    note: '📝', edit: '✏️', search: '🔍', bookmark: '🔖',
    kanban: '📋', timer: '⏱️', calendar: '📅',
    dashboard: '📊', brain: '🧠', timeline: '📅',
    globe: '🌐', image: '🖼️', language: '🌐', compare: '⇄',
    columns: '⇆', collage: '🎨', history: '📜',
    terminal: '💻', rocket: '🚀', folder: '📁',
    code: '💻', snippet: '📝', git: '🔀', api: '🔌',
    canvas: '🎨', palette: '🎨', preview: '👁️',
    chat: '💬', tree: '🌳', form: '📋',
  }
  return icons[name] || '📦'
}

// ===== 列表布局 (sidebar_list) =====
const filteredItems = computed(() => {
  if (!localData.value.items) return []
  if (!searchQuery.value) return localData.value.items
  const q = searchQuery.value.toLowerCase()
  return localData.value.items.filter(item =>
    JSON.stringify(item).toLowerCase().includes(q)
  )
})

// ===== 双栏布局字段解析 =====
// 根据 currentItem 实际包含的 key 自动选择字段
const dualLeftField = computed(() => {
  const item = currentItem.value
  if (item.left_content !== undefined) return 'left_content'
  if (item.left_text !== undefined) return 'left_text'
  if (item.old_version !== undefined) return 'old_version'
  return 'left_content'
})
const dualRightField = computed(() => {
  const item = currentItem.value
  if (item.right_content !== undefined) return 'right_content'
  if (item.right_text !== undefined) return 'right_text'
  if (item.new_version !== undefined) return 'new_version'
  return 'right_content'
})
const dualLeftLabel = computed(() => {
  const item = currentItem.value
  return item.left_label || item.left_title || '左栏'
})
const dualRightLabel = computed(() => {
  const item = currentItem.value
  return item.right_label || item.right_title || '右栏'
})

function selectItem(id) {
  const item = localData.value.items.find(i => i.id === id)
  if (item) {
    currentItem.value = { ...item }
    selectedItem.value = id
  }
}

function addNewItem() {
  const newItem = { id: Date.now() }
  props.config.fields.forEach(f => {
    newItem[f.name] = f.default || ''
  })
  if (!localData.value.items) localData.value.items = []
  localData.value.items.unshift(newItem)
  selectItem(newItem.id)
}

// ===== Markdown 编辑器 =====
const mdPreviewHtml = ref('')
function updateMdPreview() {
  try {
    mdPreviewHtml.value = marked(currentItem.value.content || '')
  } catch {
    mdPreviewHtml.value = currentItem.value.content || ''
  }
}

// ===== 看板任务 =====
const kanbanColumns = computed(() => {
  const statusField = props.config.fields.find(f => f.name === 'status')
  return statusField?.options || ['待办', '进行中', '已完成']
})

function getKanbanItems(status) {
  return (localData.value.items || []).filter(i => (i.status || '待办') === status)
}

function addKanbanItem(status) {
  const newItem = { id: Date.now(), title: '新任务', status, priority: '中' }
  if (!localData.value.items) localData.value.items = []
  localData.value.items.unshift(newItem)
}

// ===== 番茄钟 =====
const pomoRunning = ref(false)
const pomoOnBreak = ref(false)
const pomoRemaining = ref(25 * 60)
const pomoCompletedCycles = ref(0)
let pomoTimer = null

const pomoStatusText = computed(() => {
  if (!pomoRunning.value && pomoRemaining.value === 25 * 60) return '准备开始'
  if (pomoOnBreak.value) return '休息中'
  return pomoRunning.value ? '专注中' : '已暂停'
})

function formatTime(seconds) {
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function togglePomodoro() {
  if (pomoRunning.value) {
    clearInterval(pomoTimer)
    pomoRunning.value = false
  } else {
    pomoRunning.value = true
    pomoTimer = setInterval(() => {
      pomoRemaining.value--
      if (pomoRemaining.value <= 0) {
        clearInterval(pomoTimer)
        pomoRunning.value = false
        if (pomoOnBreak.value) {
          pomoOnBreak.value = false
          pomoRemaining.value = 25 * 60
        } else {
          pomoOnBreak.value = true
          pomoRemaining.value = 5 * 60
          pomoCompletedCycles.value++
        }
      }
    }, 1000)
  }
}

function resetPomodoro() {
  clearInterval(pomoTimer)
  pomoRunning.value = false
  pomoOnBreak.value = false
  pomoRemaining.value = 25 * 60
}

// ===== 日历 =====
const calendarYear = ref(new Date().getFullYear())
const calendarMonth = ref(new Date().getMonth())

const calendarDays = computed(() => {
  const days = []
  const firstDay = new Date(calendarYear.value, calendarMonth.value, 1)
  const lastDay = new Date(calendarYear.value, calendarMonth.value + 1, 0)
  const startWeekday = firstDay.getDay()
  const today = new Date()

  for (let i = 0; i < startWeekday; i++) {
    days.push({ key: 'e' + i, num: '', events: [] })
  }
  for (let d = 1; d <= lastDay.getDate(); d++) {
    const dateStr = `${calendarYear.value}-${String(calendarMonth.value + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    const events = (localData.value.items || []).filter(i =>
      i.start_time && i.start_time.startsWith(dateStr)
    )
    days.push({
      key: 'd' + d,
      num: d,
      isToday: d === today.getDate() && calendarMonth.value === today.getMonth() && calendarYear.value === today.getFullYear(),
      events,
    })
  }
  return days
})

function prevMonth() {
  if (calendarMonth.value === 0) {
    calendarMonth.value = 11
    calendarYear.value--
  } else {
    calendarMonth.value--
  }
}

function nextMonth() {
  if (calendarMonth.value === 11) {
    calendarMonth.value = 0
    calendarYear.value++
  } else {
    calendarMonth.value++
  }
}

// ===== 内嵌浏览器 =====
const browserUrl = ref('')
function navigateBrowser() {
  let url = currentItem.value.url || ''
  if (url && !url.startsWith('http')) {
    url = 'https://' + url
  }
  browserUrl.value = url
}

// ===== 终端 =====
const terminalLines = ref(['MyAgent Terminal v0.1', '输入命令开始操作...'])
const terminalInput = ref('')
const terminalEl = ref(null)

async function execTerminal() {
  const cmd = terminalInput.value.trim()
  if (!cmd) return
  terminalLines.value.push(`$ ${cmd}`)
  terminalInput.value = ''
  // 占位响应
  terminalLines.value.push(`[模拟] 命令已执行: ${cmd}`)
  await nextTick()
  if (terminalEl.value) {
    terminalEl.value.scrollTop = terminalEl.value.scrollHeight
  }
}

// ===== 迷你对话 =====
const chatInput = ref('')
const chatStreaming = ref(false)
const chatScrollEl = ref(null)

async function sendMiniChat() {
  if (!chatInput.value || chatStreaming.value) return
  const text = chatInput.value
  chatInput.value = ''
  if (!localData.value.messages) localData.value.messages = []
  localData.value.messages.push({ role: 'user', content: text })
  await nextTick()
  if (chatScrollEl.value) chatScrollEl.value.scrollTop = chatScrollEl.value.scrollHeight

  // 通过 API 发送 (占位)
  chatStreaming.value = true
  try {
    const res = await fetch('/api/agents/general_assistant/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    })
    const data = await res.json()
    localData.value.messages.push({ role: 'assistant', content: data.reply || '(无响应)' })
  } catch {
    localData.value.messages.push({ role: 'assistant', content: '(连接失败，请检查后端)' })
  }
  chatStreaming.value = false
  await nextTick()
  if (chatScrollEl.value) chatScrollEl.value.scrollTop = chatScrollEl.value.scrollHeight
}

// ===== API 测试器 =====
async function sendApiRequest() {
  currentItem.value.status_code = '请求中...'
  currentItem.value.response = ''
  try {
    const opts = { method: currentItem.value.method || 'GET' }
    if (currentItem.value.body && currentItem.value.method !== 'GET') {
      opts.headers = { 'Content-Type': 'application/json' }
      opts.body = currentItem.value.body
    }
    const res = await fetch(currentItem.value.url, opts)
    currentItem.value.status_code = res.status
    const text = await res.text()
    try {
      currentItem.value.response = JSON.stringify(JSON.parse(text), null, 2)
    } catch {
      currentItem.value.response = text
    }
  } catch (e) {
    currentItem.value.status_code = 'Error'
    currentItem.value.response = String(e)
  }
}

// ===== 画板 =====
const canvasEl = ref(null)
const canvasTool = ref('画笔')
const canvasColor = ref('#6c5ce7')
let drawing = false

function startDraw(e) {
  drawing = true
  const canvas = canvasEl.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const rect = canvas.getBoundingClientRect()
  ctx.beginPath()
  ctx.moveTo(e.clientX - rect.left, e.clientY - rect.top)
}

function draw(e) {
  if (!drawing) return
  const canvas = canvasEl.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  const rect = canvas.getBoundingClientRect()
  ctx.strokeStyle = canvasColor.value
  ctx.lineWidth = 2
  ctx.lineTo(e.clientX - rect.left, e.clientY - rect.top)
  ctx.stroke()
}

function stopDraw() {
  drawing = false
}

function clearCanvas() {
  const canvas = canvasEl.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  ctx.clearRect(0, 0, canvas.width, canvas.height)
}

// ===== 全局搜索 =====
const searchResults = ref([])
async function doGlobalSearch() {
  if (!searchQuery.value) return
  searchResults.value = [{ id: 0, title: '搜索中...', snippet: '' }]
  try {
    // 占位 — 实际应调用后端搜索 API
    searchResults.value = [
      { id: 1, title: `搜索结果: ${searchQuery.value}`, snippet: '这是模拟搜索结果...' },
    ]
  } catch {
    searchResults.value = []
  }
}

// ===== 树形大纲 =====
const treeData = ref([
  { id: 1, title: '一级节点', level: 0, expanded: true },
  { id: 2, title: '二级节点', level: 1, expanded: false },
  { id: 3, title: '另一分支', level: 0, expanded: false },
])

// ===== 图片查看器 =====
const previewImage = ref(null)
function addImage() {
  const url = prompt('输入图片 URL:')
  if (url) {
    if (!localData.value.images) localData.value.images = []
    localData.value.images.push({ id: Date.now(), url, title: '图片' })
  }
}

// ===== 默认数据 =====
const defaultStats = [
  { label: '总任务', value: 0 },
  { label: '已完成', value: 0 },
  { label: '对话数', value: 0 },
  { label: '模块数', value: 0 },
]

const defaultColors = [
  '#6c5ce7', '#00cec9', '#fd79a8', '#fdcb6e', '#00b894',
  '#e8463a', '#0984e3', '#a29bfe', '#fab1a0', '#55efc4',
]

// ===== 语言选项 =====
function getLangOptions() {
  return ['python', 'javascript', 'typescript', 'html', 'css', 'json', 'yaml', 'markdown']
}

function getSourceLangOptions() {
  return ['自动检测', '中文', '英文', '日文']
}

function getTargetLangOptions() {
  return ['中文', '英文', '日文', '法文']
}

// ===== 初始化 =====
onMounted(() => {
  loadData()
  if (props.config.template === 'markdown_editor' && currentItem.value.content) {
    updateMdPreview()
  }
  // 初始化画布尺寸
  if (props.config.template === 'canvas_whiteboard') {
    nextTick(() => {
      if (canvasEl.value) {
        canvasEl.value.width = canvasEl.value.offsetWidth
        canvasEl.value.height = canvasEl.value.offsetHeight
      }
    })
  }
})
</script>

<style scoped>
.module-renderer {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-1);
  border-radius: var(--radius);
  overflow: hidden;
}

.module-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: var(--bg-2);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.module-icon { font-size: 14px; }
.module-title { font-size: 13px; font-weight: 600; color: var(--text-0); flex: 1; }

.module-actions { display: flex; gap: 4px; }
.btn-action {
  width: 20px; height: 20px;
  border: none; border-radius: 4px;
  background: transparent; color: var(--text-2);
  cursor: pointer; font-size: 16px; line-height: 1;
}
.btn-action:hover { background: rgba(232,70,58,0.2); color: #e8463a; }

.module-body { flex: 1; overflow: auto; padding: 12px; }

/* 通用字段 */
.field-row { margin-bottom: 10px; }
.field-label {
  display: block; font-size: 12px; color: var(--text-2);
  margin-bottom: 4px;
}
.required { color: #e8463a; }
.field-input {
  width: 100%; padding: 6px 8px;
  background: var(--bg-0); border: 1px solid var(--border);
  border-radius: 6px; color: var(--text-0); font-size: 13px;
  outline: none;
}
.field-input:focus { border-color: var(--accent); }
select.field-input { cursor: pointer; }
textarea.field-input { resize: vertical; min-height: 60px; font-family: var(--font-mono, monospace); }

/* sidebar_list 布局 */
.sidebar-list-layout { display: flex; height: 100%; gap: 8px; }
.sll-sidebar { width: 200px; display: flex; flex-direction: column; gap: 8px; }
.sll-search {
  padding: 6px 8px; background: var(--bg-0);
  border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-0); font-size: 12px; outline: none;
}
.sll-list { flex: 1; overflow-y: auto; }
.sll-item {
  padding: 6px 8px; border-radius: 6px; cursor: pointer;
  margin-bottom: 2px; transition: background 0.15s;
}
.sll-item:hover { background: rgba(255,255,255,0.04); }
.sll-item.active { background: rgba(108,92,231,0.12); }
.sll-item-title { font-size: 13px; color: var(--text-0); }
.sll-item-meta { font-size: 11px; color: var(--text-2); }
.sll-add {
  padding: 6px; border: 1px dashed var(--border);
  border-radius: 6px; background: transparent;
  color: var(--text-2); cursor: pointer; font-size: 12px;
}
.sll-add:hover { border-color: var(--accent); color: var(--accent); }
.sll-detail { flex: 1; overflow-y: auto; }
.empty-state { color: var(--text-2); text-align: center; padding: 40px 0; font-size: 13px; }

/* Markdown 编辑器 */
.md-editor-layout { display: flex; height: 100%; gap: 8px; }
.md-editor-pane { flex: 1; display: flex; flex-direction: column; gap: 8px; }
.md-title-input {
  padding: 6px 8px; background: var(--bg-0);
  border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-0); font-size: 14px; font-weight: 600;
}
.md-textarea {
  flex: 1; padding: 8px; background: var(--bg-0);
  border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-0); font-size: 13px; font-family: var(--font-mono, monospace);
  resize: none; outline: none;
}
.md-preview-pane {
  flex: 1; padding: 8px; overflow-y: auto;
  background: var(--bg-0); border: 1px solid var(--border);
  border-radius: 6px; font-size: 13px; line-height: 1.6;
}

/* 代码编辑器 */
.code-editor-layout { display: flex; flex-direction: column; height: 100%; gap: 8px; }
.code-toolbar { display: flex; gap: 8px; }
.code-filename, .code-lang {
  padding: 4px 8px; background: var(--bg-0);
  border: 1px solid var(--border); border-radius: 4px;
  color: var(--text-0); font-size: 12px;
}
.code-filename { flex: 1; }
.code-textarea {
  flex: 1; padding: 8px; background: var(--bg-0);
  border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-0); font-size: 13px; font-family: var(--font-mono, monospace);
  resize: none; outline: none; line-height: 1.5;
}

/* 双栏布局 */
.dual-pane-layout { display: flex; height: 100%; gap: 8px; }
.dual-pane { flex: 1; display: flex; flex-direction: column; }
.dual-pane-header {
  padding: 4px 8px; font-size: 12px; color: var(--text-2);
  border-bottom: 1px solid var(--border); margin-bottom: 4px;
}
.dual-textarea {
  flex: 1; padding: 8px; background: var(--bg-0);
  border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-0); font-size: 13px; font-family: var(--font-mono, monospace);
  resize: none; outline: none;
}

/* 看板 */
.kanban-board { display: flex; height: 100%; gap: 8px; overflow-x: auto; }
.kanban-col {
  flex: 1; min-width: 150px; display: flex; flex-direction: column;
  background: var(--bg-0); border-radius: 8px; padding: 8px;
}
.kanban-col-header { font-size: 12px; color: var(--text-2); margin-bottom: 8px; font-weight: 600; }
.kanban-items { flex: 1; overflow-y: auto; }
.kanban-item {
  background: var(--bg-1); border-radius: 6px; padding: 8px;
  margin-bottom: 6px; border-left: 3px solid var(--text-2);
}
.kanban-item.priority-高 { border-left-color: #e8463a; }
.kanban-item.priority-中 { border-left-color: #fdcb6e; }
.kanban-item.priority-低 { border-left-color: #00b894; }
.kanban-item-title { font-size: 13px; color: var(--text-0); }
.kanban-item-meta { font-size: 11px; color: var(--text-2); margin-top: 4px; }
.kanban-add {
  margin-top: 4px; padding: 4px; border: 1px dashed var(--border);
  border-radius: 4px; background: transparent;
  color: var(--text-2); cursor: pointer; font-size: 11px;
}

/* 番茄钟 */
.pomodoro-layout { display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; gap: 12px; }
.pomodoro-timer {
  font-size: 48px; font-weight: 700; font-family: var(--font-mono, monospace);
  color: var(--accent); padding: 20px;
  border: 3px solid var(--accent); border-radius: 50%;
  width: 120px; height: 120px; display: flex; align-items: center; justify-content: center;
}
.pomodoro-timer.working { border-color: #e8463a; color: #e8463a; }
.pomodoro-timer.break { border-color: #00b894; color: #00b894; }
.pomodoro-status { font-size: 14px; color: var(--text-1); }
.pomodoro-controls { display: flex; gap: 8px; }
.pomo-btn {
  padding: 6px 16px; border: 1px solid var(--accent);
  border-radius: 6px; background: transparent;
  color: var(--accent); cursor: pointer; font-size: 13px;
}
.pomo-btn:hover { background: rgba(108,92,231,0.1); }
.pomodoro-cycles { font-size: 12px; color: var(--text-2); }

/* 迷你对话 */
.mini-chat { display: flex; flex-direction: column; height: 100%; }
.mini-chat-messages { flex: 1; overflow-y: auto; padding: 4px 0; }
.mini-msg { margin-bottom: 6px; max-width: 85%; padding: 6px 10px; border-radius: 8px; font-size: 13px; }
.mini-msg.user { margin-left: auto; background: var(--accent); color: white; }
.mini-msg.assistant { background: var(--bg-2); border: 1px solid var(--border); }
.mini-chat-input { display: flex; gap: 4px; }
.mini-chat-input input {
  flex: 1; padding: 6px 8px; background: var(--bg-0);
  border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-0); font-size: 12px; outline: none;
}
.mini-chat-input button {
  padding: 6px 12px; background: var(--accent);
  border: none; border-radius: 6px; color: white;
  cursor: pointer; font-size: 12px;
}

/* 内嵌浏览器 */
.browser-layout { display: flex; flex-direction: column; height: 100%; }
.browser-toolbar { display: flex; gap: 4px; margin-bottom: 8px; }
.browser-url {
  flex: 1; padding: 6px 8px; background: var(--bg-0);
  border: 1px solid var(--border); border-radius: 6px;
  color: var(--text-0); font-size: 12px;
}
.browser-toolbar button {
  padding: 6px 12px; background: var(--accent);
  border: none; border-radius: 6px; color: white;
  cursor: pointer; font-size: 12px;
}
.browser-frame { flex: 1; border: 1px solid var(--border); border-radius: 6px; background: white; }
.browser-empty { flex: 1; display: flex; align-items: center; justify-content: center; color: var(--text-2); }

/* 终端 */
.terminal-layout { display: flex; flex-direction: column; height: 100%; background: #0a0a0f; border-radius: 6px; }
.terminal-output { flex: 1; overflow-y: auto; padding: 8px; }
.terminal-line { font-family: var(--font-mono, monospace); font-size: 12px; color: #00ff88; white-space: pre-wrap; }
.terminal-input { display: flex; align-items: center; padding: 8px; border-top: 1px solid var(--border); }
.terminal-prompt { color: #00ff88; font-family: var(--font-mono, monospace); margin-right: 6px; }
.terminal-cmd {
  flex: 1; background: transparent; border: none;
  color: #00ff88; font-family: var(--font-mono, monospace);
  font-size: 12px; outline: none;
}

/* 仪表盘 */
.dashboard-layout { display: flex; flex-direction: column; height: 100%; gap: 12px; }
.dashboard-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 8px; }
.stat-card { background: var(--bg-0); border-radius: 8px; padding: 12px; text-align: center; }
.stat-value { font-size: 24px; font-weight: 700; color: var(--accent); }
.stat-label { font-size: 11px; color: var(--text-2); }
.dashboard-chart { flex: 1; background: var(--bg-0); border-radius: 8px; }
.chart-placeholder { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-2); font-size: 13px; }

/* 时间线 */
.timeline-layout { overflow-y: auto; }
.timeline-item { display: flex; gap: 12px; margin-bottom: 16px; position: relative; }
.timeline-time { font-size: 11px; color: var(--text-2); white-space: nowrap; width: 80px; text-align: right; }
.timeline-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--accent); margin-top: 4px; flex-shrink: 0; }
.timeline-content { flex: 1; }
.timeline-event { font-size: 13px; color: var(--text-0); }
.timeline-details { font-size: 12px; color: var(--text-2); margin-top: 2px; }

/* 日历 */
.calendar-layout { display: flex; flex-direction: column; height: 100%; }
.calendar-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.calendar-header button { background: none; border: none; color: var(--accent); cursor: pointer; font-size: 16px; }
.calendar-header span { font-size: 14px; font-weight: 600; }
.calendar-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 2px; flex: 1; }
.calendar-day {
  background: var(--bg-0); border-radius: 4px; padding: 4px;
  min-height: 40px; font-size: 11px;
}
.calendar-day.today { background: rgba(108,92,231,0.15); }
.calendar-day.hasEvent { border: 1px solid var(--accent); }
.day-num { color: var(--text-2); }
.day-event { font-size: 10px; color: var(--accent); margin-top: 2px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* 图片查看器 */
.image-viewer-layout { height: 100%; display: flex; flex-direction: column; }
.iv-grid { flex: 1; display: grid; grid-template-columns: repeat(auto-fill, minmax(80px, 1fr)); gap: 4px; overflow-y: auto; }
.iv-thumb { cursor: pointer; border-radius: 4px; overflow: hidden; aspect-ratio: 1; }
.iv-thumb img { width: 100%; height: 100%; object-fit: cover; }
.iv-add { margin-top: 8px; padding: 6px; border: 1px dashed var(--border); border-radius: 6px; background: transparent; color: var(--text-2); cursor: pointer; }

/* 翻译 */
.translate-layout { display: flex; flex-direction: column; height: 100%; gap: 8px; }
.translate-controls { display: flex; align-items: center; gap: 8px; }
.translate-select { padding: 4px 8px; background: var(--bg-0); border: 1px solid var(--border); border-radius: 4px; color: var(--text-0); font-size: 12px; }
.translate-arrow { color: var(--text-2); }
.translate-source { flex: 1; padding: 8px; background: var(--bg-0); border: 1px solid var(--border); border-radius: 6px; color: var(--text-0); font-size: 13px; resize: none; outline: none; min-height: 80px; }
.translate-result { flex: 1; padding: 8px; background: var(--bg-0); border: 1px solid var(--border); border-radius: 6px; color: var(--text-1); font-size: 13px; overflow-y: auto; }

/* 画板 */
.canvas-layout { display: flex; flex-direction: column; height: 100%; }
.canvas-toolbar { display: flex; gap: 4px; margin-bottom: 8px; flex-wrap: wrap; align-items: center; }
.canvas-toolbar button { padding: 4px 8px; border: 1px solid var(--border); border-radius: 4px; background: transparent; color: var(--text-2); cursor: pointer; font-size: 11px; }
.canvas-toolbar button.active { border-color: var(--accent); color: var(--accent); }
.canvas-color { width: 28px; height: 28px; border: none; border-radius: 4px; cursor: pointer; }
.canvas-area { flex: 1; border: 1px solid var(--border); border-radius: 6px; background: var(--bg-0); cursor: crosshair; }

/* 调色板 */
.palette-layout { display: flex; flex-direction: column; height: 100%; gap: 12px; align-items: center; }
.palette-picker { width: 80px; height: 80px; border: none; border-radius: 12px; cursor: pointer; }
.palette-info { text-align: center; }
.palette-hex { font-family: var(--font-mono, monospace); font-size: 14px; color: var(--text-0); }
.palette-name { padding: 4px 8px; background: var(--bg-0); border: 1px solid var(--border); border-radius: 4px; color: var(--text-0); font-size: 12px; margin-top: 4px; }
.palette-grid { display: grid; grid-template-columns: repeat(5, 1fr); gap: 4px; width: 100%; }
.palette-swatch { height: 30px; border-radius: 4px; cursor: pointer; }

/* 树形大纲 */
.tree-layout { overflow-y: auto; }
.tree-node { display: flex; align-items: center; gap: 4px; padding: 4px 0; }
.tree-toggle { cursor: pointer; font-size: 10px; color: var(--text-2); width: 14px; }
.tree-title { font-size: 13px; color: var(--text-0); }

/* API 测试器 */
.api-layout { display: flex; flex-direction: column; height: 100%; gap: 8px; }
.api-request { display: flex; flex-direction: column; gap: 8px; }
.api-row { display: flex; gap: 4px; }
.api-method { padding: 4px 8px; background: var(--bg-0); border: 1px solid var(--border); border-radius: 4px; color: var(--text-0); font-size: 12px; }
.api-url { flex: 1; padding: 4px 8px; background: var(--bg-0); border: 1px solid var(--border); border-radius: 4px; color: var(--text-0); font-size: 12px; }
.api-send { padding: 4px 12px; background: var(--accent); border: none; border-radius: 4px; color: white; cursor: pointer; font-size: 12px; }
.api-body { padding: 8px; background: var(--bg-0); border: 1px solid var(--border); border-radius: 6px; color: var(--text-0); font-size: 12px; font-family: var(--font-mono, monospace); resize: vertical; min-height: 60px; }
.api-response { flex: 1; overflow-y: auto; }
.api-status { font-size: 12px; color: var(--text-2); margin-bottom: 4px; }
.api-result { font-family: var(--font-mono, monospace); font-size: 12px; color: var(--text-1); white-space: pre-wrap; }

/* 全局搜索 */
.search-layout { display: flex; flex-direction: column; height: 100%; gap: 8px; }
.search-input { flex: 1; padding: 8px 12px; background: var(--bg-0); border: 1px solid var(--border); border-radius: 6px; color: var(--text-0); font-size: 13px; outline: none; }
.search-input:focus { border-color: var(--accent); }
.search-scope { padding: 4px 8px; background: var(--bg-0); border: 1px solid var(--border); border-radius: 4px; color: var(--text-0); font-size: 12px; }
.search-results { flex: 1; overflow-y: auto; }
.search-result-item { padding: 8px; border-bottom: 1px solid var(--border); }
.result-title { font-size: 13px; color: var(--text-0); }
.result-snippet { font-size: 12px; color: var(--text-2); margin-top: 2px; }

/* 通用表单 */
.generic-form { max-width: 400px; }
</style>
