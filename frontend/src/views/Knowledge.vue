<template>
  <div class="page knowledge-page">
    <header class="header">
      <div>
        <h1>我的知识库</h1>
        <p>创建知识库、上传文档并管理内容。</p>
      </div>
      <div class="header-actions">
        <div class="actions action-bar">
          <button class="ghost" @click="goSettings">模型设置</button>
          <button class="ghost" @click="goChat">返回聊天</button>
          <button class="ghost" @click="goMy">我的</button>
          <button class="ghost" @click="logout">退出登录</button>
        </div>
      </div>
    </header>

    <div v-if="notice" class="notice">{{ notice }}</div>
    <div v-if="error" class="error">{{ error }}</div>

    <section class="card">
      <div class="actions" style="justify-content: space-between;">
        <h2>知识库管理</h2>
        <button class="ghost" @click="fetchKnowledgeBases">刷新列表</button>
      </div>
      <form class="actions" style="flex-direction: column;" @submit.prevent="createKnowledgeBase">
        <label>
          名称
          <input v-model="kbForm.name" required />
        </label>
        <label>
          描述
          <textarea v-model="kbForm.description" placeholder="可选"></textarea>
        </label>
        <button type="submit">创建知识库</button>
      </form>
      <div class="kb-grid">
        <div
          v-for="kb in knowledgeBases"
          :key="kb.id"
          class="kb-card"
          :class="{ active: activeKb && activeKb.id === kb.id }"
        >
          <button class="kb-select" @click="selectKnowledgeBase(kb)">
            <strong>{{ kb.name }}</strong>
            <span>#{{ kb.id }}</span>
          </button>
          <button class="kb-delete" @click.stop="deleteKnowledgeBase(kb.id)">删除</button>
        </div>
      </div>
    </section>

    <section class="card" v-if="activeKb">
      <div class="actions" style="justify-content: space-between;">
        <h2>知识库文件</h2>
        <button class="ghost" @click="fetchDocuments">刷新文件</button>
      </div>
      <div class="actions" style="flex-direction: column;">
        <label>
          上传文件到：{{ activeKb.name }}
          <input type="file" @change="onFileChange" />
        </label>
        <button @click="uploadDocument">上传文件</button>
      </div>
      <div v-if="lastUpload" class="notice">
        上传成功：{{ lastUpload.file_name }} (状态: {{ lastUpload.status }})
      </div>
      <div v-if="documents.items.length" class="doc-list">
        <div v-for="doc in documents.items" :key="doc.id" class="doc-item">
          <div>
            <strong>{{ doc.file_name }}</strong>
            <div class="doc-meta">
              <span class="status-pill" :class="`status-${doc.status}`">{{ formatDocStatus(doc.status) }}</span>
              <span v-if="doc.chunk_count">切片：{{ doc.processed_chunks || 0 }}/{{ doc.chunk_count }}</span>
              <span v-else>切片：{{ doc.processed_chunks || 0 }}</span>
            </div>
            <div v-if="doc.status === 'processing' || doc.status === 'uploading'" class="doc-progress">
              <div class="progress-bar" :class="{ indeterminate: !doc.chunk_count }">
                <div
                  class="progress-fill"
                  :style="{ width: `${getDocProgress(doc)}%` }"
                ></div>
              </div>
              <span class="progress-text">{{ getProgressText(doc) }}</span>
            </div>
            <div v-if="doc.status === 'failed' && doc.error_msg" class="doc-error">
              失败原因：{{ doc.error_msg }}
            </div>
          </div>
          <div class="doc-actions">
            <span class="doc-time">{{ formatTime(doc.created_at) }}</span>
            <button
              v-if="doc.status === 'failed' || doc.status === 'completed'"
              class="ghost doc-retry"
              @click="reindexDocument(doc)"
            >
              {{ doc.status === 'failed' ? '重试' : '重建索引' }}
            </button>
            <button class="doc-delete" @click="deleteDocument(doc)">删除</button>
          </div>
        </div>
      </div>
      <div v-else class="placeholder">该知识库暂无文档。</div>
    </section>

    <CenterToast :message="successMessage" />
  </div>
</template>

<script setup>
import { ref, onBeforeUnmount } from 'vue';
import { useRouter } from 'vue-router';
import { apiFetch, clearTokens } from '../api/client.js';
import CenterToast from '../components/CenterToast.vue';
import { useCenterToast } from '../composables/useCenterToast.js';

const router = useRouter();
const notice = ref('');
const error = ref('');
const { message: successMessage, show: showSuccess } = useCenterToast();

const knowledgeBases = ref([]);
const kbForm = ref({ name: '', description: '' });
const uploadForm = ref({ file: null });
const lastUpload = ref(null);
const activeKb = ref(null);
const documents = ref({ items: [] });
let documentPollTimer = null;

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

const goSettings = () => {
  router.push('/settings');
};

const goMy = () => {
  router.push('/my');
};

const logout = () => {
  clearTokens();
  router.push('/login');
};

const fetchKnowledgeBases = async () => {
  try {
    const data = await apiFetch('/knowledge/list');
    knowledgeBases.value = data || [];
    if (!activeKb.value && knowledgeBases.value.length) {
      selectKnowledgeBase(knowledgeBases.value[0]);
    }
  } catch (err) {
    setError(`获取知识库失败：${err.message}`);
  }
};

const createKnowledgeBase = async () => {
  try {
    const data = await apiFetch('/knowledge/create', {
      method: 'POST',
      body: kbForm.value,
    });
    knowledgeBases.value.unshift(data);
    kbForm.value = { name: '', description: '' };
    setNotice('知识库创建成功');
  } catch (err) {
    setError(`创建知识库失败：${err.message}`);
  }
};

const onFileChange = (event) => {
  uploadForm.value.file = event.target.files[0];
};

const uploadDocument = async () => {
  if (!activeKb.value || !uploadForm.value.file) {
    setError('请选择知识库和文件');
    return;
  }
  try {
    const formData = new FormData();
    formData.append('file', uploadForm.value.file);
    const data = await apiFetch(`/knowledge/${activeKb.value.id}/upload`, {
      method: 'POST',
      body: formData,
    });
    lastUpload.value = data;
    uploadForm.value.file = null;
    setNotice('文件上传成功，正在后台处理。');
    await fetchDocuments();
  } catch (err) {
    setError(`上传失败：${err.message}`);
  }
};

const selectKnowledgeBase = async (kb) => {
  activeKb.value = kb;
  documents.value.items = [];
  await fetchDocuments();
};

const deleteKnowledgeBase = async (kbId) => {
  const confirmed = window.confirm('您确定要删除吗？');
  if (!confirmed) return;
  try {
    await apiFetch(`/knowledge/${kbId}`, { method: 'DELETE' });
    knowledgeBases.value = knowledgeBases.value.filter((kb) => kb.id !== kbId);
    if (activeKb.value && activeKb.value.id === kbId) {
      activeKb.value = knowledgeBases.value[0] || null;
      documents.value.items = [];
      if (activeKb.value) {
        await fetchDocuments();
      }
    }
    updateDocumentPolling();
  } catch (err) {
    setError(`删除知识库失败：${err.message}`);
  }
};

const hasProcessingDocs = () =>
  (documents.value.items || []).some((doc) =>
    ['processing', 'uploading'].includes(doc.status),
  );

const startDocumentPolling = () => {
  if (documentPollTimer) return;
  documentPollTimer = setInterval(() => {
    fetchDocuments({ silent: true });
  }, 3000);
};

const stopDocumentPolling = () => {
  if (!documentPollTimer) return;
  clearInterval(documentPollTimer);
  documentPollTimer = null;
};

const updateDocumentPolling = () => {
  if (hasProcessingDocs()) {
    startDocumentPolling();
  } else {
    stopDocumentPolling();
  }
};

const fetchDocuments = async ({ silent = false } = {}) => {
  if (!activeKb.value) {
    if (!silent) setError('请选择知识库');
    return;
  }
  try {
    const data = await apiFetch(`/knowledge/${activeKb.value.id}/documents`);
    documents.value.items = data || [];
    updateDocumentPolling();
  } catch (err) {
    if (!silent) {
      setError(`获取文档失败：${err.message}`);
    }
  }
};

const deleteDocument = async (doc) => {
  if (!activeKb.value) return;
  const confirmed = window.confirm(`确定删除文档「${doc.file_name}」吗？`);
  if (!confirmed) return;
  try {
    await apiFetch(`/knowledge/${activeKb.value.id}/documents/${doc.id}`, { method: 'DELETE' });
    documents.value.items = documents.value.items.filter((item) => item.id !== doc.id);
    setNotice('文档删除成功');
    updateDocumentPolling();
  } catch (err) {
    setError(`删除文档失败：${err.message}`);
  }
};

const formatTime = (time) => {
  if (!time) return '';
  return new Date(time).toLocaleString();
};

const STATUS_LABELS = {
  uploading: '上传中',
  processing: '处理中',
  completed: '已完成',
  failed: '失败',
};

const formatDocStatus = (status) => STATUS_LABELS[status] || status || '未知';

const getDocProgress = (doc) => {
  if (!doc) return 0;
  const total = Number(doc.chunk_count || 0);
  const processed = Number(doc.processed_chunks || 0);
  if (!total) return 40;
  const ratio = Math.min(1, Math.max(0, processed / total));
  return Math.round(ratio * 100);
};

const getProgressText = (doc) => {
  if (!doc) return '';
  if (doc.chunk_count) return `进度 ${getDocProgress(doc)}%`;
  return '处理中...';
};

const reindexDocument = async (doc) => {
  if (!doc || !doc.id) return;
  if (doc.status === 'processing' || doc.status === 'uploading') {
    setError('文档正在处理中，请稍后再试');
    return;
  }
  const confirmed = window.confirm(`确定要重建索引「${doc.file_name}」吗？`);
  if (!confirmed) return;
  try {
    await apiFetch(`/knowledge/documents/${doc.id}/reindex`, { method: 'POST' });
    setNotice('已提交重建任务，稍后会自动更新状态。');
    await fetchDocuments({ silent: true });
  } catch (err) {
    setError(`重建失败：${err.message}`);
  }
};

fetchKnowledgeBases();
onBeforeUnmount(() => {
  stopDocumentPolling();
});
</script>

<style scoped>
.knowledge-page {
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

.knowledge-page::before {
  content: none;
  display: none;
}

.knowledge-page > * {
  position: relative;
  z-index: 1;
}

.knowledge-page .header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.knowledge-page .header h1 {
  margin: 0;
  font-size: 26px;
}

.knowledge-page .header p {
  margin: 6px 0 0;
  color: var(--text-muted);
}

.knowledge-page .actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.knowledge-page label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
}

.knowledge-page input,
.knowledge-page textarea,
.knowledge-page select {
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface-soft);
  font-size: 13px;
}

.knowledge-page button {
  border: none;
  padding: 10px 16px;
  border-radius: var(--radius-sm);
  background: var(--accent-gradient);
  color: #fff;
  font-weight: 600;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
}

.knowledge-page button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.knowledge-page button.ghost {
  background: rgba(255, 255, 255, 0.7);
  color: var(--accent-strong);
  border: 1px solid rgba(59, 130, 246, 0.25);
  box-shadow: none;
}

.knowledge-page .notice,
.knowledge-page .error {
  margin-top: 8px;
  border-radius: 12px;
  padding: 10px 14px;
  font-size: 13px;
}

.knowledge-page .notice {
  background: var(--notice-bg);
  color: var(--notice-text);
}

.knowledge-page .error {
  background: var(--error-bg);
  color: var(--error-text);
}

.knowledge-page .card {
  background: var(--surface-strong);
  border-radius: var(--radius-lg);
  padding: 18px;
  box-shadow: var(--shadow-md);
  border: 1px solid var(--border);
  backdrop-filter: blur(10px);
}

.knowledge-page .kb-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.knowledge-page .kb-card {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(246, 248, 255, 0.9);
  border-radius: 16px;
  padding: 10px 12px;
  border: 1px solid rgba(111, 136, 255, 0.15);
}

.knowledge-page .kb-card.active {
  background: rgba(111, 136, 255, 0.15);
  border-color: rgba(111, 136, 255, 0.35);
}

.knowledge-page .kb-select {
  flex: 1;
  background: transparent;
  color: inherit;
  text-align: left;
  box-shadow: none;
  padding: 6px 0;
}

.knowledge-page .kb-delete {
  background: rgba(255, 219, 230, 0.7);
  color: #b04a63;
  padding: 6px 10px;
  border-radius: 999px;
  box-shadow: none;
}

.knowledge-page .doc-list {
  display: grid;
  gap: 10px;
}

.knowledge-page .doc-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #fff;
  border-radius: 14px;
  padding: 12px 14px;
  box-shadow: 0 12px 24px rgba(58, 72, 125, 0.08);
}

.knowledge-page .doc-meta {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: #6b7390;
  margin-top: 6px;
  align-items: center;
}

.knowledge-page .doc-time {
  font-size: 12px;
  color: #8b93ab;
}

.knowledge-page .doc-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.knowledge-page .status-pill {
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 600;
  font-size: 11px;
  background: rgba(148, 163, 184, 0.2);
  color: #475569;
}

.knowledge-page .status-pill.status-processing,
.knowledge-page .status-pill.status-uploading {
  background: rgba(59, 130, 246, 0.18);
  color: #1d4ed8;
}

.knowledge-page .status-pill.status-completed {
  background: rgba(34, 197, 94, 0.18);
  color: #15803d;
}

.knowledge-page .status-pill.status-failed {
  background: rgba(239, 68, 68, 0.18);
  color: #b91c1c;
}

.knowledge-page .doc-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 6px;
  font-size: 12px;
  color: #6b7390;
}

.knowledge-page .progress-bar {
  flex: 1;
  height: 6px;
  border-radius: 999px;
  background: rgba(99, 102, 241, 0.18);
  overflow: hidden;
  position: relative;
}

.knowledge-page .progress-fill {
  height: 100%;
  width: 0%;
  background: linear-gradient(90deg, #6366f1, #8b5cf6);
  transition: width 0.4s ease;
}

.knowledge-page .progress-bar.indeterminate .progress-fill {
  width: 40%;
  position: absolute;
  animation: progress-move 1.2s ease-in-out infinite;
}

.knowledge-page .doc-error {
  margin-top: 6px;
  font-size: 12px;
  color: var(--error-text);
  background: var(--error-bg);
  padding: 6px 8px;
  border-radius: var(--radius-sm);
}

.knowledge-page .doc-retry {
  font-size: 12px;
  padding: 6px 10px;
}

@keyframes progress-move {
  0% {
    left: -40%;
  }
  100% {
    left: 100%;
  }
}

.knowledge-page .doc-delete {
  padding: 6px 10px;
  border-radius: 999px;
  background: rgba(255, 219, 230, 0.7);
  color: #b04a63;
  box-shadow: none;
}

.knowledge-page .placeholder {
  text-align: center;
  padding: 20px 0;
  color: #7b839e;
}

@media (max-width: 1080px) {
  .knowledge-page {
    width: 100%;
    height: auto;
    max-height: none;
    margin: 16px auto;
  }

  .knowledge-page .header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
