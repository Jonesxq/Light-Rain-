import { createRouter, createWebHistory } from 'vue-router';
import LoginView from '../views/Login.vue';
import RegisterView from '../views/Register.vue';
import ChatView from '../views/Chat.vue';
import KnowledgeView from '../views/Knowledge.vue';
import { getToken } from '../api/client.js';

const routes = [
  { path: '/', redirect: '/login' },
  { path: '/login', component: LoginView },
  { path: '/register', component: RegisterView },
  { path: '/chat', component: ChatView, meta: { requiresAuth: true } },
  { path: '/knowledge', component: KnowledgeView, meta: { requiresAuth: true } },
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
