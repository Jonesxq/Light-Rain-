<template>
  <div class="page settings-page">
    <header class="header">
      <div>
        <h1>模型设置</h1>
        <p>配置你的 OpenAI 兼容模型 Key / Base URL / 模型名。</p>
      </div>
      <div class="header-actions">
        <div class="actions action-bar">
          <button class="ghost" @click="goChat">返回聊天</button>
          <button class="ghost" @click="goMy">我的</button>
          <button class="ghost" @click="goUsage">使用量看板</button>
        </div>
      </div>
    </header>

    <div v-if="notice" class="notice">{{ notice }}</div>
    <div v-if="error" class="error">{{ error }}</div>

    <section class="card">
      <div class="card-head">
        <h2>用户模型配置</h2>
        <label class="toggle">
          <input type="checkbox" v-model="form.enabled" />
          <span>启用</span>
        </label>
      </div>

      <div class="form-grid">
        <label>
          API Key
          <input
            v-model="form.apiKey"
            type="password"
            placeholder="输入你的 API Key"
          />
          <small v-if="hasApiKey">
            已设置：{{ maskedKey }}
          </small>
          <small v-else>尚未设置 API Key</small>
        </label>

        <label>
          Base URL
          <input
            v-model="form.apiBaseUrl"
            placeholder="https://api.openai.com/v1"
          />
        </label>

        <label>
          模型名
          <input v-model="form.model" placeholder="例如 gpt-4o-mini" />
        </label>
      </div>

      <div class="actions">
        <button @click="saveSettings">保存设置</button>
        <button class="ghost" @click="clearKey" :disabled="!hasApiKey">清空 Key</button>
        <button class="ghost danger" @click="clearSettings">清空配置</button>
      </div>
    </section>

    <CenterToast :message="successMessage" />
  </div>
</template>

<script setup>
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { apiFetch } from '../api/client.js';
import CenterToast from '../components/CenterToast.vue';
import { useCenterToast } from '../composables/useCenterToast.js';

const router = useRouter();
const notice = ref('');
const error = ref('');
const { message: successMessage, show: showSuccess } = useCenterToast();

const form = ref({
  enabled: true,
  apiBaseUrl: '',
  model: '',
  apiKey: '',
});
const maskedKey = ref('');
const hasApiKey = ref(false);

const setNotice = (message) => {
  showSuccess(message);
  notice.value = '';
  error.value = '';
};

const setError = (message) => {
  error.value = message;
  notice.value = '';
};

const goChat = () => {
  router.push('/chat');
};

const goMy = () => {
  router.push('/my');
};

const goUsage = () => {
  router.push('/usage');
};

const loadSettings = async () => {
  try {
    const data = await apiFetch('/llm-settings/me');
    form.value.enabled = data.enabled ?? false;
    form.value.apiBaseUrl = data.api_base_url || '';
    form.value.model = data.model || '';
    form.value.apiKey = '';
    maskedKey.value = data.api_key_masked || '';
    hasApiKey.value = Boolean(data.has_api_key);
  } catch (err) {
    setError(`获取配置失败：${err.message}`);
  }
};

const saveSettings = async () => {
  try {
    const payload = {
      enabled: form.value.enabled,
      api_base_url: form.value.apiBaseUrl,
      model: form.value.model,
    };
    if (form.value.apiKey && form.value.apiKey.trim()) {
      payload.api_key = form.value.apiKey.trim();
    }
    const data = await apiFetch('/llm-settings/me', {
      method: 'PUT',
      body: payload,
    });
    form.value.apiKey = '';
    maskedKey.value = data.api_key_masked || '';
    hasApiKey.value = Boolean(data.has_api_key);
    setNotice('模型设置已保存');
  } catch (err) {
    setError(`保存失败：${err.message}`);
  }
};

const clearKey = async () => {
  try {
    const payload = {
      enabled: form.value.enabled,
      api_base_url: form.value.apiBaseUrl,
      model: form.value.model,
      api_key: '',
    };
    const data = await apiFetch('/llm-settings/me', {
      method: 'PUT',
      body: payload,
    });
    form.value.apiKey = '';
    maskedKey.value = data.api_key_masked || '';
    hasApiKey.value = Boolean(data.has_api_key);
    setNotice('API Key 已清空');
  } catch (err) {
    setError(`清空失败：${err.message}`);
  }
};

const clearSettings = async () => {
  const confirmed = window.confirm('确定清空配置吗？该操作会移除已保存的 Key。');
  if (!confirmed) return;
  try {
    await apiFetch('/llm-settings/me', { method: 'DELETE' });
    form.value = { enabled: false, apiBaseUrl: '', model: '', apiKey: '' };
    maskedKey.value = '';
    hasApiKey.value = false;
    setNotice('配置已清空');
  } catch (err) {
    setError(`清空失败：${err.message}`);
  }
};

loadSettings();
</script>

<style scoped>
.settings-page {
  position: relative;
  width: 1200px;
  height: 760px;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 48px);
  margin: 24px auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  background: var(--page-panel);
  border-radius: var(--radius-xl);
  border: 1px solid var(--border);
  box-shadow: var(--shadow-lg);
  overflow: auto;
  font-family: var(--font-sans);
  color: var(--text-strong);
}

.settings-page::before {
  content: none;
  display: none;
}

.settings-page > * {
  position: relative;
  z-index: 1;
}

.settings-page small {
  color: var(--text-soft);
}

.settings-page button.danger {
  color: var(--error-text);
  border-color: rgba(239, 68, 68, 0.3);
}

.settings-page .form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.settings-page .toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #49517a;
}

@media (max-width: 1080px) {
  .settings-page {
    width: 100%;
    height: auto;
    max-height: none;
    margin: 16px auto;
  }

  .settings-page .header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>


