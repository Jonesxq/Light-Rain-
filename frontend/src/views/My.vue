<template>
  <div class="page my-page">
    <header class="header">
      <div>
        <h1>我的界面</h1>
        <p>管理你的外观与偏好设置。</p>
      </div>
      <div class="header-actions">
        <div class="actions action-bar">
          <button class="ghost" @click="goChat">返回聊天</button>
        </div>
      </div>
    </header>

    <div v-if="notice" class="notice">{{ notice }}</div>
    <div v-if="error" class="error">{{ error }}</div>

    <section class="card avatar-card">
      <div class="card-head">
        <h2>头像设置</h2>
        <span class="hint">全站生效</span>
      </div>
      <div class="avatar-grid">
        <div class="avatar-item">
          <div class="avatar-title">助手头像</div>
          <div class="avatar-preview" :style="avatarStyle(assistantAvatar)">
            <span v-if="!assistantAvatar" class="avatar-placeholder">助手</span>
          </div>
          <div class="avatar-actions">
            <button class="ghost" type="button" @click="triggerUpload('assistant')">上传头像</button>
            <button class="ghost" type="button" @click="clearAvatar('assistant')">恢复默认</button>
          </div>
          <input
            ref="assistantInputRef"
            class="file-input"
            type="file"
            accept="image/*"
            @change="handleAvatarUpload('assistant', $event)"
          />
        </div>
        <div class="avatar-item">
          <div class="avatar-title">我的头像</div>
          <div class="avatar-preview" :style="avatarStyle(userAvatar)">
            <span v-if="!userAvatar" class="avatar-placeholder">我</span>
          </div>
          <div class="avatar-actions">
            <button class="ghost" type="button" @click="triggerUpload('user')">上传头像</button>
            <button class="ghost" type="button" @click="clearAvatar('user')">恢复默认</button>
          </div>
          <input
            ref="userInputRef"
            class="file-input"
            type="file"
            accept="image/*"
            @change="handleAvatarUpload('user', $event)"
          />
        </div>
      </div>
      <div class="avatar-hint">支持 JPG/PNG，建议不超过 1MB。</div>
    </section>

    <CenterToast :message="successMessage" />
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import CenterToast from '../components/CenterToast.vue';
import { useCenterToast } from '../composables/useCenterToast.js';

const router = useRouter();
const notice = ref('');
const error = ref('');
const { message: successMessage, show: showSuccess } = useCenterToast();

const assistantAvatar = ref('');
const userAvatar = ref('');
const assistantInputRef = ref(null);
const userInputRef = ref(null);
const MAX_AVATAR_SIZE = 1024 * 1024;

const setNotice = (message) => {
  showSuccess(message);
  notice.value = '';
  error.value = '';
};

const setError = (message) => {
  error.value = message;
  notice.value = '';
};

const applyAvatar = (role, dataUrl) => {
  const key = role === 'assistant' ? 'chatAssistantAvatar' : 'chatUserAvatar';
  const cssVar = role === 'assistant' ? '--chat-assistant-avatar-image' : '--chat-user-avatar-image';
  if (dataUrl) {
    localStorage.setItem(key, dataUrl);
    document.documentElement.style.setProperty(cssVar, `url("${dataUrl}")`);
  } else {
    localStorage.removeItem(key);
    document.documentElement.style.removeProperty(cssVar);
  }
};

const avatarStyle = (dataUrl) => {
  if (!dataUrl) return {};
  return {
    backgroundImage: `url("${dataUrl}")`,
  };
};

const triggerUpload = (role) => {
  if (role === 'assistant' && assistantInputRef.value) {
    assistantInputRef.value.click();
  }
  if (role === 'user' && userInputRef.value) {
    userInputRef.value.click();
  }
};

const handleAvatarUpload = (role, event) => {
  const file = event?.target?.files?.[0];
  if (!file) return;
  if (!file.type.startsWith('image/')) {
    setError('请选择图片文件');
    return;
  }
  if (file.size > MAX_AVATAR_SIZE) {
    setError('图片过大，请选择 1MB 以内的图片');
    return;
  }
  const reader = new FileReader();
  reader.onload = () => {
    const dataUrl = String(reader.result || '');
    if (role === 'assistant') {
      assistantAvatar.value = dataUrl;
    } else {
      userAvatar.value = dataUrl;
    }
    applyAvatar(role, dataUrl);
    setNotice('头像已更新');
  };
  reader.onerror = () => setError('读取图片失败');
  reader.readAsDataURL(file);
};

const clearAvatar = (role) => {
  if (role === 'assistant') {
    assistantAvatar.value = '';
  } else {
    userAvatar.value = '';
  }
  applyAvatar(role, '');
  setNotice('已恢复默认头像');
};

const goChat = () => router.push('/chat');

onMounted(() => {
  const assistantSaved = localStorage.getItem('chatAssistantAvatar') || '';
  const userSaved = localStorage.getItem('chatUserAvatar') || '';
  assistantAvatar.value = assistantSaved;
  userAvatar.value = userSaved;
  applyAvatar('assistant', assistantSaved);
  applyAvatar('user', userSaved);
});
</script>

<style scoped>
.my-page {
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

.my-page::before {
  content: none;
  display: none;
}

.my-page > * {
  position: relative;
  z-index: 1;
}

.avatar-card {
  gap: 16px;
}

.avatar-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 16px;
}

.avatar-item {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid var(--border);
  background: var(--surface-soft);
}

.avatar-title {
  font-weight: 600;
  color: var(--text-strong);
}

.avatar-preview {
  width: 96px;
  height: 96px;
  border-radius: 50%;
  background: rgba(148, 163, 184, 0.18);
  border: 1px solid rgba(148, 163, 184, 0.35);
  display: grid;
  place-items: center;
  background-size: cover;
  background-position: center;
}

.avatar-placeholder {
  font-size: 12px;
  color: var(--text-soft);
}

.avatar-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.avatar-hint {
  font-size: 12px;
  color: var(--text-soft);
}

.file-input {
  display: none;
}

@media (max-width: 1080px) {
  .my-page {
    width: 100%;
    height: auto;
    max-height: none;
    margin: 16px auto;
  }

  .my-page .header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
