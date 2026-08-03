<template>
  <div class="app-shell">
    <!-- 顶部导航栏 -->
    <header class="app-header">
      <div class="app-logo">MyAgent</div>
      <nav class="app-nav">
        <router-link to="/" class="nav-item">对话</router-link>
        <router-link to="/workbench" class="nav-item">工作台</router-link>
        <router-link to="/skins" class="nav-item">皮肤</router-link>
      </nav>
      <div class="app-status">
        <span class="status-dot" :class="{ online: llmOnline }"></span>
        <span class="status-text">{{ llmOnline ? 'llama.cpp 在线' : 'llama.cpp 离线' }}</span>
      </div>
    </header>

    <!-- 主内容区 -->
    <main class="app-main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const llmOnline = ref(false)

async function checkHealth() {
  try {
    const res = await fetch('/api/health')
    const data = await res.json()
    llmOnline.value = data.llm_available
  } catch {
    llmOnline.value = false
  }
}

onMounted(() => {
  checkHealth()
  setInterval(checkHealth, 10000) // 每 10 秒检查一次
})
</script>

<style>
:root {
  --bg-0: #0f0f1a;
  --bg-1: #1a1a2e;
  --bg-2: #16213e;
  --text-0: #e8e8f0;
  --text-1: #c8d8e8;
  --text-2: #8aa8c8;
  --accent: #6c5ce7;
  --accent-2: #00cec9;
  --border: rgba(255,255,255,0.08);
  --radius: 12px;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  background: var(--bg-0);
  color: var(--text-0);
  font-family: "SF Pro Text", "PingFang SC", -apple-system, "Segoe UI", Roboto, sans-serif;
  font-size: 15px;
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
  padding: 0 24px;
  height: 56px;
  background: var(--bg-1);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.app-logo {
  font-size: 18px;
  font-weight: 700;
  background: linear-gradient(135deg, var(--accent), var(--accent-2));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin-right: 32px;
}

.app-nav {
  display: flex;
  gap: 8px;
  flex: 1;
}

.nav-item {
  padding: 6px 16px;
  border-radius: 8px;
  text-decoration: none;
  color: var(--text-2);
  font-size: 14px;
  transition: all 0.2s;
}

.nav-item:hover {
  color: var(--text-0);
  background: rgba(255,255,255,0.05);
}

.nav-item.router-link-active {
  color: var(--accent-2);
  background: rgba(0,206,201,0.1);
}

.app-status {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--text-2);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #e8463a;
}

.status-dot.online {
  background: #00b894;
}

.app-main {
  flex: 1;
  overflow: hidden;
}
</style>
