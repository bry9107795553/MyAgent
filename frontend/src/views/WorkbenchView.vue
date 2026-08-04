<template>
  <div class="workbench-view">
    <!-- 顶部工具栏 -->
    <div class="workbench-header">
      <div class="header-left">
        <h2>工作台</h2>
        <span class="module-count" v-if="mergedModules.length">{{ mergedModules.length }} 个模块</span>
      </div>
      <div class="header-right">
        <button @click="toggleEdit" class="btn-toggle" :class="{active: editing}">
          {{ editing ? '完成编辑' : '编辑布局' }}
        </button>
        <button @click="showAddPanel = true" class="btn-add" v-if="editing">+ 添加模块</button>
        <button @click="saveLayout" class="btn-save" v-if="editing">保存布局</button>
      </div>
    </div>

    <!-- GridStack 布局区域 -->
    <div class="grid-wrapper" ref="gridWrapperEl">
      <!-- 空状态 -->
      <div v-if="!loading && mergedModules.length === 0" class="empty-state">
        <div class="empty-icon">⊞</div>
        <p class="empty-title">工作台是空的</p>
        <p class="empty-hint">点击「编辑布局」→「添加模块」开始构建你的个性化面板</p>
        <button @click="showAddPanel = true" class="btn-start">开始添加</button>
      </div>

      <!-- 加载状态 -->
      <div v-if="loading" class="loading-state">
        <div class="spinner"></div>
        <p>加载中...</p>
      </div>

      <!-- GridStack 容器 -->
      <div class="grid-stack" ref="gridEl"></div>
    </div>

    <!-- 模块添加面板 (弹窗) -->
    <div v-if="showAddPanel" class="modal-overlay" @click.self="showAddPanel = false">
      <div class="modal-panel">
        <div class="modal-header">
          <h3>添加模块</h3>
          <button @click="showAddPanel = false" class="btn-close">×</button>
        </div>

        <!-- 标签页切换 -->
        <div class="tab-bar">
          <button
            v-for="tab in tabs"
            :key="tab.id"
            @click="activeTab = tab.id"
            :class="{active: activeTab === tab.id}"
          >{{ tab.label }}</button>
        </div>

        <div class="modal-body">
          <!-- 已有模块 -->
          <div v-if="activeTab === 'library'" class="tab-content">
            <div v-if="availableModules.length === 0" class="tab-empty">
              模块库为空，试试用「AI 生成」创建新模块
            </div>
            <div v-else class="module-list">
              <div
                v-for="mod in availableModules"
                :key="mod.module_id"
                class="module-card"
                :class="{added: isOnWorkbench(mod.module_id)}"
                @click="addModuleToGrid(mod)"
              >
                <div class="mc-icon">{{ getIcon(mod.icon) }}</div>
                <div class="mc-info">
                  <div class="mc-name">{{ mod.name }}</div>
                  <div class="mc-desc">{{ mod.description || mod.template }}</div>
                </div>
                <div class="mc-action">
                  <span v-if="isOnWorkbench(mod.module_id)" class="badge-added">已添加</span>
                  <span v-else class="badge-add">+ 添加</span>
                </div>
              </div>
            </div>
          </div>

          <!-- AI 生成 -->
          <div v-if="activeTab === 'generate'" class="tab-content">
            <p class="gen-hint">用自然语言描述你需要的模块，AI 会自动生成：</p>
            <textarea
              v-model="genDescription"
              class="gen-input"
              placeholder="例如：我需要一个写作辅助模块，可以记录和 AI 讨论的大纲、人物设定和剧情走向"
              rows="4"
            ></textarea>
            <button
              @click="generateModule"
              class="btn-generate"
              :disabled="generating || !genDescription.trim()"
            >
              {{ generating ? '生成中...' : 'AI 生成模块' }}
            </button>
            <div v-if="genResult" class="gen-result" :class="{error: genResult.error}">
              <template v-if="genResult.error">
                {{ genResult.error }}
              </template>
              <template v-else-if="genResult.module">
                <div class="gen-success">
                  <span>✓ 模块「{{ genResult.module.name }}」已生成</span>
                  <button @click="addModuleToGrid(genResult.module)" class="btn-add-gen">
                    添加到工作台
                  </button>
                </div>
              </template>
            </div>
          </div>

          <!-- 模板快速添加 -->
          <div v-if="activeTab === 'templates'" class="tab-content">
            <div v-for="(templates, cat) in templatesByCategory" :key="cat" class="tpl-category">
              <div class="tpl-cat-title">{{ cat }}</div>
              <div class="tpl-grid">
                <div
                  v-for="tpl in templates"
                  :key="tpl.id"
                  class="tpl-card"
                  @click="createFromTemplate(tpl)"
                >
                  <span class="tpl-icon">{{ getIcon(tpl.icon) }}</span>
                  <span class="tpl-name">{{ tpl.name }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { createApp, h } from 'vue'
import { GridStack } from 'gridstack'
import 'gridstack/dist/gridstack.min.css'
import ModuleRenderer from '@/components/ModuleRenderer.vue'
import { useLayoutStore } from '@/stores/layout.js'

// ===== Store =====
const store = useLayoutStore()

// ===== 响应式状态 =====
const gridEl = ref(null)
const gridWrapperEl = ref(null)
const grid = ref(null)
const loading = ref(true)
const editing = ref(false)
const showAddPanel = ref(false)
const activeTab = ref('library')
const genDescription = ref('')
const generating = ref(false)
const genResult = ref(null)

// Vue 子应用实例映射 (module_id -> app)
const vueApps = new Map()

// 拖拽起始位置 (用于模块交换)
let dragStartNode = null

// 标签页
const tabs = [
  { id: 'library', label: '模块库' },
  { id: 'generate', label: 'AI 生成' },
  { id: 'templates', label: '模板' },
]

// ===== 计算属性 =====

// 合并布局位置和模块完整配置
const mergedModules = computed(() => {
  if (store.modules.length === 0) return []
  return store.modules.map(layoutMod => {
    // 布局中只存了 module_id + 位置，需要合并完整配置
    const fullConfig = store.availableModules.find(
      m => m.module_id === layoutMod.module_id
    )
    if (fullConfig) {
      return { ...fullConfig, x: layoutMod.x, y: layoutMod.y, w: layoutMod.w, h: layoutMod.h }
    }
    // 如果模块配置不在模块库中 (可能已删除)，用布局中的基本信息
    return layoutMod
  }).filter(m => m) // 过滤掉 null
})

// 按分类分组的模板
const templatesByCategory = computed(() => store.templatesByCategory)

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

// ===== GridStack 初始化 =====

function initGrid() {
  if (!gridEl.value) return

  grid.value = GridStack.init({
    cellHeight: 80,
    column: 12,
    margin: 8,
    float: true,       // 允许自由放置，不被其他模块推动
    animate: true,
    staticGrid: true,  // 初始为静态 (非编辑模式)
    draggable: {
      handle: '.grid-stack-item-content .module-header',
    },
    resizable: {
      handles: 'se, sw, ne, nw',
    },
  }, gridEl.value)

  // 拖拽开始 — 记录起始位置 (用于模块交换)
  grid.value.on('dragstart', (event, el) => {
    const node = el.gridstackNode
    dragStartNode = {
      id: node.id,
      x: node.x,
      y: node.y,
      w: node.w,
      h: node.h,
    }
  })

  // 拖拽结束 — 检测是否需要交换模块位置
  grid.value.on('dragstop', (event, el) => {
    const node = el.gridstackNode
    handleModuleSwap(node)
    updateModulePosition(node)
  })

  // 调整大小结束
  grid.value.on('resizestop', (event, el) => {
    const node = el.gridstackNode
    updateModulePosition(node)
    // 通知模块内容区重新计算尺寸
    const app = vueApps.get(node.id)
    if (app) {
      window.dispatchEvent(new Event('resize'))
    }
  })
}

/**
 * 模块交换逻辑
 * 当拖拽一个模块到另一个模块的位置时，自动交换两者的坐标
 */
function handleModuleSwap(draggedNode) {
  if (!dragStartNode) return

  // 在所有网格节点中查找与拖拽模块当前位置重叠的其他模块
  const allNodes = grid.value.engine.nodes
  const targetNode = allNodes.find(n =>
    n.id !== draggedNode.id &&
    rectsOverlap(
      { x: draggedNode.x, y: draggedNode.y, w: draggedNode.w, h: draggedNode.h },
      { x: n.x, y: n.y, w: n.w, h: n.h }
    )
  )

  if (targetNode) {
    // 交换：将目标模块移动到拖拽模块的原始位置
    grid.value.update(targetNode.el, {
      x: dragStartNode.x,
      y: dragStartNode.y,
      w: dragStartNode.w,
      h: dragStartNode.h,
    })

    // 同步到 store
    store.swapModules(dragStartNode.id, targetNode.id)
  }

  dragStartNode = null
}

/** 检测两个矩形是否重叠 */
function rectsOverlap(a, b) {
  return !(
    a.x + a.w <= b.x ||
    b.x + b.w <= a.x ||
    a.y + a.h <= b.y ||
    b.y + b.h <= a.y
  )
}

/** 更新单个模块的位置到 store */
function updateModulePosition(node) {
  store.updateModulePosition(node.id, node.x, node.y, node.w, node.h)
}

// ===== 渲染模块到 GridStack =====

/**
 * 将一个模块添加到 GridStack 网格中
 * 并在网格项内部挂载 Vue 组件 (ModuleRenderer)
 */
function addWidget(moduleConfig) {
  if (!grid.value) return

  // 先添加网格项 (GridStack DOM)
  grid.value.addWidget({
    id: moduleConfig.module_id,
    x: moduleConfig.x ?? 0,
    y: moduleConfig.y ?? 0,
    w: moduleConfig.w ?? moduleConfig.default_size?.w ?? 6,
    h: moduleConfig.h ?? moduleConfig.default_size?.h ?? 8,
    content: '<div class="widget-mount"></div>',
  })

  // 等待 DOM 更新后挂载 Vue 组件
  nextTick(() => {
    mountModuleComponent(moduleConfig)
  })
}

/**
 * 在 GridStack 网格项内部挂载 ModuleRenderer 组件
 */
function mountModuleComponent(moduleConfig) {
  // 通过 id 找到对应的网格项 DOM
  const nodes = grid.value.engine.nodes
  const node = nodes.find(n => n.id === moduleConfig.module_id)
  if (!node || !node.el) return

  // 找到挂载点
  const mountEl = node.el.querySelector('.widget-mount')
  if (!mountEl) return

  // 如果已存在 Vue 实例，先卸载
  if (vueApps.has(moduleConfig.module_id)) {
    const oldApp = vueApps.get(moduleConfig.module_id)
    oldApp.unmount()
    vueApps.delete(moduleConfig.module_id)
  }

  // 创建并挂载新的 Vue 子应用
  const app = createApp({
    render: () => h(ModuleRenderer, {
      config: moduleConfig,
      editing: editing.value,
      onRemove: () => removeWidget(moduleConfig.module_id),
    })
  })
  app.mount(mountEl)
  vueApps.set(moduleConfig.module_id, app)
}

/**
 * 从 GridStack 中移除模块
 */
function removeWidget(moduleId) {
  // 卸载 Vue 组件
  if (vueApps.has(moduleId)) {
    const app = vueApps.get(moduleId)
    app.unmount()
    vueApps.delete(moduleId)
  }

  // 从 GridStack 移除
  const node = grid.value.engine.nodes.find(n => n.id === moduleId)
  if (node && node.el) {
    grid.value.removeWidget(node.el)
  }

  // 从 store 移除
  store.removeModule(moduleId)
}

/**
 * 重新渲染所有模块 (编辑模式切换时调用)
 */
function rerenderAllModules() {
  // 重新挂载所有 Vue 组件以更新 editing 状态
  for (const [moduleId, oldApp] of vueApps) {
    oldApp.unmount()
  }
  vueApps.clear()

  const moduleConfigs = mergedModules.value
  for (const mod of moduleConfigs) {
    mountModuleComponent(mod)
  }
}

// ===== 编辑模式 =====

function toggleEdit() {
  editing.value = !editing.value
  if (grid.value) {
    grid.value.setStatic(!editing.value)
  }
  // editing 变化由 watch 处理，自动重新渲染模块
}

// 监听 editing 变化 — 重新渲染模块以更新编辑状态
watch(editing, () => {
  rerenderAllModules()
})

// ===== 布局保存 =====

async function saveLayout() {
  await store.saveLayout()
  // 简单提示
  const btn = document.querySelector('.btn-save')
  if (btn) {
    const original = btn.textContent
    btn.textContent = '已保存 ✓'
    setTimeout(() => { btn.textContent = original }, 1500)
  }
}

// ===== 模块添加面板 =====

function isOnWorkbench(moduleId) {
  return store.modules.some(m => m.module_id === moduleId)
}

function addModuleToGrid(moduleConfig) {
  if (isOnWorkbench(moduleConfig.module_id)) return

  // 添加到 store
  store.addModule(moduleConfig)

  // 添加到 GridStack
  addWidget(moduleConfig)

  // 关闭面板
  showAddPanel.value = false
}

// ===== AI 生成模块 =====

async function generateModule() {
  if (!genDescription.value.trim()) return
  generating.value = true
  genResult.value = null

  try {
    const res = await fetch('/api/modules/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        description: genDescription.value,
        agent_id: 'default',
      }),
    })

    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      genResult.value = { error: err.detail || `生成失败 (${res.status})` }
    } else {
      const data = await res.json()
      if (data.success && data.module) {
        genResult.value = { module: data.module }
        // 刷新模块库
        await store.loadAvailableModules()
      } else {
        genResult.value = { error: data.error || '生成失败' }
      }
    }
  } catch (e) {
    genResult.value = { error: `连接失败: ${e.message}。请确认后端服务已启动。` }
  } finally {
    generating.value = false
  }
}

// ===== 从模板创建 =====

async function createFromTemplate(tpl) {
  // 从模板创建一个模块实例
  const moduleId = `mod_${Date.now().toString(36)}`
  const newModule = {
    module_id: moduleId,
    template: tpl.id,
    name: tpl.name,
    description: tpl.description || '',
    fields: tpl.default_fields || [],
    layout: tpl.default_layout || 'single_column',
    data_source: 'local_storage',
    default_size: tpl.default_size || { w: 6, h: 8 },
    icon: tpl.icon,
    category: tpl.category,
  }

  addModuleToGrid(newModule)
}

// ===== 生命周期 =====

onMounted(async () => {
  // 初始化 store (加载布局 + 模块库 + 模板)
  await store.init()

  // 初始化 GridStack
  await nextTick()
  initGrid()

  // 渲染已保存的模块
  await nextTick()
  for (const mod of mergedModules.value) {
    addWidget(mod)
  }

  loading.value = false
})

onBeforeUnmount(() => {
  // 清理所有 Vue 子应用
  for (const [, app] of vueApps) {
    app.unmount()
  }
  vueApps.clear()

  // 销毁 GridStack
  if (grid.value) {
    grid.value.destroy()
    grid.value = null
  }
})
</script>

<style scoped>
.workbench-view {
  height: 100%;
  display: flex;
  flex-direction: column;
}

/* ===== 顶部工具栏 ===== */
.workbench-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 24px;
  height: 52px;
  background: var(--bg-1);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.workbench-header h2 {
  font-size: 16px;
  font-weight: 600;
}

.module-count {
  font-size: 12px;
  color: var(--text-2);
  background: var(--bg-0);
  padding: 2px 8px;
  border-radius: 10px;
}

.header-right {
  display: flex;
  gap: 8px;
}

.btn-toggle {
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: transparent;
  color: var(--text-1);
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.btn-toggle:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.btn-toggle.active {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}

.btn-add {
  padding: 6px 14px;
  border: 1px solid var(--accent-2);
  border-radius: 6px;
  background: transparent;
  color: var(--accent-2);
  cursor: pointer;
  font-size: 13px;
}

.btn-add:hover {
  background: rgba(0,206,201,0.1);
}

.btn-save {
  padding: 6px 14px;
  border: none;
  border-radius: 6px;
  background: var(--accent);
  color: white;
  cursor: pointer;
  font-size: 13px;
}

.btn-save:hover {
  opacity: 0.9;
}

/* ===== GridStack 区域 ===== */
.grid-wrapper {
  flex: 1;
  overflow: auto;
  position: relative;
  padding: 12px;
}

.grid-stack {
  min-height: 400px;
}

/* GridStack 样式覆盖 */
.grid-stack :deep(.grid-stack-item) {
  border-radius: var(--radius);
  overflow: hidden;
}

.grid-stack :deep(.grid-stack-item-content) {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  padding: 0;
}

.grid-stack :deep(.grid-stack-item-content:hover) {
  border-color: var(--accent);
}

/* 编辑模式下的视觉提示 */
.grid-stack.editing :deep(.grid-stack-item) {
  box-shadow: 0 0 0 2px rgba(108,92,231,0.3);
}

.grid-stack :deep(.widget-mount) {
  height: 100%;
}

/* GridStack 拖拽手柄 */
.grid-stack :deep(.module-header) {
  cursor: move;
}

/* ===== 空状态 ===== */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 300px;
  color: var(--text-2);
}

.empty-icon {
  font-size: 48px;
  margin-bottom: 16px;
  opacity: 0.5;
}

.empty-title {
  font-size: 16px;
  color: var(--text-1);
  margin-bottom: 8px;
}

.empty-hint {
  font-size: 13px;
  margin-bottom: 20px;
  text-align: center;
}

.btn-start {
  padding: 8px 20px;
  border: 1px solid var(--accent);
  border-radius: 8px;
  background: var(--accent);
  color: white;
  cursor: pointer;
  font-size: 14px;
}

.btn-start:hover {
  opacity: 0.9;
}

/* ===== 加载状态 ===== */
.loading-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 300px;
  color: var(--text-2);
}

.spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--border);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-bottom: 12px;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ===== 模块添加弹窗 ===== */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0,0,0,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.modal-panel {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 16px;
  width: 640px;
  max-width: 90vw;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
}

.modal-header h3 {
  font-size: 16px;
  font-weight: 600;
}

.btn-close {
  width: 28px;
  height: 28px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-2);
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
}

.btn-close:hover {
  background: rgba(255,255,255,0.06);
  color: var(--text-0);
}

/* 标签栏 */
.tab-bar {
  display: flex;
  gap: 4px;
  padding: 8px 20px 0;
}

.tab-bar button {
  padding: 8px 16px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--text-2);
  cursor: pointer;
  font-size: 13px;
  transition: all 0.2s;
}

.tab-bar button:hover {
  color: var(--text-0);
}

.tab-bar button.active {
  color: var(--accent);
  border-bottom-color: var(--accent);
}

/* 弹窗内容区 */
.modal-body {
  flex: 1;
  overflow-y: auto;
  padding: 16px 20px 20px;
}

.tab-content {
  min-height: 200px;
}

.tab-empty {
  text-align: center;
  color: var(--text-2);
  padding: 40px 0;
  font-size: 13px;
}

/* 模块库列表 */
.module-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.module-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: var(--bg-0);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.module-card:hover {
  border-color: var(--accent);
  background: rgba(108,92,231,0.04);
}

.module-card.added {
  opacity: 0.5;
  cursor: not-allowed;
}

.mc-icon {
  font-size: 20px;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-2);
  border-radius: 8px;
}

.mc-info {
  flex: 1;
}

.mc-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-0);
}

.mc-desc {
  font-size: 12px;
  color: var(--text-2);
  margin-top: 2px;
}

.badge-add {
  font-size: 12px;
  color: var(--accent-2);
}

.badge-added {
  font-size: 12px;
  color: var(--text-2);
}

/* AI 生成 */
.gen-hint {
  font-size: 13px;
  color: var(--text-2);
  margin-bottom: 12px;
}

.gen-input {
  width: 100%;
  padding: 12px;
  background: var(--bg-0);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text-0);
  font-size: 14px;
  resize: vertical;
  outline: none;
  font-family: inherit;
}

.gen-input:focus {
  border-color: var(--accent);
}

.btn-generate {
  margin-top: 12px;
  padding: 10px 20px;
  border: none;
  border-radius: 8px;
  background: var(--accent);
  color: white;
  cursor: pointer;
  font-size: 14px;
  width: 100%;
}

.btn-generate:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.gen-result {
  margin-top: 16px;
  padding: 12px;
  border-radius: 8px;
  background: var(--bg-0);
  border: 1px solid var(--border);
  font-size: 13px;
}

.gen-result.error {
  border-color: #e8463a;
  color: #e8463a;
}

.gen-success {
  display: flex;
  justify-content: space-between;
  align-items: center;
  color: #00b894;
}

.btn-add-gen {
  padding: 6px 14px;
  border: 1px solid var(--accent-2);
  border-radius: 6px;
  background: transparent;
  color: var(--accent-2);
  cursor: pointer;
  font-size: 12px;
}

.btn-add-gen:hover {
  background: rgba(0,206,201,0.1);
}

/* 模板列表 */
.tpl-category {
  margin-bottom: 16px;
}

.tpl-cat-title {
  font-size: 12px;
  color: var(--text-2);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 8px;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--border);
}

.tpl-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 8px;
}

.tpl-card {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--bg-0);
  border: 1px solid var(--border);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
}

.tpl-card:hover {
  border-color: var(--accent);
  background: rgba(108,92,231,0.04);
}

.tpl-icon {
  font-size: 16px;
}

.tpl-name {
  font-size: 13px;
  color: var(--text-0);
}
</style>
