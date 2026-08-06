<template>
  <div class="workgroup-page">
    <div class="page-header">
      <h1>工作组</h1>
      <p class="subtitle">10 条预设流水线，按触发词自动匹配</p>
    </div>

    <div v-if="workgroups.length === 0" class="loading">加载中…</div>
    <div v-else class="wg-grid">
      <div v-for="wg in workgroups" :key="wg.id" class="wg-card">
        <div class="wg-head">
          <div class="wg-id">{{ wg.id }}</div>
          <div class="wg-name">{{ wg.name }}</div>
        </div>
        <div class="wg-desc">{{ wg.description }}</div>
        <div class="wg-meta">
          <span class="wg-stat">{{ wg.members.length }} 角色</span>
          <span class="wg-stat">{{ wg.pipeline_steps }} 步</span>
        </div>
        <div class="wg-triggers">
          <div class="triggers-label">触发关键词</div>
          <div class="triggers-list">
            <span v-for="t in wg.trigger_keywords.slice(0, 6)" :key="t" class="trigger-chip">{{ t }}</span>
            <span v-if="wg.trigger_keywords.length > 6" class="trigger-more">+{{ wg.trigger_keywords.length - 6 }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const workgroups = ref([])

async function loadWorkgroups() {
  try {
    const r = await fetch('/api/system')
    const d = await r.json()
    workgroups.value = d.workgroups || []
  } catch (e) {
    console.error('加载工作组失败', e)
  }
}

onMounted(loadWorkgroups)
</script>

<style scoped>
.workgroup-page { padding: 32px 40px; height: 100%; overflow-y: auto; }
.page-header { margin-bottom: 28px; }
.page-header h1 { font-size: 24px; font-weight: 700; letter-spacing: -0.5px; margin-bottom: 6px; }
.subtitle { font-size: 13px; color: var(--text-secondary); }
.loading { padding: 60px; text-align: center; color: var(--text-tertiary); }

.wg-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.wg-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 18px 20px;
  transition: all 0.15s;
  display: flex; flex-direction: column; gap: 10px;
}
.wg-card:hover {
  border-color: var(--accent-border);
  box-shadow: 0 4px 16px rgba(91,93,240,0.08);
  transform: translateY(-1px);
}

.wg-head { display: flex; align-items: center; gap: 10px; }
.wg-id {
  font-family: ui-monospace, "SF Mono", monospace;
  font-size: 11px; padding: 3px 8px;
  background: var(--accent-soft); color: var(--accent);
  border-radius: 6px; font-weight: 600;
}
.wg-name { font-size: 15px; font-weight: 600; }

.wg-desc { font-size: 12px; color: var(--text-secondary); line-height: 1.55; min-height: 36px; }

.wg-meta { display: flex; gap: 8px; }
.wg-stat {
  font-size: 11px; color: var(--text-tertiary);
  background: var(--bg-hover); padding: 3px 8px; border-radius: 6px;
}

.wg-triggers { display: flex; flex-direction: column; gap: 6px; }
.triggers-label { font-size: 10px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.5px; }
.triggers-list { display: flex; flex-wrap: wrap; gap: 5px; }
.trigger-chip {
  font-size: 11px; color: var(--text-secondary);
  background: var(--bg-root); border: 1px solid var(--border-light);
  padding: 3px 8px; border-radius: 6px;
}
.trigger-more {
  font-size: 11px; color: var(--text-tertiary);
  background: var(--bg-hover); padding: 3px 8px; border-radius: 6px;
}
</style>