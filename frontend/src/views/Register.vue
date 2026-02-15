<template>
  <div class="auth-page auth-split">
    <div class="auth-globe" aria-hidden="true">
      <div class="globe">
        <div class="globe-texture"></div>
        <div class="globe-clouds"></div>
      </div>
    </div>
    <div class="auth-card">
      <h1>注册</h1>
      <p>创建新账号后请完成邮箱验证。</p>

      <div v-if="notice" class="notice">{{ notice }}</div>
      <div v-if="error" class="error">{{ error }}</div>

      <form class="auth-form" @submit.prevent="handleRegister">
        <label>
          用户名
          <input v-model="registerForm.username" required />
          <small class="hint">用户名不少于 3 个字符</small>
        </label>
        <label>
          邮箱
          <input type="email" v-model="registerForm.email" required />
        </label>
        <label>
          密码
          <input type="password" v-model="registerForm.password" required />
          <small class="hint">密码不少于 6 个字符</small>
        </label>
        <button type="submit">注册</button>
      </form>

      <div class="verify-block">
        <h2>邮箱验证码验证</h2>
        <p>注册完成后，将验证码填入并提交完成验证。</p>
        <form class="auth-form" @submit.prevent="handleVerifyEmail">
          <label>
            验证邮箱
            <input type="email" v-model="verifyForm.email" placeholder="注册邮箱" required />
          </label>
          <label>
            验证码
            <input v-model="verifyForm.code" placeholder="输入邮件验证码" required />
          </label>
          <button type="submit" class="ghost">提交验证</button>
        </form>
      </div>

      <div class="auth-links">
        <router-link to="/login">已有账号？去登录</router-link>
      </div>
    </div>

    <CenterToast :message="successMessage" />
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { apiFetch } from '../api/client.js';
import CenterToast from '../components/CenterToast.vue';
import { useCenterToast } from '../composables/useCenterToast.js';

const notice = ref('');
const error = ref('');
const { message: successMessage, show: showSuccess } = useCenterToast();

const registerForm = ref({
  username: '',
  email: '',
  password: '',
});

const verifyForm = ref({
  email: '',
  code: '',
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

const handleRegister = async () => {
  try {
    const data = await apiFetch('/auth/register', {
      method: 'POST',
      body: registerForm.value,
      skipAuth: true,
    });
    setNotice(`注册成功：${data.username}，请查收邮箱完成验证。`);
    verifyForm.value.email = registerForm.value.email;
  } catch (err) {
    setError(`注册失败：${err.message}`);
  }
};

const handleVerifyEmail = async () => {
  try {
    if (!verifyForm.value.email.trim()) {
      setError('请输入需要验证的邮箱');
      return;
    }
    if (!verifyForm.value.code.trim()) {
      setError('请输入邮箱验证码');
      return;
    }
    await apiFetch('/auth/verify-email', {
      method: 'POST',
      body: {
        email: verifyForm.value.email,
        code: verifyForm.value.code,
      },
      skipAuth: true,
    });
    setNotice('邮箱验证成功，可以前往登录。');
  } catch (err) {
    setError(`邮箱验证失败：${err.message}`);
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
