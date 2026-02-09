<template>
  <div class="page settings-page">
    <header class="header">
      <div>
        <h1>模型设置</h1>
        <p>配置你的 OpenAI 兼容模型 Key / Base URL / 模型名。</p>
      </div>
      <div class="actions" style="flex-direction: column; align-items: flex-end;">
        <label>
          API Base
          <input v-model="apiBase" @change="persistApiBase" placeholder="http://127.0.0.1:8000/api/v1" />
        </label>
        <div class="actions">
          <button class="ghost" @click="goChat">返回聊天</button>
          <button class="ghost" @click="goKnowledge">知识库</button>
          <button class="ghost" @click="logout">退出登录</button>
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
import { apiFetch, clearTokens, getApiBase, setApiBase } from '../api/client.js';
import CenterToast from '../components/CenterToast.vue';
import { useCenterToast } from '../composables/useCenterToast.js';

const router = useRouter();
const apiBase = ref(getApiBase());
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

const persistApiBase = () => {
  setApiBase(apiBase.value);
  setNotice('API Base 已更新');
};

const goChat = () => {
  router.push('/chat');
};

const goKnowledge = () => {
  router.push('/knowledge');
};

const logout = () => {
  clearTokens();
  router.push('/login');
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
  background: linear-gradient(135deg, #cdd7ff 0%, #eef2ff 45%, #f7eaff 100%);
  border-radius: 28px;
  overflow: auto;
  font-family: "Noto Sans SC", "Source Han Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
  color: #1f2a44;
}

.settings-page::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 12% 18%, rgba(111, 140, 255, 0.28), transparent 45%),
    radial-gradient(circle at 90% 8%, rgba(245, 189, 255, 0.35), transparent 40%),
    radial-gradient(circle at 80% 80%, rgba(169, 210, 255, 0.3), transparent 40%);
  pointer-events: none;
}

.settings-page > * {
  position: relative;
  z-index: 1;
}

.settings-page .header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.settings-page .header h1 {
  margin: 0;
  font-size: 26px;
}

.settings-page .header p {
  margin: 6px 0 0;
  color: #6a728d;
}

.settings-page .actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.settings-page label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: #5c647f;
}

.settings-page input {
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(111, 136, 255, 0.25);
  background: #fff;
  font-size: 13px;
}

.settings-page small {
  color: #7b839e;
}

.settings-page button {
  border: none;
  padding: 10px 16px;
  border-radius: 14px;
  background: linear-gradient(135deg, #6f88ff, #8d6bff);
  color: #fff;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 12px 22px rgba(108, 125, 255, 0.25);
}

.settings-page button.ghost {
  background: rgba(255, 255, 255, 0.9);
  color: #45507a;
  border: 1px solid rgba(111, 136, 255, 0.2);
  box-shadow: none;
}

.settings-page button.danger {
  color: #b04a63;
  border-color: rgba(255, 219, 230, 0.7);
}

.settings-page button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.settings-page .notice,
.settings-page .error {
  margin-top: 8px;
  border-radius: 12px;
  padding: 10px 14px;
  font-size: 13px;
}

.settings-page .notice {
  background: rgba(207, 234, 255, 0.6);
  color: #2c5a86;
}

.settings-page .error {
  background: rgba(255, 221, 228, 0.7);
  color: #a83c50;
}

.settings-page .card {
  background: rgba(255, 255, 255, 0.92);
  border-radius: 22px;
  padding: 18px;
  box-shadow: 0 22px 50px rgba(58, 72, 125, 0.16);
  border: 1px solid rgba(225, 231, 255, 0.9);
  backdrop-filter: blur(10px);
}

.settings-page .card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
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
