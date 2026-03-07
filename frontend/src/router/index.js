import { createRouter, createWebHistory } from 'vue-router';
import { getToken } from '../api/client.js';

const LoginView = () => import('../views/Login.vue');
const RegisterView = () => import('../views/Register.vue');
const ChatView = () => import('../views/Chat.vue');
const KnowledgeView = () => import('../views/Knowledge.vue');
const SettingsView = () => import('../views/Settings.vue');
const UsageView = () => import('../views/Usage.vue');
const AiNewsView = () => import('../views/AiNews.vue');
const MyView = () => import('../views/My.vue');

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

