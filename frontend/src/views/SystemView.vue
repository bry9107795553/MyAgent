<template>
  <div class="system-view">
    <!-- 顶部状态栏 -->
    <section class="status-bar">
      <div class="status-card" :class="{ online: systemData.gpu?.llm_available }">
        <div class="status-icon">{{ systemData.gpu?.llm_available ? '🟢' : '🔴' }}</div>
        <div class="status-info">
          <div class="status-label">推理引擎</div>
          <div class="status-value">{{ systemData.gpu?.llm_available ? 'llama.cpp 在线' : '离线' }}</div>
        </div>
      </div>
      <div class="status-card">
        <div class="status-icon">🎯</div>
        <div class="status-info">
          <div class="status-label">加载模型</div>
          <div class="status-value">{{ systemData.gpu?.model || '-' }}</div>
        </div>
      </div>
      <div class="status-card">
        <div class="status-icon">🖥️</div>
        <div class="status-info">
          <div class="status-label">GPU 模式</div>
          <div class="status-value">{{ systemData.gpu?.mode_label || systemData.gpu?.mode || '-' }}</div>
        </div>
      </div>
      <div class="status-card">
        <div class="status-icon">📊</div>
        <div class="status-info">
          <div class="status-label">系统规模</div>
          <div class="status-value">{{ systemData.role_count || 0 }} 角色 · {{ systemData.workgroup_count || 0 }} 工作组</div>
        </div>
      </div>
    </section>

    <!-- 角色列表 -->
    <section class="panel">
      <div class="panel-header">
        <h2>角色清单 ({{ systemData.role_count || 0 }})</h2>
        <span class="panel-hint">所有角色共享一个 {{ systemData.gpu?.model || '模型' }}，按类别分组</span>
      </div>
      <div class="role-grid">
        <div v-for="(roles, category) in systemData.categories" :key="category" class="role-group">
          <div class="group-label">{{ categoryLabels[category] || category }}</div>
          <div class="role-list">
            <div v-for="role in roles" :key="role.id" class="role-chip">
              <span class="role-name">{{ role.name }}</span>
              <span class="role-id">{{ role.id }}</span>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- 工作组 -->
    <section class="panel">
      <div class="panel-header">
        <h2>工作组 ({{ systemData.workgroup_count || 0 }})</h2>
        <span class="panel-hint">点击触发或在对话中输入关键词自动匹配</span>
      </div>
      <div class="workgroup-grid">
        <div v-for="wg in systemData.workgroups" :key="wg.id" class="workgroup-card">
          <div class="wg-header">
            <span class="wg-name">{{ wg.name }}</span>
            <span class="wg-steps">{{ wg.pipeline_steps }} 步</span>
          </div>
          <div class="wg-desc">{{ wg.description }}</div>
          <div class="wg-keywords">
            <span v-for="kw in wg.trigger_keywords.slice(0, 5)" :key="kw" class="kw-tag">{{ kw }}</span>
          </div>
          <div class="wg-members">
            <span v-for="m in wg.members.slice(0, 6)" :key="m" class="member-tag">{{ m }}</span>
            <span v-if="wg.members.length > 6" class="member-more">+{{ wg.members.length - 6 }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- 路由信息 -->
    <section class="panel small">
      <div class="panel-header">
        <h2>推理路由</h2>
      </div>
      <div class="routing-info">
        <code>{{ systemData.gpu?.routing || '-' }}</code>
        <div class="routing-endpoint">端点: {{ systemData.gpu?.endpoint || '-' }}</div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const systemData = ref({
  roles: [],
  categories: {},
  workgroups: [],
  role_count: 0,
  workgroup_count: 0,
  gpu: { mode: '', model: '', endpoint: '', llm_available: false, routing: '', mode_label: '' }
})

const categoryLabels = {
  general: '通用角色',
  dev: '开发团队',
  logistics: '后勤',
  management: '管理'
}

async function loadSystem() {
  try {
    const res = await fetch('/api/system')
    const data = await res.json()
    systemData.value = data
  } catch (e) {
    console.error('Failed to load system info:', e)
  }
}

onMounted(() => {
  loadSystem()
})
</script>

<style scoped>
.system-view {
  height: 100%;
  overflow-y: auto;
  padding: 24px;
}

.status-bar {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 24px;
}

.status-card {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-card.online {
  border-color: rgba(0, 184, 148, 0.3);
}

.status-icon {
  font-size: 24px;
}

.status-label {
  font-size: 12px;
  color: var(--text-2);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.status-value {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-0);
  margin-top: 2px;
}

.panel {
  background: var(--bg-1);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 20px;
  margin-bottom: 16px;
}

.panel.small {
  padding: 16px 20px;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 16px;
}

.panel-header h2 {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-0);
}

.panel-hint {
  font-size: 12px;
  color: var(--text-2);
}

.role-grid {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.role-group {
  /*  */
}

.group-label {
  font-size: 11px;
  color: var(--accent-2);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
  font-weight: 600;
}

.role-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.role-chip {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
}

.role-name {
  color: var(--text-0);
  font-weight: 500;
}

.role-id {
  color: var(--text-2);
  font-size: 11px;
  font-family: monospace;
}

.workgroup-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.workgroup-card {
  background: var(--bg-0);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  transition: border-color 0.2s;
}

.workgroup-card:hover {
  border-color: var(--accent);
}

.wg-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.wg-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-0);
}

.wg-steps {
  font-size: 11px;
  color: var(--accent-2);
  background: rgba(0, 206, 201, 0.1);
  padding: 1px 8px;
  border-radius: 8px;
}

.wg-desc {
  font-size: 12px;
  color: var(--text-2);
  margin-bottom: 10px;
  line-height: 1.5;
}

.wg-keywords {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}

.kw-tag {
  font-size: 10px;
  padding: 1px 6px;
  background: rgba(108, 92, 231, 0.1);
  color: var(--accent);
  border-radius: 4px;
}

.wg-members {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
}

.member-tag {
  font-size: 10px;
  padding: 1px 6px;
  background: rgba(255,255,255,0.05);
  color: var(--text-2);
  border-radius: 4px;
  font-family: monospace;
}

.member-more {
  font-size: 10px;
  color: var(--text-2);
}

.routing-info {
  font-size: 13px;
}

.routing-info code {
  display: block;
  padding: 8px 12px;
  background: var(--bg-0);
  border-radius: 6px;
  color: var(--accent-2);
  font-size: 13px;
  margin-bottom: 6px;
}

.routing-endpoint {
  font-size: 12px;
  color: var(--text-2);
  font-family: monospace;
}
</style>
