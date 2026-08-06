import { createApp } from 'vue'
import { createPinia } from 'pinia'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'

// 路由
import ChatView from './views/ChatView.vue'
import WorkbenchView from './views/WorkbenchView.vue'
import SkinMarketView from './views/SkinMarketView.vue'
import BrowserView from './views/BrowserView.vue'
import WorkgroupView from './views/WorkgroupView.vue'

const routes = [
  { path: '/', name: 'chat', component: ChatView },
  { path: '/history', redirect: '/' },
  { path: '/workgroups', name: 'workgroups', component: WorkgroupView },
  { path: '/plugins', redirect: '/' },
  { path: '/browse', name: 'browse', component: BrowserView },
  { path: '/workbench', name: 'workbench', component: WorkbenchView },
  { path: '/skins', name: 'skins', component: SkinMarketView },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

const app = createApp(App)
app.use(createPinia())
app.use(router)
app.mount('#app')
