<template>
  <div class="app-shell">
    <!-- 顶部导航栏 -->
    <header class="app-header">
      <div class="app-brand">
        <svg class="brand-icon" width="22" height="22" viewBox="0 0 24 24" fill="none">
          <rect x="3" y="3" width="8" height="8" rx="2" fill="url(#g1)"/>
          <rect x="13" y="3" width="8" height="8" rx="2" fill="url(#g2)"/>
          <rect x="3" y="13" width="8" height="8" rx="2" fill="url(#g3)"/>
          <rect x="13" y="13" width="8" height="8" rx="2" fill="url(#g4)"/>
          <defs>
            <linearGradient id="g1" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#6366f1"/><stop offset="100%" stop-color="#8b5cf6"/></linearGradient>
            <linearGradient id="g2" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#8b5cf6"/><stop offset="100%" stop-color="#a78bfa"/></linearGradient>
            <linearGradient id="g3" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#a78bfa"/><stop offset="100%" stop-color="#c4b5fd"/></linearGradient>
            <linearGradient id="g4" x1="0" y1="0" x2="1" y2="1"><stop offset="0%" stop-color="#c4b5fd"/><stop offset="100%" stop-color="#ddd6fe"/></linearGradient>
          </defs>
        </svg>
        <span class="brand-text">MyAgent</span>
      </div>
      <nav class="app-nav">
        <router-link to="/" class="nav-item">对话</router-link>
        <router-link to="/workbench" class="nav-item">工作台</router-link>
        <router-link to="/skins" class="nav-item">皮肤</router-link>
      </nav>
      <div class="app-right">
        <!-- 模型切换器 -->
        <div class="model-switcher" @click="toggleModelMenu" ref="modelSwitcherEl">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none"><rect x="2" y="3" width="12" height="10" rx="2" stroke="#6366f1" stroke-width="1.2"/><path d="M5 6l3 3 3-3" stroke="#6366f1" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <span class="model-name">{{ currentModelName }}</span>
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M3 4l2 2 2-2" stroke="var(--text-muted)" stroke-width="1.2" stroke-linecap="round"/></svg>
          <div v-if="showModelMenu" class="model-menu">
            <div
              v-for="m in models"
              :key="m.id"
              class="model-menu-item"
              :class="{ active: m.is_active }"
              @click.stop="switchModel(m.id)"
            >
              <div class="mmi-name">{{ m.name }}</div>
              <div class="mmi-provider">{{ m.provider === 'llama_cpp' ? '本地' : '云端' }}</div>
              <span v-if="m.is_active" class="mmi-check">✓</span>
            </div>
          </div>
        </div>
        <!-- 状态指示 -->
        <div class="status-badge" :class="{ online: llmOnline }">
          <span class="status-dot"></span>
          <span class="status-text">{{ llmOnline ? 'llama.cpp' : '离线' }}</span>
        </div>
      </div>
    </header>

    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

const llmOnline = ref(false)
const currentModelName = ref('Qwen2.5-14B')
const models = ref([])
const showModelMenu = ref(false)
const modelSwitcherEl = ref(null)

async function checkHealth() {
  try {
    const res = await fetch('/api/health')
    const data = await res.json()
    llmOnline.value = data.llm_available
    if (data.current_model?.name) {
      currentModelName.value = data.current_model.name
    }
  } catch {
    llmOnline.value = false
  }
}

async function loadModels() {
  try {
    const res = await fetch('/api/models')
    const data = await res.json()
    models.value = data.models || []
    if (data.current?.name) {
      currentModelName.value = data.current.name
    }
  } catch { /* ignore */ }
}

async function switchModel(profileId) {
  try {
    await fetch('/api/models/switch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile_id: profileId }),
    })
    showModelMenu.value = false
    await loadModels()
  } catch { /* ignore */ }
}

function toggleModelMenu() {
  showModelMenu.value = !showModelMenu.value
}

function handleClickOutside(e) {
  if (modelSwitcherEl.value && !modelSwitcherEl.value.contains(e.target)) {
    showModelMenu.value = false
  }
}

onMounted(() => {
  checkHealth()
  loadModels()
  setInterval(checkHealth, 10000)
  document.addEventListener('click', handleClickOutside)
})

onBeforeUnmount(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<style>
:root {
  --brand: #6366f1;
  --brand-soft: #eef2ff;
  --brand-dark: #4f46e5;
  --surface: #ffffff;
  --surface-muted: #f8fafc;
  --sidebar-bg: #f8fafc;
  --sidebar-active: #eef2ff;
  --border: #e2e8f0;
  --text: #1e293b;
  --text-muted: #94a3b8;
  --text-sidebar: #475569;
  --radius: 8px;
  --radius-card: 12px;
  --radius-full: 999px;
  --font-sans: 'Segoe UI', 'PingFang SC', system-ui, -apple-system, sans-serif;
  --font-mono: 'Cascadia Code', 'Fira Code', 'Consolas', monospace;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  background: #f1f5f9;
  color: var(--text);
  font-family: var(--font-sans);
  font-size: 14px;
  overflow: hidden;
}

.app-shell {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.app-header {
  display: flex;
  align-items: center;
  padding: 0 16px;
  height: 48px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  gap: 12px;
}

.app-brand {
  display: flex;
  align-items: center;
  gap: 8px;
}

.brand-icon {
  flex-shrink: 0;
}

.brand-text {
  font-weight: 600;
  font-size: 15px;
  color: var(--text);
  letter-spacing: -0.3px;
}

.app-nav {
  display: flex;
  gap: 2px;
  background: var(--surface-muted);
  border-radius: var(--radius);
  padding: 3px;
}

.nav-item {
  padding: 5px 14px;
  border-radius: 6px;
  text-decoration: none;
  color: var(--text-muted);
  font-size: 13px;
  transition: all 0.15s;
}

.nav-item:hover {
  color: var(--text);
}

.nav-item.router-link-active {
  color: #fff;
  background: var(--brand);
  font-weight: 500;
}

.app-right {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.model-switcher {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--surface);
  cursor: pointer;
  font-size: 12px;
  color: var(--text);
  position: relative;
  user-select: none;
}

.model-switcher:hover {
  border-color: var(--brand);
}

.model-name {
  font-size: 12px;
  color: var(--text);
}

.model-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  box-shadow: 0 8px 24px rgba(0,0,0,0.1);
  min-width: 200px;
  z-index: 100;
  overflow: hidden;
}

.model-menu-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  cursor: pointer;
  transition: background 0.15s;
}

.model-menu-item:hover {
  background: var(--surface-muted);
}

.model-menu-item.active {
  background: var(--brand-soft);
}

.mmi-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text);
}

.mmi-provider {
  font-size: 11px;
  color: var(--text-muted);
  padding: 1px 6px;
  border-radius: var(--radius-full);
  background: var(--surface-muted);
}

.mmi-check {
  margin-left: auto;
  font-size: 12px;
  color: var(--brand);
  font-weight: 600;
}

.status-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  background: #fef2f2;
  border: 1px solid #fecaca;
  font-size: 11px;
  color: #dc2626;
}

.status-badge.online {
  background: #f0fdf4;
  border-color: #bbf7d0;
  color: #166534;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #dc2626;
}

.status-badge.online .status-dot {
  background: #22c55e;
  box-shadow: 0 0 4px #22c55e;
}

.app-main {
  flex: 1;
  overflow: hidden;
}
</style>