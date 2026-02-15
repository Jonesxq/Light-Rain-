<template>
  <div class="auth-page auth-split">
    <div class="auth-globe" aria-hidden="true">
      <div class="globe">
        <div class="globe-texture"></div>
        <div class="globe-clouds"></div>
      </div>
    </div>
    <div class="auth-card">
      <h1>登录</h1>
      <p>使用邮箱或用户名登录系统。</p>

      <div v-if="notice" class="notice">{{ notice }}</div>
      <div v-if="error" class="error">{{ error }}</div>

      <form class="auth-form" @submit.prevent="handleLogin">
        <label>
          邮箱或用户名
          <input v-model="loginForm.identifier" placeholder="email 或 username" required />
        </label>
        <label>
          密码
          <input type="password" v-model="loginForm.password" required />
        </label>
        <button type="submit">登录</button>
      </form>

      <div class="auth-links">
        <router-link to="/register">没有账号？去注册</router-link>
      </div>
    </div>

    <CenterToast :message="successMessage" />
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { apiFetch, setTokens } from '../api/client.js';
import CenterToast from '../components/CenterToast.vue';
import { useCenterToast } from '../composables/useCenterToast.js';

const router = useRouter();
const notice = ref('');
const error = ref('');
const { message: successMessage, show: showSuccess } = useCenterToast();

const loginForm = ref({
  identifier: '',
  password: '',
});

const setNotice = (message) => {
  showSuccess(message);
  notice.value = '';
  error.value = '';
};

const setError = (message) => {
  error.value = message;
  notice.value = '';
};

const handleLogin = async () => {
  try {
    const identifier = loginForm.value.identifier.trim();
    if (!identifier) {
      setError('请输入邮箱或用户名');
      return;
    }
    const payload = { password: loginForm.value.password };
    if (identifier.includes('@')) {
      payload.email = identifier;
    } else {
      payload.username = identifier;
    }
    const data = await apiFetch('/auth/login', {
      method: 'POST',
      body: payload,
      skipAuth: true,
    });
    setTokens(data.access_token, data.refresh_token);
    showSuccess('登录成功');
    notice.value = '';
    error.value = '';
    await new Promise((resolve) => setTimeout(resolve, 700));
    router.push('/chat');
  } catch (err) {
    setError(`登录失败：${err.message}`);
  }
};
</script>

<style scoped>
.auth-form,
.auth-links {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.auth-links {
  text-align: center;
}
</style>
