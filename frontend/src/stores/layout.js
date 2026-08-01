/**
 * 布局状态管理 — Pinia Store
 *
 * 管理工作台的面板布局：
 * - modules: 当前工作台上的模块列表 (含位置和尺寸)
 * - availableModules: 模块库中所有可用模块 (从后端加载)
 * - templates: 所有模板定义 (从后端加载)
 * - editing: 是否处于编辑模式
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useLayoutStore = defineStore('layout', () => {
  // ===== 状态 =====
  const modules = ref([])           // 当前布局中的模块 [{module_id, x, y, w, h, ...config}]
  const availableModules = ref([])  // 所有已生成的模块 (模块库)
  const templates = ref([])         // 所有模板定义
  const categories = ref([])        // 模板分类
  const editing = ref(false)        // 编辑模式
  const loading = ref(false)        // 加载状态

  // ===== 计算属性 =====
  const moduleCount = computed(() => modules.value.length)
  const hasModules = computed(() => modules.value.length > 0)

  // 按分类分组的模板
  const templatesByCategory = computed(() => {
    const grouped = {}
    for (const tpl of templates.value) {
      const cat = tpl.category || '其他'
      if (!grouped[cat]) grouped[cat] = []
      grouped[cat].push(tpl)
    }
    return grouped
  })

  // ===== Actions =====

  /** 从后端加载当前布局 */
  async function loadLayout() {
    loading.value = true
    try {
      const res = await fetch('/api/layout')
      const data = await res.json()
      modules.value = data.modules || []
    } catch (e) {
      console.error('加载布局失败:', e)
      // 回退到 localStorage
      const saved = localStorage.getItem('myagent_layout')
      if (saved) {
        try {
          modules.value = JSON.parse(saved).modules || []
        } catch {
          modules.value = []
        }
      }
    } finally {
      loading.value = false
    }
  }

  /** 保存布局到后端 + localStorage */
  async function saveLayout(layoutModules = null) {
    const data = layoutModules || modules.value
    const payload = {
      modules: data.map(m => ({
        module_id: m.module_id,
        x: m.x ?? 0,
        y: m.y ?? 0,
        w: m.w ?? m.default_size?.w ?? 6,
        h: m.h ?? m.default_size?.h ?? 8,
      })),
      name: 'default',
    }

    // localStorage 即时保存
    localStorage.setItem('myagent_layout', JSON.stringify({ modules: data }))

    // 后端保存
    try {
      await fetch('/api/layout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
    } catch (e) {
      console.warn('后端保存布局失败 (使用本地存储):', e)
    }
  }

  /** 加载所有已生成的模块 */
  async function loadAvailableModules() {
    try {
      const res = await fetch('/api/modules')
      const data = await res.json()
      availableModules.value = data.modules || []
    } catch (e) {
      console.error('加载模块库失败:', e)
      availableModules.value = []
    }
  }

  /** 加载所有模板 */
  async function loadTemplates() {
    try {
      const res = await fetch('/api/modules/templates')
      const data = await res.json()
      templates.value = data.templates || []
      categories.value = data.categories || []
    } catch (e) {
      console.error('加载模板失败:', e)
      templates.value = []
      categories.value = []
    }
  }

  /** 添加模块到工作台 */
  function addModule(moduleConfig) {
    // 避免重复添加
    if (modules.value.find(m => m.module_id === moduleConfig.module_id)) {
      return false
    }
    const newModule = {
      ...moduleConfig,
      x: moduleConfig.x ?? 0,
      y: moduleConfig.y ?? 0,
      w: moduleConfig.w ?? moduleConfig.default_size?.w ?? 6,
      h: moduleConfig.h ?? moduleConfig.default_size?.h ?? 8,
    }
    modules.value.push(newModule)
    return true
  }

  /** 从工作台移除模块 */
  function removeModule(moduleId) {
    const idx = modules.value.findIndex(m => m.module_id === moduleId)
    if (idx >= 0) {
      modules.value.splice(idx, 1)
      return true
    }
    return false
  }

  /** 更新模块位置/尺寸 (拖拽或调整大小后调用) */
  function updateModulePosition(moduleId, x, y, w, h) {
    const mod = modules.value.find(m => m.module_id === moduleId)
    if (mod) {
      mod.x = x
      mod.y = y
      mod.w = w
      mod.h = h
    }
  }

  /** 交换两个模块的位置 */
  function swapModules(moduleIdA, moduleIdB) {
    const a = modules.value.find(m => m.module_id === moduleIdA)
    const b = modules.value.find(m => m.module_id === moduleIdB)
    if (a && b) {
      const tmpX = a.x, tmpY = a.y, tmpW = a.w, tmpH = a.h
      a.x = b.x; a.y = b.y; a.w = b.w; a.h = b.h
      b.x = tmpX; b.y = tmpY; b.w = tmpW; b.h = tmpH
      return true
    }
    return false
  }

  /** 切换编辑模式 */
  function toggleEditing() {
    editing.value = !editing.value
  }

  /** 初始化 — 加载所有数据 */
  async function init() {
    await Promise.all([
      loadLayout(),
      loadAvailableModules(),
      loadTemplates(),
    ])
  }

  return {
    // 状态
    modules,
    availableModules,
    templates,
    categories,
    editing,
    loading,
    // 计算属性
    moduleCount,
    hasModules,
    templatesByCategory,
    // Actions
    loadLayout,
    saveLayout,
    loadAvailableModules,
    loadTemplates,
    addModule,
    removeModule,
    updateModulePosition,
    swapModules,
    toggleEditing,
    init,
  }
})
