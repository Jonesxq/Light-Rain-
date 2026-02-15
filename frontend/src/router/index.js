import { createRouter, createWebHistory } from 'vue-router';
import LoginView from '../views/Login.vue';
import RegisterView from '../views/Register.vue';
import ChatView from '../views/Chat.vue';
import KnowledgeView from '../views/Knowledge.vue';
import SettingsView from '../views/Settings.vue';
import UsageView from '../views/Usage.vue';
import AiNewsView from '../views/AiNews.vue';
import MyView from '../views/My.vue';
import { getToken } from '../api/client.js';

const routes = [
  { path: '/', redirect: '/login' },
  { path: '/login', component: LoginView },
  { path: '/register', component: RegisterView },
  { path: '/chat', component: ChatView, meta: { requiresAuth: true } },
  { path: '/knowledge', component: KnowledgeView, meta: { requiresAuth: true } },
  { path: '/settings', component: SettingsView, meta: { requiresAuth: true } },
  { path: '/usage', component: UsageView, meta: { requiresAuth: true } },
  { path: '/ai-news', component: AiNewsView, meta: { requiresAuth: true } },
  { path: '/my', component: MyView, meta: { requiresAuth: true } },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  if (to.meta.requiresAuth && !getToken()) {
    return '/login';
  }
  return true;
});

export default router;

