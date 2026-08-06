<template>
  <div class="app-shell" :data-theme="theme">
    <header class="topbar">
      <div class="topbar-brand">
        <div class="topbar-logo">
          <svg viewBox="0 0 24 24" fill="none"><path d="M12 2L2 7l10 5 10-5-10-5z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/></svg>
        </div>
        <span class="topbar-name">MyAgent</span>
      </div>
      <nav class="topbar-nav">
        <router-link to="/" class="nav-item">对话</router-link>
        <router-link to="/history" class="nav-item">历史</router-link>
        <router-link to="/workgroups" class="nav-item">工作组</router-link>
        <router-link to="/browse" class="nav-item">阅览</router-link>
        <router-link to="/workbench" class="nav-item">工作台</router-link>
        <router-link to="/skins" class="nav-item">皮肤</router-link>
        <router-link to="/plugins" class="nav-item">扩展</router-link>
      </nav>
      <div class="topbar-right">
        <span class="topbar-model-tag" v-if="llmOnline">🟢</span>
        <!-- 模型切换 -->
        <div class="model-switcher" ref="modelSwitcher">
          <button class="model-btn" @click.stop="showModelMenu = !showModelMenu">
            {{ modelName }}
            <svg viewBox="0 0 10 6" fill="none"><path d="M1 1l4 4 4-4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>
          </button>
          <div class="model-dropdown" v-if="showModelMenu">
            <div class="model-dropdown-label">当前 GPU 模型</div>
            <div class="model-option" v-for="m in models" :key="m.value" :class="{active: m.value === currentModel}" @click="switchModel(m)">
              {{ m.label }}
              <span class="check" v-if="m.value === currentModel">✓</span>
            </div>
          </div>
        </div>
        <!-- 主题切换 -->
        <button class="theme-toggle" @click="toggleTheme" title="切换主题">
          <svg v-if="theme !== 'dark'" viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="4" stroke="currentColor" stroke-width="1.6"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
          <svg v-else viewBox="0 0 24 24" fill="none"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>
        </button>
        <!-- 设置 -->
        <button class="settings-btn" @click="showSettings = true" title="设置">
          <svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.6"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 01-2.83 2.83l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z" stroke="currentColor" stroke-width="1.6"/></svg>
        </button>
      </div>
    </header>

    <!-- 设置面板 -->
    <div class="settings-overlay" v-if="showSettings" @click.self="showSettings = false">
      <div class="settings-panel">
        <div class="settings-head">
          <h2>设置</h2>
          <button class="settings-close" @click="showSettings = false">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M4 4l8 8M4 12l8-8" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>
          </button>
        </div>
        <div class="settings-body">
          <div class="routing-hint">智能路由：系统根据任务类型自动选择模型</div>
          <div>
            <div class="settings-section-title">默认全局模型</div>
            <select class="model-select" v-model="globalModel">
              <option>Qwen3-30B-A3B</option>
              <option>Qwen3-14B</option>
              <option>DeepSeek-V3 (API)</option>
            </select>
          </div>
          <div>
            <div class="settings-section-title">专项模型</div>
            <select class="model-select" v-model="visionModel" style="margin-bottom:8px;">
              <option value="">不启用视觉模型</option>
              <option>Qwen2.5-VL-7B</option>
              <option>Qwen3-30B-A3B (多模态)</option>
            </select>
            <div class="settings-section-title" style="margin-top:12px;">代码模型</div>
            <select class="model-select" v-model="codeModel">
              <option value="">跟随全局模型</option>
              <option>DeepSeek-Coder-V2</option>
              <option>Qwen3-30B-A3B</option>
            </select>
          </div>
        </div>
      </div>
    </div>

    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const theme = ref(localStorage.getItem('myagent-theme') || '')
const showModelMenu = ref(false)
const showSettings = ref(false)
const llmOnline = ref(false)
const modelName = ref('Qwen3-30B-A3B')
const currentModel = ref('30b')
const globalModel = ref('Qwen3-30B-A3B')
const visionModel = ref('Qwen2.5-VL-7B')
const codeModel = ref('')

const models = [
  { label: 'Qwen3-30B-A3B', value: '30b' },
  { label: 'Qwen3-14B', value: '14b' },
  { label: 'DeepSeek-V3 (API)', value: 'api' },
]

function toggleTheme() {
  theme.value = theme.value === 'dark' ? '' : 'dark'
  localStorage.setItem('myagent-theme', theme.value)
}

function switchModel(m) {
  currentModel.value = m.value
  modelName.value = m.label
  showModelMenu.value = false
}

async function checkHealth() {
  try {
    const res = await fetch('/api/health')
    const data = await res.json()
    llmOnline.value = data.llm_available
  } catch { llmOnline.value = false }
}

onMounted(() => { checkHealth(); setInterval(checkHealth, 10000) })
</script>

<style>
/* ===== 专注向设计系统 ===== */
:root {
  --accent: #5b5df0;
  --accent-hover: #4a4cdb;
  --accent-soft: rgba(91,93,240,0.06);
  --accent-border: rgba(91,93,240,0.2);
  --bg-root: #f4f5f7;
  --bg-surface: #ffffff;
  --bg-hover: #ebecef;
  --bg-active: #e3e5f5;
  --text-primary: #1e2430;
  --text-secondary: #64748b;
  --text-tertiary: #94a3b8;
  --border: #e2e5e9;
  --border-light: #edf0f3;
  --success: #10b981;
  --success-bg: #ecfdf5;
  --danger: #ef4444;
  --shadow-card: 0 1px 3px rgba(15,23,42,0.06);
}

[data-theme="dark"] {
  --bg-root: #0f1119;
  --bg-surface: #181b24;
  --bg-hover: #1f2330;
  --bg-active: #24283a;
  --text-primary: #e4e6ed;
  --text-secondary: #9ca3b8;
  --text-tertiary: #6b7288;
  --border: #272b3a;
  --border-light: #1f2330;
  --shadow-card: 0 1px 3px rgba(0,0,0,0.4);
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  background: var(--bg-root);
  color: var(--text-primary);
  font-family: -apple-system, BlinkMacSystemFont, "SF Pro Display", "Inter", "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 14px; overflow: hidden;
  -webkit-font-smoothing: antialiased;
}

::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-thumb { background: #d4d4d8; border-radius: 3px; }

.app-shell { display: flex; flex-direction: column; height: 100vh; }

.topbar {
  display: flex; align-items: center; padding: 0 20px; height: 48px; flex-shrink: 0;
  background: rgba(255,255,255,0.8); backdrop-filter: blur(20px);
  border-bottom: 1px solid var(--border-light); gap: 6px;
}
[data-theme="dark"] .topbar { background: rgba(24,27,36,0.85); }

.topbar-brand { display: flex; align-items: center; gap: 10px; margin-right: 16px; flex-shrink: 0; }
.topbar-logo { width: 26px; height: 26px; border-radius: 7px; background: var(--accent); display: flex; align-items: center; justify-content: center; }
.topbar-logo svg { width: 14px; height: 14px; color: #fff; }
.topbar-name { font-size: 15px; font-weight: 700; letter-spacing: -0.3px; }

.topbar-nav { display: flex; gap: 2px; flex: 1; min-width: 0; overflow-x: auto; scrollbar-width: none; }
.topbar-nav::-webkit-scrollbar { display: none; }

.nav-item {
  padding: 5px 12px; border-radius: 7px; text-decoration: none;
  font-size: 13px; color: var(--text-secondary); font-weight: 500;
  transition: all 0.15s; white-space: nowrap;
}
.nav-item:hover { color: var(--text-primary); background: var(--bg-hover); }
.nav-item.router-link-active { color: var(--accent); background: var(--accent-soft); }

.topbar-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
.topbar-model-tag { font-size: 10px; }

.model-switcher { position: relative; }
.model-btn {
  display: flex; align-items: center; gap: 5px; font-size: 11px; color: var(--text-secondary);
  background: var(--bg-hover); padding: 4px 10px; border-radius: 10px; font-weight: 500;
  border: none; cursor: pointer; font-family: inherit; transition: all 0.15s;
}
.model-btn:hover { background: var(--bg-surface); box-shadow: var(--shadow-card); }
.model-btn svg { width: 10px; height: 10px; }

.model-dropdown {
  position: absolute; top: 100%; right: 0; margin-top: 6px;
  background: var(--bg-surface); border: 1px solid var(--border);
  border-radius: 12px; padding: 6px; min-width: 200px;
  box-shadow: var(--shadow-card), 0 12px 40px rgba(0,0,0,0.1); z-index: 100;
}
.model-dropdown-label { font-size: 10px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.5px; padding: 6px 10px 4px; }
.model-option {
  display: flex; align-items: center; justify-content: space-between;
  padding: 8px 10px; border-radius: 8px; cursor: pointer;
  font-size: 12px; color: var(--text-primary); transition: all 0.12s;
}
.model-option:hover { background: var(--bg-hover); }
.model-option.active { background: var(--accent-soft); color: var(--accent); }
.check { color: var(--accent); font-weight: 700; }

.theme-toggle {
  width: 28px; height: 28px; border-radius: 7px; border: 1px solid var(--border);
  background: var(--bg-surface); color: var(--text-tertiary);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.theme-toggle:hover { background: var(--bg-hover); color: var(--text-primary); }
.theme-toggle svg { width: 14px; height: 14px; }

.settings-btn {
  width: 28px; height: 28px; border-radius: 7px; border: 1px solid var(--border);
  background: var(--bg-surface); color: var(--text-tertiary);
  cursor: pointer; display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.settings-btn:hover { background: var(--bg-hover); color: var(--text-primary); }
.settings-btn svg { width: 14px; height: 14px; }

/* 设置面板 */
.settings-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.2); z-index: 200;
  display: flex; align-items: stretch; justify-content: flex-end;
}
.settings-panel {
  width: 400px; background: var(--bg-surface); height: 100%; overflow-y: auto;
  box-shadow: -8px 0 40px rgba(0,0,0,0.1); animation: slide-in 0.2s ease-out;
}
@keyframes slide-in { from { transform: translateX(40px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
.settings-head { display: flex; align-items: center; justify-content: space-between; padding: 20px 24px; border-bottom: 1px solid var(--border); }
.settings-head h2 { font-size: 17px; font-weight: 700; }
.settings-close { width: 30px; height: 30px; border-radius: 8px; border: none; background: var(--bg-hover); color: var(--text-secondary); cursor: pointer; display: flex; align-items: center; justify-content: center; }
.settings-close:hover { background: #fee2e2; color: var(--danger); }
.settings-body { padding: 20px 24px; display: flex; flex-direction: column; gap: 20px; }
.settings-section-title { font-size: 10px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 6px; }
.routing-hint { font-size: 11px; color: var(--text-tertiary); padding: 10px 14px; background: var(--bg-hover); border-radius: 10px; line-height: 1.5; }
.model-select { width: 100%; padding: 8px 12px; border: 1.5px solid var(--border); border-radius: 10px; font-size: 13px; color: var(--text-primary); background: var(--bg-surface); outline: none; font-family: inherit; }

.app-main { flex: 1; overflow: hidden; background: var(--bg-root); }
</style>
