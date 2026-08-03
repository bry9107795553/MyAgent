<template>
  <div class="skin-market">
    <h2>皮肤仓库</h2>
    <div class="skin-grid">
      <div
        v-for="skin in skins"
        :key="skin.id"
        class="skin-card"
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

async function loadSkins() {
  const res = await fetch('/api/skins')
  const data = await res.json()
  skins.value = data.skins || []
}

async function applySkin(skinId) {
  await fetch('/api/skins/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ skin_id: skinId }),
  })
  alert(`皮肤已应用: ${skinId}`)
}

onMounted(() => {
  loadSkins()
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
