import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'

// 路由
import ChatView from './views/ChatView.vue'
import WorkbenchView from './views/WorkbenchView.vue'
import SkinMarketView from './views/SkinMarketView.vue'
import SystemView from './views/SystemView.vue'

const routes = [
  { path: '/', name: 'chat', component: ChatView },
  { path: '/workbench', name: 'workbench', component: WorkbenchView },
  { path: '/skins', name: 'skins', component: SkinMarketView },
  { path: '/system', name: 'system', component: SystemView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
