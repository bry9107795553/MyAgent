<template>
  <div class="skin-market">
    <h2>皮肤仓库</h2>
    <div class="skin-grid">
      <div
        v-for="skin in skins"
        :key="skin.id"
        class="skin-card"
        :class="{active: skin.id === currentSkinId}"
        @click="applySkin(skin.id)"
      >
        <div class="skin-preview">
          <div
            v-for="color in skin.preview_colors"
            :key="color"
            class="color-dot"
            :style="{ background: color }"
          ></div>
        </div>
        <div class="skin-name">{{ skin.name }}</div>
        <div class="skin-desc">{{ skin.description }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const skins = ref([])
const currentSkinId = ref('')

async function loadSkins() {
  try {
    const res = await fetch('/api/skins')
    const data = await res.json()
    skins.value = data.skins || []
  } catch (e) {
    console.warn('加载皮肤失败:', e)
  }
}

async function loadCurrentSkin() {
  try {
    const res = await fetch('/api/skins/current')
    const data = await res.json()
    currentSkinId.value = data.id || data.skin_id || ''
  } catch (e) {}
}

async function applySkin(skinId) {
  // 1. 通知后端
  try {
    await fetch('/api/skins/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ skin_id: skinId }),
    })
  } catch (e) {}

  // 2. 从 skins 列表中找到完整配置并应用 CSS 变量
  const skin = skins.value.find(s => s.id === skinId)
  if (skin && skin.variables) {
    const root = document.documentElement
    for (const [key, val] of Object.entries(skin.variables)) {
      root.style.setProperty(key, val)
    }
    currentSkinId.value = skinId
    // 记住选择
    localStorage.setItem('myagent_skin', skinId)
  }
}

onMounted(async () => {
  await loadSkins()
  // 恢复上次选择的皮肤
  const savedSkin = localStorage.getItem('myagent_skin')
  if (savedSkin && skins.value.find(s => s.id === savedSkin)) {
    await applySkin(savedSkin)
  } else {
    await loadCurrentSkin()
    // 如果后端有 current，可能不在前端 skins 列表中，尝试重新加载
    if (currentSkinId.value) {
      const current = skins.value.find(s => s.id === currentSkinId.value)
      if (current) await applySkin(current.id)
    }
  }
})
</script>

<style scoped>
.skin-market {
  padding: 24px;
  overflow-y: auto;
  height: 100%;
}
.skin-market h2 {
  font-size: 20px;
  margin-bottom: 24px;
}
.skin-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 16px;
}
.skin-card {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px;
  cursor: pointer;
  transition: border-color 0.2s;
}
.skin-card:hover {
  border-color: var(--accent);
}
.skin-card.active {
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-2, var(--accent));
}
.skin-preview {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
  height: 40px;
  border-radius: 8px;
  overflow: hidden;
}
.color-dot {
  flex: 1;
}
.skin-name {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 4px;
}
.skin-desc {
  font-size: 12px;
  color: var(--text-2);
}
</style>
