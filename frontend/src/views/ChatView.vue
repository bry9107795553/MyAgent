<template>
  <div class="agent-platform">
    <!-- ===== 左栏: 系统状态 + 智能体 + 工作组 + 角色 ===== -->
    <aside class="left-panel">
      <div class="sys-bar" :class="{ online: llmOnline }" @click="showSys=!showSys">
        <span class="sys-dot"></span>
        <span class="sys-text">{{ llmOnline ? modelName : '离线' }}</span>
        <span class="sys-arrow">{{ showSys ? '▴' : '▾' }}</span>
      </div>
      <div v-if="showSys" class="sys-detail">
        <div class="kv"><span>模型</span><span>{{ modelName }}</span></div>
        <div class="kv"><span>角色</span><span>{{ roles.length }}</span></div>
        <div class="kv"><span>工作组</span><span>{{ workgroups.length }}</span></div>
      </div>

      <div class="section">
        <div class="shead">智能体</div>
        <div v-for="a in agents" :key="a.agent_id" class="a-item" :class="{ active: currentAgent===a.agent_id }"
             @click="selectAgent(a.agent_id)">
          <span class="a-icon">🤖</span>
          <div><div class="a-name">{{ a.name }}</div><div class="a-desc">{{ a.description }}</div></div>
        </div>
      </div>

      <div class="section">
        <div class="shead" @click="wgOpen=!wgOpen">工作组 {{ wgOpen?'▴':'▾' }}</div>
        <div v-if="wgOpen" class="slist">
          <div v-for="wg in workgroups" :key="wg.id" class="wg-chip" @click="triggerWg(wg)">
            <div class="wg-top"><span>{{ wg.name }}</span><span class="steps">{{ wg.pipeline_steps }}步</span></div>
            <div class="wg-kw">{{ (wg.trigger_keywords||[]).slice(0,3).join(' · ') }}</div>
          </div>
        </div>
      </div>

      <div class="section" style="flex:1">
        <div class="shead" @click="roleOpen=!roleOpen">角色 ({{ roles.length }}) {{ roleOpen?'▴':'▾' }}</div>
        <div v-if="roleOpen" class="slist">
          <div v-for="(grs,grp) in roleGroups" :key="grp">
            <div class="glabel">{{ groupLabels[grp]||grp }}</div>
            <div v-for="r in grs" :key="r.id" class="r-chip">
              <span class="rdot" :class="'g-'+r.gpu_affinity"></span>
              <span class="rname">{{ r.name }}</span>
            </div>
          </div>
        </div>
      </div>
    </aside>

    <!-- ===== 中栏: 对话 ===== -->
    <div class="chat-col">
      <div class="messages" ref="msgEl">
        <div v-if="messages.length===0 && !streaming" class="empty">
          <div class="empty-icon">💬</div>
          <div class="empty-title">MyAgent 就绪</div>
          <div class="empty-sub">输入消息开始对话，工作组自动触发</div>
          <div class="pills">
            <span class="pill" @click="sendQuick('我想要做程序开发')">程序开发</span>
            <span class="pill" @click="sendQuick('审查代码')">代码审查</span>
            <span class="pill" @click="sendQuick('做界面设计')">界面设计</span>
            <span class="pill" @click="sendQuick('翻译一段文本')">翻译</span>
          </div>
        </div>
        <div v-for="(m,i) in messages" :key="i" class="msg" :class="m.role">
          <div class="bubble" v-html="md(m.content)"></div>
          <div v-if="m.meta?.workgroup" class="msg-meta">
            <span class="mtag">{{ m.meta.workgroup }}</span>
            <span class="mroles" v-if="m.meta.roles_used?.length">{{ m.meta.roles_used.join(' → ') }}</span>
            <span class="done-badge" v-if="m.meta.roles_used?.length">✓ {{ m.meta.roles_used.length }}步完成</span>
          </div>
        </div>
        <div v-if="streaming" class="msg assistant"><div class="bubble streaming">{{ buf }}<span class="c">▊</span></div></div>
      </div>
      <div class="input-bar">
        <input v-model="txt" class="inp" placeholder="输入消息或关键词触发工作组..."
               @keyup.enter="send" :disabled="streaming"/>
        <button class="send-btn" @click="send" :disabled="streaming||!txt">{{ streaming?'…':'发送' }}</button>
      </div>
    </div>

    <!-- ===== 右栏: 产出区 ===== -->
    <aside class="right-panel">
      <div class="rhead">
        <span v-if="pipelineActive" class="rhead-badge active">执行中</span>
        <span v-else-if="lastPipeline.length" class="rhead-badge done">已完成</span>
        <span v-else class="rhead-badge idle">等待中</span>
        <span class="rhead-title">产出区</span>
      </div>
      <div class="rbody" v-if="pipelineActive || lastPipeline.length">
        <div class="pipeline-steps">
          <div v-for="(step, idx) in displaySteps" :key="idx" class="step"
               :class="{ done:step.s==='done', active:step.s==='running', fail:step.s==='fail' }"
               @click="selectedStep = idx">
            <div class="step-dot">
              <span v-if="step.s==='done'">✓</span>
              <span v-else-if="step.s==='running'">◉</span>
              <span v-else-if="step.s==='fail'">✗</span>
              <span v-else>{{ idx+1 }}</span>
            </div>
            <div class="step-info">
              <div class="step-role">{{ step.role }}</div>
              <div class="step-status">{{ step.s==='done'?'完成':step.s==='running'?'执行中…':step.s==='fail'?'失败':'等待' }}</div>
            </div>
          </div>
        </div>
        <div v-if="selectedStep!==null && displaySteps[selectedStep]?.output" class="step-detail">
          <div class="detail-head">{{ displaySteps[selectedStep].role }} · 产出</div>
          <div class="detail-body" v-html="md(displaySteps[selectedStep].output)"></div>
        </div>
      </div>
      <div class="rbody empty-r" v-else>
        <div class="empty-r-icon">📋</div>
        <div class="empty-r-text">工作组产出将在这里展示</div>
        <div class="empty-r-sub">发送「程序开发」「代码审查」等关键词触发</div>
      </div>
    </aside>
  </div>
</template>

<script setup>
import {ref,nextTick,onMounted,computed} from 'vue'
import {marked} from 'marked'

// ---- state ----
const agents=ref([]),currentAgent=ref(''),messages=ref([]),txt=ref('')
const streaming=ref(false),buf=ref(''),msgEl=ref(null),lastMeta=ref(null)
const llmOnline=ref(false),modelName=ref('Qwen2.5-14B'),showSys=ref(false)
const roles=ref([]),workgroups=ref([]),wgOpen=ref(true),roleOpen=ref(false)

// pipeline output panel
const pipelineActive=ref(false)
const pipelineSteps=ref([])      // {role, status: 'pending'|'running'|'done'|'fail', output}
const lastPipeline=ref([])
const selectedStep=ref(null)

const groupLabels={general:'通用',dev:'开发团队',logistics:'后勤',management:'管理'}
const roleGroups=computed(()=>{
  const g={};roles.value.forEach(r=>{const c=r.group||'general';(g[c]=g[c]||[]).push(r)});return g
})
const displaySteps = computed(() => pipelineActive.value ? pipelineSteps.value : lastPipeline.value)

function md(t){try{return marked(t||'')}catch{return t||''}}

// ---- data ----
async function loadAgents(){try{const r=await fetch('/api/agents');const d=await r.json();agents.value=d.agents||[];if(agents.value.length&&!currentAgent.value)selectAgent(agents.value[0].agent_id)}catch{}}
async function loadSys(){try{const r=await fetch('/api/system');const d=await r.json();roles.value=d.roles||[];workgroups.value=d.workgroups||[];if(d.gpu){llmOnline.value=d.gpu.llm_available;modelName.value=d.gpu.model||modelName.value}}catch{try{const r=await fetch('/api/health');const d=await r.json();llmOnline.value=d.llm_available}catch{}}}
function selectAgent(id){currentAgent.value=id;messages.value=[];loadHistory(id)}
async function loadHistory(id){try{const r=await fetch('/api/agents/'+id+'/history');messages.value=(await r.json()).history||[];scroll()}catch{}}

// ---- send ----
async function send(){
  if(!txt.value||!currentAgent.value)return
  const t=txt.value;txt.value='';messages.value.push({role:'user',content:t});scroll()
  streaming.value=true;buf.value=''

  // init pipeline panel
  pipelineActive.value=true
  pipelineSteps.value=[{role:'匹配中…',s:'running',output:''}]
  selectedStep.value=0

  const ws=new WebSocket((location.protocol==='https:'?'wss':'ws')+'://'+location.host+'/api/agents/'+currentAgent.value+'/ws')
  ws.onopen=()=>ws.send(JSON.stringify({message:t}))
  ws.onmessage=e=>{
    const d=JSON.parse(e.data)
    if(d.type==='stream_token'){buf.value+=d.content;scroll()}
    else if(d.type==='stream_meta'){
      lastMeta.value={type:d.dispatch_type,workgroup:d.workgroup,roles_used:d.roles_used}
      // update pipeline panel
      if(d.roles_used?.length){
        pipelineSteps.value=d.roles_used.map((r,i)=>({role:r,s:i===0?'running':'pending',output:''}))
        selectedStep.value=0
      }
    }
    else if(d.type==='stream_end'){
      const final = buf.value
      messages.value.push({role:'assistant',content:final,meta:lastMeta.value||undefined})
      buf.value='';lastMeta.value=null;streaming.value=false;ws.close()

      // finalize pipeline
      if(pipelineActive.value && pipelineSteps.value.length){
        // Try to parse workgroup output to extract per-role results
        try {
          const results = parsePipelineOutput(final)
          if(results.length){
            pipelineSteps.value = pipelineSteps.value.map((s,i)=>({
              ...s,s:'done',
              output:results[i]?.content||'已完成'
            }))
          } else {
            pipelineSteps.value = pipelineSteps.value.map(s=>({...s,s:'done',output:'已完成'}))
          }
        } catch {
          pipelineSteps.value = pipelineSteps.value.map(s=>({...s,s:'done',output:'已完成'}))
        }
        lastPipeline.value = [...pipelineSteps.value]
        selectedStep.value = 0
      }
      pipelineActive.value = false
    }
  }
  ws.onerror=()=>{streaming.value=false;buf.value='';pipelineActive.value=false}
}

function parsePipelineOutput(text) {
  // extract steps like "#### 步骤 1: 教练"  or "✓ 步骤 1: coach 完成"
  const steps = []
  const pattern = /(?:####?\s*)?步骤\s*(\d+)\s*[:：]\s*(\S+)/g
  const matches = [...text.matchAll(pattern)]
  if(!matches.length) return []

  // collect content between steps
  const segments = text.split(/(?:####?\s*)?步骤\s*\d+\s*[:：]\s*\S+/)
  matches.forEach((m,i) => {
    steps.push({num:m[1], role:m[2], content: (segments[i+1]||'').trim().slice(0,500)})
  })
  return steps
}

function sendQuick(t){txt.value=t;send()}
function triggerWg(wg){txt.value=(wg.trigger_keywords||[])[0]||wg.id;send()}
function scroll(){nextTick(()=>{if(msgEl.value)msgEl.value.scrollTop=msgEl.value.scrollHeight})}
onMounted(()=>{loadAgents();loadSys();setInterval(loadSys,15000)})
</script>

<style scoped>
.agent-platform{display:flex;height:100%}

/* ===== LEFT PANEL ===== */
.left-panel{width:240px;background:var(--bg-1);border-right:1px solid var(--border);display:flex;flex-direction:column;overflow-y:auto;flex-shrink:0}
.sys-bar{display:flex;align-items:center;gap:6px;padding:8px 10px;background:var(--bg-2);cursor:pointer;border-bottom:1px solid var(--border)}
.sys-dot{width:7px;height:7px;border-radius:50%;background:#e8463a}
.sys-bar.online .sys-dot{background:#00b894;box-shadow:0 0 5px rgba(0,184,148,.35)}
.sys-text{font-size:11px;color:var(--text-2);flex:1}
.sys-arrow{font-size:9px;color:var(--text-2)}
.sys-detail{padding:6px 10px;background:var(--bg-0);border-bottom:1px solid var(--border)}
.kv{display:flex;justify-content:space-between;font-size:11px;padding:2px 0;color:var(--text-2)}.kv span:last-child{color:var(--text-0)}
.section{border-bottom:1px solid var(--border)}
.shead{padding:10px 10px 6px;font-size:10px;color:var(--text-2);text-transform:uppercase;letter-spacing:.05em;cursor:pointer;display:flex;justify-content:space-between}
.shead:hover{color:var(--text-0)}
.a-item{display:flex;gap:8px;padding:8px 10px;cursor:pointer;transition:background .12s}
.a-item:hover{background:rgba(255,255,255,.02)}
.a-item.active{background:rgba(108,92,231,.1);border-right:2px solid var(--accent)}
.a-icon{font-size:16px;flex-shrink:0}
.a-name{font-size:12px;font-weight:500;color:var(--text-0)}.a-desc{font-size:10px;color:var(--text-2);margin-top:1px}
.slist{max-height:260px;overflow-y:auto;padding:0 8px 6px}
.glabel{font-size:9px;color:var(--accent-2);text-transform:uppercase;letter-spacing:.05em;padding:5px 3px 2px;font-weight:600}
.r-chip{display:flex;align-items:center;gap:5px;padding:2px 6px;margin:1px 0;border-radius:4px;font-size:11px}
.rdot{width:5px;height:5px;border-radius:50%;flex-shrink:0}.g-gpu0{background:var(--accent)}.g-gpu1{background:var(--accent-2)}.g-gpu2{background:#fdcb6e}
.rname{color:var(--text-0);font-size:11px}
.wg-chip{padding:5px 8px;margin:2px 0;border-radius:5px;cursor:pointer;border:1px solid transparent;transition:all .12s}
.wg-chip:hover{background:var(--bg-2);border-color:var(--accent)}
.wg-top{display:flex;justify-content:space-between;font-size:11px}.wg-top span:first-child{color:var(--text-0);font-weight:500}
.steps{font-size:9px;color:var(--accent-2);background:rgba(0,206,201,.1);padding:0 5px;border-radius:6px}
.wg-kw{font-size:9px;color:var(--text-2);margin-top:2px}

/* ===== CHAT ===== */
.chat-col{flex:1;display:flex;flex-direction:column;min-width:0}
.messages{flex:1;overflow-y:auto;padding:20px 24px}
.empty{display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;gap:10px}
.empty-icon{font-size:44px}.empty-title{font-size:18px;font-weight:600}.empty-sub{font-size:12px;color:var(--text-2)}
.pills{display:flex;gap:6px;flex-wrap:wrap;justify-content:center;margin-top:6px}
.pill{padding:5px 14px;background:var(--bg-1);border:1px solid var(--border);border-radius:16px;font-size:12px;color:var(--text-1);cursor:pointer;transition:all .12s}
.pill:hover{border-color:var(--accent);color:var(--accent)}
.msg{margin-bottom:14px;max-width:78%}.msg.user{margin-left:auto}
.bubble{padding:9px 14px;border-radius:10px;font-size:13px;line-height:1.6}
.msg.user .bubble{background:var(--accent);color:#fff;border-bottom-right-radius:2px}
.msg.assistant .bubble{background:var(--bg-1);border:1px solid var(--border);border-bottom-left-radius:2px}
.c{animation:blink 1s infinite}@keyframes blink{50%{opacity:0}}
.msg-meta{margin-top:4px;padding-left:4px;display:flex;gap:6px;align-items:center;flex-wrap:wrap}
.mtag{padding:2px 7px;background:rgba(108,92,231,.1);border:1px solid rgba(108,92,231,.2);border-radius:8px;font-size:10px;color:var(--accent)}
.mroles{font-size:9px;color:var(--text-2)}
.done-badge{font-size:10px;color:#00b894}
.input-bar{display:flex;gap:8px;padding:14px 18px;border-top:1px solid var(--border)}
.inp{flex:1;padding:9px 14px;background:var(--bg-1);border:1px solid var(--border);border-radius:8px;color:var(--text-0);font-size:13px;outline:none}.inp:focus{border-color:var(--accent)}
.send-btn{padding:9px 16px;background:var(--accent);border:none;border-radius:8px;color:#fff;font-size:13px;cursor:pointer}.send-btn:disabled{opacity:.4;cursor:not-allowed}

/* ===== RIGHT PANEL (产出区) ===== */
.right-panel{width:280px;background:var(--bg-1);border-left:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0}
.rhead{display:flex;align-items:center;gap:8px;padding:10px 12px;border-bottom:1px solid var(--border)}
.rhead-badge{padding:2px 8px;border-radius:8px;font-size:10px;font-weight:500}
.rhead-badge.active{background:rgba(0,206,201,.12);color:var(--accent-2);animation:pulse 2s infinite}
.rhead-badge.done{background:rgba(0,184,148,.12);color:#00b894}
.rhead-badge.idle{background:rgba(255,255,255,.04);color:var(--text-2)}
.rhead-title{font-size:12px;font-weight:600;color:var(--text-0)}
@keyframes pulse{50%{opacity:.5}}
.rbody{flex:1;overflow-y:auto}
.pipeline-steps{padding:8px}
.step{display:flex;gap:8px;padding:8px;border-radius:6px;cursor:pointer;transition:background .12s;align-items:center;border:1px solid transparent}
.step:hover{background:rgba(255,255,255,.02)}
.step.active{border-color:var(--accent);background:rgba(108,92,231,.08)}
.step.done{opacity:.7}
.step.fail{border-color:rgba(232,70,58,.3)}
.step-dot{width:20px;height:20px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:10px;flex-shrink:0;background:var(--bg-2);color:var(--text-2)}
.step.done .step-dot{background:rgba(0,184,148,.15);color:#00b894}
.step.active .step-dot{background:rgba(108,92,231,.15);color:var(--accent);animation:pulse 1.5s infinite}
.step.fail .step-dot{background:rgba(232,70,58,.15);color:#e8463a}
.step-info{min-width:0}
.step-role{font-size:12px;color:var(--text-0);font-weight:500}
.step-status{font-size:10px;color:var(--text-2);margin-top:1px}
.step-detail{margin:0 8px 8px;background:var(--bg-2);border:1px solid var(--border);border-radius:8px;overflow:hidden}
.detail-head{padding:8px 10px;font-size:11px;color:var(--accent-2);border-bottom:1px solid var(--border);font-weight:500}
.detail-body{padding:10px;font-size:12px;line-height:1.6;color:var(--text-1);max-height:300px;overflow-y:auto}
.empty-r{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;padding:32px 16px}
.empty-r-icon{font-size:40px}.empty-r-text{font-size:13px;color:var(--text-1);font-weight:500}.empty-r-sub{font-size:11px;color:var(--text-2)}
</style>
