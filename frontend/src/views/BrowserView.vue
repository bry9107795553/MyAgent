<template>
  <div class="browser-view">
    <!-- 顶部标签栏 -->
    <div class="browser-tabs">
      <div class="tab" :class="{ active: activeTab === 'files' }" @click="activeTab='files'">📁 文件</div>
      <div class="tab" :class="{ active: activeTab === 'projects' }" @click="activeTab='projects'">📦 项目</div>
    </div>

    <!-- 文件浏览器 -->
    <div v-if="activeTab==='files'" class="file-browser">
      <div class="breadcrumb">
        <span class="bc-item" @click="cd('')">/</span>
        <template v-for="(part, i) in currentPath" :key="i">
          <span class="bc-sep">/</span>
          <span class="bc-item" @click="cd(currentPath.slice(0, i+1).join('/'))">{{ part }}</span>
        </template>
      </div>
      <div class="file-list">
        <div v-if="listing.length===0" class="empty-files">空目录</div>
        <div v-for="item in listing" :key="item.name"
             class="file-row"
             :class="{ dir: item.is_dir }"
             @click="item.is_dir ? cd((currentPath.length?currentPath.join('/')+'/':'')+item.name) : openFile(item)">
          <span class="file-icon">{{ item.is_dir ? '📁' : iconFor(item.name) }}</span>
          <span class="file-name">{{ item.name }}</span>
          <span class="file-size" v-if="!item.is_dir">{{ fmtSize(item.size) }}</span>
        </div>
      </div>
    </div>

    <!-- 文件预览 -->
    <div v-if="previewContent!==null" class="preview-panel">
      <div class="preview-head">
        <span>{{ previewFile }}</span>
        <button class="preview-close" @click="previewContent=null;previewFile=''">✕</button>
      </div>
      <div class="preview-body" v-html="previewContent"></div>
    </div>

    <!-- 项目列表 -->
    <div v-if="activeTab==='projects'" class="projects-panel">
      <div v-if="projects.length===0" class="empty-files">暂无项目</div>
      <div v-for="p in projects" :key="p.id" class="project-card" @click="openProject(p)">
        <div class="pj-name">{{ p.name || p.id }}</div>
        <div class="pj-meta">状态: {{ p.status || '未知' }}</div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { marked } from 'marked'

const activeTab = ref('files')
const currentPath = ref([])
const listing = ref([])
const projects = ref([])
const workgroups = ref([])
const previewContent = ref(null)
const previewFile = ref('')

const extIcons = {
  '.md': '📝', '.py': '🐍', '.js': '🟨', '.ts': '🔷', '.vue': '💚',
  '.json': '📋', '.yaml': '⚙', '.yml': '⚙', '.css': '🎨', '.html': '🌐',
  '.sh': '🖥', '.txt': '📄', '.xml': '📰', '.svg': '🖼', '.csv': '📊',
  '.png': '🖼', '.jpg': '🖼', '.gif': '🖼', '.pptx': '📊', '.pdf': '📕',
  '.toml': '⚙', '.cfg': '⚙', '.ini': '⚙', '.env': '🔒',
}
function iconFor(name) {
  const ext = name.substring(name.lastIndexOf('.'))
  return extIcons[ext] || '📄'
}

function fmtSize(b) {
  if (!b) return ''
  if (b < 1024) return b + ' B'
  if (b < 1024*1024) return (b/1024).toFixed(1) + ' KB'
  return (b/1024/1024).toFixed(2) + ' MB'
}

async function cd(dir) {
  const path = dir.split('/').filter(Boolean).join('/')
  currentPath.value = path ? path.split('/') : []
  try {
    const res = await fetch(`/api/read?path=${encodeURIComponent(path)}`)
    const data = await res.json()
    listing.value = data.files || []
  } catch {
    listing.value = []
  }
}

async function openFile(item) {
  const path = (currentPath.value.length ? currentPath.value.join('/')+'/' : '') + item.name
  previewFile.value = item.name
  try {
    const res = await fetch(`/api/read?path=${encodeURIComponent(path)}`)
    const data = await res.json()
    if (data.content) {
      const ext = item.name.substring(item.name.lastIndexOf('.'))
      if (['.md','.txt','.json','.yaml','.yml','.xml','.html','.css','.js','.ts','.vue','.py','.sh','.csv','.toml','.cfg'].includes(ext)) {
        if (ext === '.md') previewContent.value = marked(data.content)
        else previewContent.value = `<pre class="code-block" style="background:var(--bg-0);color:var(--text-1);padding:16px;border-radius:8px;font-size:13px;line-height:1.6;overflow:auto;max-height:70vh;font-family:monospace;white-space:pre-wrap">${esc(data.content)}</pre>`
      } else {
        previewContent.value = `<div style="padding:32px;text-align:center;color:var(--text-2)">📄 ${item.name}<br><small>二进制或不可预览文件</small></div>`
      }
    } else if (data.files) {
      previewContent.value = `<div style="padding:16px;color:var(--text-2)">📁 目录: ${item.name}</div>`
    }
  } catch {
    previewContent.value = `<div style="padding:16px;color:#e8463a">⚠ 无法读取: ${item.name}</div>`
  }
}

async function openProject(p) {
  activeTab.value = 'files'
  await cd('projects/' + (p.id||p.name||''))
}

function esc(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;') }

onMounted(async () => {
  // load from /api/projects if available
  try {
    const r = await fetch('/api/projects')
    const d = await r.json()
    projects.value = d.projects || []
  } catch {}
  // load workgroups
  try {
    const r = await fetch('/api/system')
    const d = await r.json()
    workgroups.value = d.workgroups || []
  } catch {
    try {
      const r = await fetch('/api/workgroups')
      const d = await r.json()
      workgroups.value = d.workgroups || []
    } catch {}
  }
  // initial file listing
  await cd('')
})
</script>

<style scoped>
.browser-view{display:flex;flex-direction:column;height:100%}
.browser-tabs{display:flex;gap:0;padding:8px 16px 0;border-bottom:1px solid var(--border)}
.tab{padding:8px 16px;font-size:13px;color:var(--text-2);cursor:pointer;border-bottom:2px solid transparent;transition:all .15s}
.tab:hover{color:var(--text-0)}
.tab.active{color:var(--accent-2);border-bottom-color:var(--accent-2)}
.file-browser{flex:1;display:flex;flex-direction:column;overflow:hidden}
.breadcrumb{padding:10px 16px;font-size:12px;color:var(--text-2);border-bottom:1px solid var(--border);display:flex;align-items:center;gap:4px;flex-wrap:wrap}
.bc-item{cursor:pointer;color:var(--accent-2)}.bc-item:hover{text-decoration:underline}.bc-sep{color:var(--text-2)}
.file-list{flex:1;overflow-y:auto;padding:4px 0}
.file-row{display:flex;align-items:center;gap:8px;padding:6px 16px;cursor:pointer;font-size:13px;transition:background .1s}.file-row:hover{background:rgba(255,255,255,.03)}
.file-row.dir{color:var(--accent-2)}
.file-icon{font-size:16px;flex-shrink:0}.file-name{color:var(--text-0);flex:1}.file-size{font-size:11px;color:var(--text-2)}
.empty-files{padding:32px;text-align:center;color:var(--text-2);font-size:13px}
.preview-panel{height:40%;border-top:1px solid var(--border);display:flex;flex-direction:column;overflow:hidden}
.preview-head{display:flex;justify-content:space-between;align-items:center;padding:8px 16px;background:var(--bg-1);border-bottom:1px solid var(--border);font-size:12px;color:var(--text-0)}
.preview-close{background:none;border:none;color:var(--text-2);cursor:pointer;font-size:14px}.preview-close:hover{color:#e8463a}
.preview-body{flex:1;overflow:auto;padding:12px 16px}
.projects-panel,.workgroups-panel{flex:1;overflow-y:auto;padding:16px}
.project-card{padding:14px;background:var(--bg-1);border:1px solid var(--border);border-radius:8px;margin-bottom:10px;cursor:pointer;transition:border .15s}.project-card:hover{border-color:var(--accent)}
.pj-name{font-size:14px;font-weight:600;color:var(--text-0)}.pj-meta{font-size:12px;color:var(--text-2);margin-top:4px}
.wg-detail-card{padding:14px;background:var(--bg-1);border:1px solid var(--border);border-radius:8px;margin-bottom:10px}
.wg-d-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px}
.wg-d-name{font-size:14px;font-weight:600;color:var(--text-0)}
.wg-d-steps{font-size:10px;background:rgba(0,206,201,.1);color:var(--accent-2);padding:1px 8px;border-radius:8px}
.wg-d-desc{font-size:12px;color:var(--text-2);margin-bottom:8px;line-height:1.5}
.wg-d-meta{font-size:11px;color:var(--text-2);margin-top:3px}.wg-d-meta label{color:var(--text-0);font-weight:500}
</style>
