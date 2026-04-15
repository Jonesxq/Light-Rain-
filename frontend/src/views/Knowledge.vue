<template>
  <main class="knowledge-page">
    <div class="knowledge-shell">
      <div class="top-actions">
        <button class="back-chat-btn" type="button" @click="goChat">返回聊天</button>
      </div>

      <div v-if="error" class="banner banner-error">{{ error }}</div>

      <div class="knowledge-grid">
        <section class="panel create-panel">
          <h2 class="title-create">新建知识库</h2>
          <form class="kb-form" @submit.prevent="createKnowledgeBase">
            <label class="field">
              <span>名称</span>
              <input v-model="kbForm.name" placeholder="输入知识库名称..." required />
            </label>
            <label class="field">
              <span>描述</span>
              <textarea
                v-model="kbForm.description"
                placeholder="描述该知识库的用途或范围..."
                rows="4"
              ></textarea>
            </label>
            <button class="create-btn" type="submit" :disabled="!kbForm.name.trim()">
              创建知识库
            </button>
          </form>
        </section>

        <section class="panel files-panel">
          <div class="panel-head">
            <h2 class="title-section">知识库文件</h2>
            <button
              class="icon-ghost"
              type="button"
              title="刷新文件"
              @click="activeKb ? fetchDocuments() : fetchKnowledgeBases()"
            >
              <span class="material-symbols-outlined" aria-hidden="true">filter_list</span>
            </button>
          </div>

          <div
            class="upload-dropzone"
            :class="{ active: dropzoneActive, disabled: !activeKb || uploading }"
            @click="activeKb && !uploading && triggerFileSelect()"
            @dragover.prevent="handleDropZoneDragOver"
            @dragleave.prevent="handleDropZoneDragLeave"
            @drop.prevent="handleDropZoneFile"
          >
            <input
              ref="fileInputRef"
              class="file-input"
              type="file"
              accept=".pdf,.docx,.txt"
              @change="onFileChange"
            />
            <div class="upload-circle">
              <span class="material-symbols-outlined" aria-hidden="true">upload</span>
            </div>
            <p class="upload-title">
              {{ activeKb ? (uploading ? '上传中...' : '上传文件') : '请先选择知识库' }}
            </p>
            <p class="upload-desc">拖拽文件到此处，或点击浏览。支持 PDF, DOCX, TXT</p>
          </div>

          <h4 class="recent-title">最近上传</h4>

          <div v-if="activeKb && documents.items.length" class="doc-list">
            <article v-for="doc in documents.items" :key="doc.id" class="doc-row">
              <div class="doc-main">
                <span class="doc-icon" :class="getFileToneClass(doc)">
                  <span class="material-symbols-outlined" aria-hidden="true">{{ getFileIcon(doc) }}</span>
                </span>
                <div class="doc-copy">
                  <p class="doc-name">{{ doc.file_name }}</p>
                  <p class="doc-meta">{{ formatDocMeta(doc) }}</p>
                  <p v-if="doc.status !== 'completed'" class="doc-status">
                    {{ formatDocStatus(doc.status) }}
                    <span v-if="doc.status === 'processing' || doc.status === 'uploading'">
                      · {{ getProgressText(doc) }}
                    </span>
                  </p>
                  <div
                    v-if="doc.status === 'processing' || doc.status === 'uploading'"
                    class="progress-bar"
                    :class="{ indeterminate: !doc.chunk_count }"
                  >
                    <div class="progress-fill" :style="{ width: `${getDocProgress(doc)}%` }"></div>
                  </div>
                  <p v-if="doc.status === 'failed' && doc.error_msg" class="doc-error">
                    失败原因：{{ doc.error_msg }}
                  </p>
                </div>
              </div>

              <div class="doc-actions">
                <span class="chunk-pill">{{ formatChunkCount(doc) }}</span>
                <details class="doc-menu" @toggle="handleDocMenuToggle">
                  <summary aria-label="文档菜单">
                    <span class="material-symbols-outlined" aria-hidden="true">more_vert</span>
                  </summary>
                  <div class="doc-menu-card">
                    <button type="button" class="doc-menu-item danger" @click.stop.prevent="deleteDocument(doc)">
                      删除
                    </button>
                  </div>
                </details>
              </div>
            </article>
          </div>

          <div v-else-if="activeKb" class="empty-block">该知识库暂无文档。</div>
          <div v-else class="empty-block">请选择左侧知识库后查看文档。</div>
        </section>

        <section class="panel list-panel">
          <div class="panel-head list-head">
            <h2 class="title-section">已有知识库</h2>
            <span class="count-chip">{{ knowledgeBases.length }} 个项目</span>
          </div>

          <div v-if="!knowledgeBases.length" class="empty-block">暂无知识库，请先创建。</div>

          <div v-else class="kb-list">
            <article
              v-for="(kb, index) in knowledgeBases"
              :key="kb.id"
              class="kb-row"
              :class="{ active: activeKb && activeKb.id === kb.id }"
            >
              <button class="kb-select" type="button" @click="selectKnowledgeBase(kb)">
                <span class="kb-icon" :class="getKbToneClass(index)">
                  <span class="material-symbols-outlined" aria-hidden="true">{{ getKbIcon(index) }}</span>
                </span>
                <span class="kb-copy">
                  <span class="kb-name">{{ kb.name }}</span>
                  <span class="kb-meta">{{ formatKbMeta(kb) }}</span>
                </span>
              </button>
              <button class="kb-delete" type="button" @click.stop="deleteKnowledgeBase(kb.id)">删除</button>
            </article>
          </div>
        </section>
      </div>
    </div>

    <button class="help-fab" type="button" aria-label="帮助">
      <span class="material-symbols-outlined" aria-hidden="true">help_outline</span>
    </button>
  </main>

  <CenterToast :message="successMessage" />
</template>

<script setup>
import { ref, onBeforeUnmount, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { apiFetch } from '../api/client.js';
import CenterToast from '../components/CenterToast.vue';
import { useCenterToast } from '../composables/useCenterToast.js';

const router = useRouter();
const error = ref('');
const { message: successMessage, show: showSuccess } = useCenterToast();

const knowledgeBases = ref([]);
const kbForm = ref({ name: '', description: '' });
const activeKb = ref(null);
const documents = ref({ items: [] });
const uploadForm = ref({ file: null });
const dropzoneActive = ref(false);
const uploading = ref(false);
const fileInputRef = ref(null);
let documentPollTimer = null;

const setNotice = (message) => {
  showSuccess(message);
  error.value = '';
};

const setError = (message) => {
  error.value = message;
};

const goChat = () => {
  router.push('/chat');
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
    documents.value.items = [];
    if (!silent) setError('请选择知识库');
    return;
  }
  try {
    const data = await apiFetch(`/knowledge/${activeKb.value.id}/documents`);
    documents.value.items = (data || []).sort(
      (a, b) => new Date(b.created_at) - new Date(a.created_at),
    );
    updateDocumentPolling();
  } catch (err) {
    if (!silent) setError(`获取文档失败：${err.message}`);
  }
};

const fetchKnowledgeBases = async ({ preferKbId = null } = {}) => {
  try {
    const data = await apiFetch('/knowledge/list');
    knowledgeBases.value = data || [];
    if (!knowledgeBases.value.length) {
      activeKb.value = null;
      documents.value.items = [];
      stopDocumentPolling();
      return;
    }

    const currentId = preferKbId ?? activeKb.value?.id;
    const nextKb =
      knowledgeBases.value.find((item) => item.id === currentId) || knowledgeBases.value[0];
    const changed = !activeKb.value || activeKb.value.id !== nextKb.id;
    activeKb.value = nextKb;

    if (changed || !documents.value.items.length) {
      await fetchDocuments({ silent: true });
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
    kbForm.value = { name: '', description: '' };
    setNotice('知识库创建成功');
    await fetchKnowledgeBases({ preferKbId: data.id });
  } catch (err) {
    setError(`创建知识库失败：${err.message}`);
  }
};

const selectKnowledgeBase = async (kb) => {
  if (activeKb.value?.id === kb.id) return;
  activeKb.value = kb;
  documents.value.items = [];
  await fetchDocuments({ silent: true });
};

const deleteKnowledgeBase = async (kbId) => {
  const confirmed = window.confirm('您确定要删除吗？');
  if (!confirmed) return;
  try {
    await apiFetch(`/knowledge/${kbId}`, { method: 'DELETE' });
    setNotice('知识库删除成功');
    const preferKbId = activeKb.value?.id === kbId ? null : activeKb.value?.id;
    await fetchKnowledgeBases({ preferKbId });
  } catch (err) {
    setError(`删除知识库失败：${err.message}`);
  }
};

const triggerFileSelect = () => {
  fileInputRef.value?.click();
};

const uploadSelectedFile = async (file) => {
  if (!file) return;
  if (uploading.value) return;
  if (!activeKb.value) {
    setError('请先选择知识库');
    return;
  }

  uploadForm.value.file = file;
  uploading.value = true;
  try {
    const formData = new FormData();
    formData.append('file', file);
    await apiFetch(`/knowledge/${activeKb.value.id}/upload`, {
      method: 'POST',
      body: formData,
    });
    uploadForm.value.file = null;
    setNotice('文件上传成功，正在后台处理。');
    await Promise.all([
      fetchDocuments({ silent: true }),
      fetchKnowledgeBases({ preferKbId: activeKb.value.id }),
    ]);
  } catch (err) {
    setError(`上传失败：${err.message}`);
  } finally {
    uploading.value = false;
    if (fileInputRef.value) fileInputRef.value.value = '';
  }
};

const onFileChange = async (event) => {
  const file = event?.target?.files?.[0];
  await uploadSelectedFile(file);
};

const handleDropZoneDragOver = () => {
  if (!activeKb.value || uploading.value) return;
  dropzoneActive.value = true;
};

const handleDropZoneDragLeave = () => {
  dropzoneActive.value = false;
};

const handleDropZoneFile = async (event) => {
  dropzoneActive.value = false;
  if (!activeKb.value || uploading.value) return;
  const file = event?.dataTransfer?.files?.[0];
  await uploadSelectedFile(file);
};

const deleteDocument = async (doc) => {
  if (!activeKb.value) return;
  const confirmed = window.confirm(`确定删除文档「${doc.file_name}」吗？`);
  if (!confirmed) return;
  try {
    await apiFetch(`/knowledge/${activeKb.value.id}/documents/${doc.id}`, { method: 'DELETE' });
    documents.value.items = documents.value.items.filter((item) => item.id !== doc.id);
    setNotice('文档删除成功');
    await fetchKnowledgeBases({ preferKbId: activeKb.value.id });
    updateDocumentPolling();
  } catch (err) {
    setError(`删除文档失败：${err.message}`);
  }
};

const handleDocMenuToggle = (event) => {
  const current = event?.target;
  if (!current?.open) return;
  document.querySelectorAll('.doc-menu[open]').forEach((node) => {
    if (node !== current) node.removeAttribute('open');
  });
};

const formatDocStatus = (status) => {
  const labels = {
    uploading: '上传中',
    processing: '处理中',
    completed: '已完成',
    failed: '失败',
  };
  return labels[status] || status || '未知';
};

const getDocProgress = (doc) => {
  const total = Number(doc?.chunk_count || 0);
  const processed = Number(doc?.processed_chunks || 0);
  if (!total) return 40;
  return Math.round(Math.min(1, Math.max(0, processed / total)) * 100);
};

const getProgressText = (doc) => {
  if (!doc) return '';
  if (doc.chunk_count) return `${getDocProgress(doc)}%`;
  return '处理中...';
};

const formatRelativeTime = (time) => {
  if (!time) return '';
  const ts = new Date(time).getTime();
  if (Number.isNaN(ts)) return '';
  const delta = Math.max(0, Date.now() - ts);
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (delta < minute) return '刚刚';
  if (delta < hour) return `${Math.floor(delta / minute)} 分钟前`;
  if (delta < day) return `${Math.floor(delta / hour)} 小时前`;
  if (delta < day * 2) return '昨天';
  if (delta < day * 7) return `${Math.floor(delta / day)} 天前`;
  if (delta < day * 30) return `${Math.floor(delta / (day * 7))} 周前`;
  if (delta < day * 365) return `${Math.floor(delta / (day * 30))} 个月前`;
  return `${Math.floor(delta / (day * 365))} 年前`;
};

const formatFileSize = (bytes) => {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) return '0 B';
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${Math.round(value / 1024)} KB`;
  if (value < 1024 * 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(1)} MB`;
  return `${(value / (1024 * 1024 * 1024)).toFixed(1)} GB`;
};

const formatKbMeta = (kb) =>
  `创建于 ${formatRelativeTime(kb.created_at)} · ${Number(kb.doc_count || 0)} 个文件`;

const formatDocMeta = (doc) =>
  `${formatFileSize(doc.file_size)} · ${formatRelativeTime(doc.created_at)}`;

const formatChunkCount = (doc) => `${Math.max(0, Number(doc?.chunk_count || 0))} 切块`;

const extractExt = (doc) => {
  const direct = String(doc?.file_type || '').toLowerCase();
  if (direct) return direct.startsWith('.') ? direct : `.${direct}`;
  const name = String(doc?.file_name || '').toLowerCase();
  const idx = name.lastIndexOf('.');
  return idx >= 0 ? name.slice(idx) : '';
};

const getFileIcon = (doc) => {
  const ext = extractExt(doc);
  if (ext === '.pdf') return 'picture_as_pdf';
  if (ext === '.doc' || ext === '.docx') return 'description';
  if (ext === '.txt') return 'article';
  return 'insert_drive_file';
};

const getFileToneClass = (doc) => {
  const ext = extractExt(doc);
  if (ext === '.pdf') return 'tone-pdf';
  if (ext === '.doc' || ext === '.docx') return 'tone-doc';
  if (ext === '.txt') return 'tone-text';
  return 'tone-default';
};

const getKbToneClass = (index) => ['tone-doc', 'tone-pdf', 'tone-text'][index % 3];
const getKbIcon = (index) => ['book', 'code', 'analytics'][index % 3];

onMounted(() => {
  fetchKnowledgeBases();
});

onBeforeUnmount(() => {
  stopDocumentPolling();
});
</script>

<style scoped>
@import url("https://fonts.googleapis.com/css2?family=Manrope:wght@700;800&family=Inter:wght@400;500;600;700&family=Noto+Sans+SC:wght@400;500;700&display=swap");
@import url("https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap");

.knowledge-page {
  min-height: 100vh;
  background: #f7f9fb;
  color: #191c1e;
  font-family: "Inter", "Noto Sans SC", sans-serif;
}

.knowledge-page .material-symbols-outlined {
  font-family: "Material Symbols Outlined";
  font-variation-settings: "FILL" 0, "wght" 420, "GRAD" 0, "opsz" 24;
}

.knowledge-shell {
  width: 100%;
  max-width: 80rem;
  margin: 0 auto;
  padding: 1rem 1rem 2.5rem;
}

.top-actions {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 1rem;
}

.back-chat-btn {
  border: 1px solid rgba(148, 163, 184, 0.35);
  border-radius: 0.875rem;
  padding: 0.52rem 0.95rem;
  background: #fff;
  color: #1d4ed8;
  font-size: 0.875rem;
  font-weight: 700;
  line-height: 1;
  cursor: pointer;
  transition: all 300ms ease-out;
}

.back-chat-btn:hover {
  border-color: rgba(37, 99, 235, 0.3);
  background: #eff6ff;
}

.knowledge-grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 2rem;
}

.panel {
  background: #fff;
  border-radius: 1rem;
  border: 1px solid rgba(148, 163, 184, 0.12);
  box-shadow: 0 4px 18px rgba(15, 23, 42, 0.04);
}

.create-panel {
  grid-column: span 7 / span 7;
  padding: 2rem;
}

.files-panel {
  grid-column: span 5 / span 5;
  grid-row: span 2 / span 2;
  padding: 2rem;
  display: flex;
  flex-direction: column;
  min-height: 100%;
}

.list-panel {
  grid-column: span 7 / span 7;
  padding: 0;
  overflow: hidden;
}

.title-create,
.title-section {
  margin: 0;
  color: #0f172a;
  font-family: "Manrope", "Inter", "Noto Sans SC", sans-serif;
  letter-spacing: -0.02em;
}

.title-create {
  margin-bottom: 2rem;
  font-size: 1.5rem;
  font-weight: 800;
}

.title-section {
  font-size: 1.25rem;
  font-weight: 800;
}

.kb-form {
  display: grid;
  gap: 1.5rem;
}

.field {
  display: grid;
  gap: 0.5rem;
}

.field span {
  font-size: 0.875rem;
  font-weight: 600;
  color: #424752;
}

.field input,
.field textarea {
  width: 100%;
  border: none;
  border-radius: 0.75rem;
  background: #f2f4f6;
  color: #191c1e;
  font-size: 1rem;
  font-family: inherit;
  padding: 1rem;
  outline: none;
  transition: box-shadow 300ms ease-out;
}

.field input:focus,
.field textarea:focus {
  box-shadow: 0 0 0 2px rgba(0, 63, 171, 0.2);
}

.field textarea {
  resize: vertical;
  min-height: 9rem;
}

.create-btn {
  border: none;
  border-radius: 999px;
  padding: 0.95rem 2.5rem;
  width: fit-content;
  font-size: 1rem;
  font-weight: 700;
  font-family: "Manrope", "Inter", "Noto Sans SC", sans-serif;
  color: #fff;
  background: linear-gradient(135deg, #003fab 0%, #0354dd 100%);
  box-shadow: 0 14px 30px rgba(0, 63, 171, 0.22);
  cursor: pointer;
  transition: transform 300ms ease-out, box-shadow 300ms ease-out, opacity 300ms ease-out;
}

.create-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 18px 30px rgba(0, 63, 171, 0.24);
}

.create-btn:disabled {
  opacity: 0.55;
  box-shadow: none;
  cursor: not-allowed;
  transform: none;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 2rem;
}

.icon-ghost {
  width: 2rem;
  height: 2rem;
  border: none;
  border-radius: 0.5rem;
  background: transparent;
  color: #94a3b8;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: color 300ms ease-out, background-color 300ms ease-out;
}

.icon-ghost:hover {
  color: #003fab;
  background: #f2f4f6;
}

.upload-dropzone {
  border: 2px dashed rgba(194, 198, 212, 0.8);
  border-radius: 1rem;
  padding: 2rem;
  margin-bottom: 2rem;
  background: rgba(248, 250, 252, 0.45);
  cursor: pointer;
  transition: border-color 300ms ease-out, background-color 300ms ease-out;
}

.upload-dropzone:hover {
  border-color: rgba(0, 63, 171, 0.28);
  background: rgba(239, 246, 255, 0.6);
}

.upload-dropzone.active {
  border-color: rgba(0, 63, 171, 0.5);
  background: rgba(219, 234, 254, 0.35);
}

.upload-dropzone.disabled {
  cursor: not-allowed;
  opacity: 0.68;
}

.upload-circle {
  width: 4rem;
  height: 4rem;
  border-radius: 999px;
  margin: 0 auto 1rem;
  background: #fff;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.08);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.upload-circle .material-symbols-outlined {
  font-size: 2rem;
  color: #003fab;
}

.upload-title {
  margin: 0 0 0.25rem;
  text-align: center;
  font-size: 1rem;
  font-weight: 700;
  font-family: "Manrope", "Inter", "Noto Sans SC", sans-serif;
  color: #0f172a;
}

.upload-desc {
  margin: 0;
  text-align: center;
  color: #64748b;
  font-size: 0.6875rem;
  line-height: 1.6;
}

.file-input {
  display: none;
}

.recent-title {
  margin: 0 0 0.75rem;
  font-size: 0.6875rem;
  font-weight: 700;
  color: #94a3b8;
  letter-spacing: 0.12em;
  text-transform: uppercase;
}

.doc-list {
  display: grid;
  gap: 0.5rem;
}

.doc-row {
  position: relative;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
  border-radius: 0.75rem;
  padding: 0.75rem;
  transition: background-color 300ms ease-out;
}

.doc-row:hover {
  background: rgba(248, 250, 252, 0.8);
}

.doc-main {
  min-width: 0;
  display: flex;
  gap: 0.75rem;
}

.doc-icon {
  width: 2.5rem;
  height: 2.5rem;
  border-radius: 0.5rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.doc-icon .material-symbols-outlined {
  font-size: 1.25rem;
}

.doc-copy {
  min-width: 0;
}

.doc-name {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.35;
  word-break: break-word;
}

.doc-meta {
  margin: 0.125rem 0 0;
  font-size: 0.625rem;
  color: #94a3b8;
}

.doc-status {
  margin: 0.25rem 0 0;
  font-size: 0.6875rem;
  color: #64748b;
}

.progress-bar {
  margin-top: 0.25rem;
  width: 100%;
  height: 0.25rem;
  border-radius: 999px;
  overflow: hidden;
  background: rgba(148, 163, 184, 0.3);
  position: relative;
}

.progress-fill {
  width: 0%;
  height: 100%;
  background: linear-gradient(90deg, #003fab 0%, #0354dd 100%);
  transition: width 0.4s ease;
}

.progress-bar.indeterminate .progress-fill {
  position: absolute;
  width: 40%;
  animation: progress-move 1.2s ease-in-out infinite;
}

.doc-error {
  margin: 0.25rem 0 0;
  color: #ba1a1a;
  font-size: 0.6875rem;
}

.doc-menu {
  position: relative;
  opacity: 0;
  transition: opacity 300ms ease-out;
}

.doc-actions {
  margin-left: auto;
  display: inline-flex;
  align-items: flex-start;
  gap: 0.375rem;
  flex-shrink: 0;
}

.chunk-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 3.8rem;
  height: 1.75rem;
  padding: 0 0.55rem;
  border-radius: 999px;
  background: #eef2ff;
  color: #3155a4;
  font-size: 0.625rem;
  font-weight: 700;
  letter-spacing: 0.01em;
}

.doc-row:hover .doc-menu,
.doc-menu[open] {
  opacity: 1;
}

.doc-menu summary {
  list-style: none;
  cursor: pointer;
  width: 1.75rem;
  height: 1.75rem;
  border-radius: 0.5rem;
  color: #94a3b8;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.doc-menu summary::-webkit-details-marker {
  display: none;
}

.doc-menu summary:hover {
  color: #003fab;
  background: #f1f5f9;
}

.doc-menu-card {
  position: absolute;
  top: calc(100% + 0.25rem);
  right: 0;
  z-index: 5;
  min-width: 5.5rem;
  background: #fff;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 0.625rem;
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
  padding: 0.25rem;
}

.doc-menu-item {
  border: none;
  width: 100%;
  text-align: left;
  border-radius: 0.5rem;
  padding: 0.45rem 0.625rem;
  background: transparent;
  color: #334155;
  font-size: 0.8125rem;
  font-weight: 600;
  cursor: pointer;
}

.doc-menu-item:hover {
  background: #f8fafc;
}

.doc-menu-item.danger {
  color: #ba1a1a;
}

.list-head {
  padding: 2rem 2rem 1rem;
  margin: 0;
}

.count-chip {
  border-radius: 999px;
  background: #d5e3fc;
  color: #0d1c2e;
  padding: 0.375rem 1rem;
  font-size: 0.75rem;
  font-weight: 700;
}

.kb-list {
  display: grid;
}

.kb-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 1.5rem 2rem;
  transition: background-color 300ms ease-out;
}

.kb-row:hover,
.kb-row.active {
  background: rgba(248, 250, 252, 0.8);
}

.kb-select {
  width: 100%;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 1rem;
  text-align: left;
  border: none;
  background: transparent;
  padding: 0;
  cursor: pointer;
}

.kb-icon {
  width: 3rem;
  height: 3rem;
  border-radius: 0.75rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.kb-icon .material-symbols-outlined {
  font-size: 1.5rem;
}

.kb-copy {
  min-width: 0;
  display: grid;
  gap: 0.125rem;
}

.kb-name {
  font-size: 1rem;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.35;
}

.kb-meta {
  font-size: 0.875rem;
  color: #64748b;
  line-height: 1.5;
}

.kb-delete {
  border: none;
  background: transparent;
  color: #ba1a1a;
  font-size: 0.875rem;
  font-weight: 700;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  border-radius: 0.5rem;
  transition: background-color 300ms ease-out;
}

.kb-delete:hover {
  background: rgba(255, 218, 214, 0.4);
}

.empty-block {
  color: #64748b;
  font-size: 0.875rem;
  text-align: center;
  padding: 1.5rem 1rem;
}

.banner {
  border-radius: 0.75rem;
  padding: 0.625rem 0.875rem;
  margin-bottom: 1rem;
  font-size: 0.875rem;
}

.banner-error {
  background: rgba(255, 218, 214, 0.6);
  color: #ba1a1a;
}

.tone-pdf {
  background: #fff1f2;
  color: #dc2626;
}

.tone-doc {
  background: #eff6ff;
  color: #2563eb;
}

.tone-text {
  background: #eef2f7;
  color: #475569;
}

.tone-default {
  background: #f2f4f6;
  color: #475569;
}

.help-fab {
  position: fixed;
  right: 2rem;
  bottom: 2rem;
  width: 3.5rem;
  height: 3.5rem;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: #fff;
  color: #003fab;
  box-shadow: 0 16px 40px rgba(148, 163, 184, 0.35);
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

@keyframes progress-move {
  0% {
    left: -40%;
  }
  100% {
    left: 100%;
  }
}

@media (min-width: 768px) {
  .knowledge-shell {
    padding: 2rem 2rem 3rem;
  }
}

@media (min-width: 1024px) {
  .knowledge-shell {
    padding: 3rem 3rem 3.5rem;
  }
}

@media (max-width: 1080px) {
  .knowledge-grid {
    grid-template-columns: 1fr;
    gap: 1rem;
  }

  .create-panel,
  .files-panel,
  .list-panel {
    grid-column: auto;
    grid-row: auto;
  }

  .files-panel {
    order: 3;
  }

  .create-btn {
    width: 100%;
  }

  .help-fab {
    right: 1rem;
    bottom: 1rem;
  }
}
</style>
