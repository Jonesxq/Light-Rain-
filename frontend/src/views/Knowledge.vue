<template>
  <div class="page knowledge-page">
    <header class="header">
      <div>
        <h1>我的知识库</h1>
        <p>创建知识库、上传文档并进行问答。</p>
      </div>
      <div class="actions" style="flex-direction: column; align-items: flex-end;">
        <label>
          API Base
          <input v-model="apiBase" @change="persistApiBase" placeholder="http://127.0.0.1:8000/api/v1" />
        </label>
        <div class="actions">
          <button class="ghost" @click="goChat">返回聊天</button>
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
              <span>状态：{{ doc.status }}</span>
              <span>切片：{{ doc.chunk_count }}</span>
            </div>
          </div>
          <div class="doc-actions">
            <span class="doc-time">{{ formatTime(doc.created_at) }}</span>
            <button class="doc-delete" @click="deleteDocument(doc)">删除</button>
          </div>
        </div>
      </div>
      <div v-else class="placeholder">该知识库暂无文档。</div>
    </section>

    <section class="card">
      <div class="actions" style="justify-content: space-between;">
        <h2>基于知识库问答</h2>
        <div class="actions">
          <select v-model.number="knowledgeChat.kbId">
            <option disabled value="">选择知识库</option>
            <option v-for="kb in knowledgeBases" :value="kb.id" :key="kb.id">
              {{ kb.name }} (#{{ kb.id }})
            </option>
          </select>
          <input v-model.number="knowledgeChat.sessionId" placeholder="会话ID（可选）" />
        </div>
      </div>
      <div class="chat-log">
        <div v-if="!knowledgeMessages.length" class="placeholder">从知识库提问，回答会展示在这里</div>
        <div v-for="(message, index) in knowledgeMessages" :key="index" :class="['chat-bubble', message.role]">
          <strong>{{ message.role }}</strong>
          <div class="message-content" v-html="formatMessage(message.content)"></div>
          <div v-if="message.sources && message.sources.length" class="source-list">
            <div class="source-title">引用来源</div>
            <ul>
              <li v-for="(source, sIndex) in message.sources" :key="sIndex">
                <span class="source-name">{{ source.file_name || '未知文档' }}</span>
                <span v-if="formatSourceLoc(source)" class="source-meta">
                  {{ formatSourceLoc(source) }}
                </span>
              </li>
            </ul>
          </div>
        </div>
      </div>
      <form class="chat-input" @submit.prevent="askKnowledge">
        <input v-model="knowledgeChat.message" placeholder="输入问题" />
        <button type="submit">发送</button>
      </form>
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

const knowledgeBases = ref([]);
const kbForm = ref({ name: '', description: '' });
const uploadForm = ref({ file: null });
const lastUpload = ref(null);
const knowledgeChat = ref({ kbId: '', sessionId: '', message: '' });
const knowledgeMessages = ref([]);
const activeKb = ref(null);
const documents = ref({ items: [] });

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
      knowledgeChat.value.kbId = activeKb.value ? activeKb.value.id : '';
      if (activeKb.value) {
        await fetchDocuments();
      }
    }
  } catch (err) {
    setError(`删除知识库失败：${err.message}`);
  }
};

const fetchDocuments = async () => {
  if (!activeKb.value) {
    setError('请选择知识库');
    return;
  }
  try {
    const data = await apiFetch(`/knowledge/${activeKb.value.id}/documents`);
    documents.value.items = data || [];
  } catch (err) {
    setError(`获取文档失败：${err.message}`);
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
  } catch (err) {
    setError(`删除文档失败：${err.message}`);
  }
};

const askKnowledge = async () => {
  if (!knowledgeChat.value.kbId) {
    setError('请选择知识库');
    return;
  }
  if (!knowledgeChat.value.message.trim()) return;

  try {
    const payload = {
      kb_id: knowledgeChat.value.kbId,
      message: knowledgeChat.value.message,
    };
    if (knowledgeChat.value.sessionId) {
      payload.session_id = Number(knowledgeChat.value.sessionId);
    }
    const data = await apiFetch('/chat/knowledge', {
      method: 'POST',
      body: payload,
    });
    knowledgeMessages.value.push({ role: 'user', content: knowledgeChat.value.message });
    knowledgeMessages.value.push({
      role: data.role,
      content: data.content,
      sources: data.sources || [],
    });
    knowledgeChat.value.message = '';
  } catch (err) {
    setError(`知识库问答失败：${err.message}`);
  }
};

const formatTime = (time) => {
  if (!time) return '';
  return new Date(time).toLocaleString();
};

const escapeHtml = (text) =>
  text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

const formatInline = (text) =>
  text
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

const formatListLabel = (text) => {
  if (!text) return '';
  return text.replace(/^([^：:]+[：:])\s*/, '<strong>$1</strong> ');
};

const isEmojiHeading = (text) =>
  /^[\u{1F000}-\u{1FAFF}]/u.test(text);

const formatMessage = (raw) => {
  if (!raw) return '';
  const escaped = escapeHtml(String(raw));
  const lines = escaped.split(/\r?\n/);
  let html = '';
  let inList = false;

  const closeList = () => {
    if (inList) {
      html += '</ul>';
      inList = false;
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (/^[-*•·]\s+/.test(trimmed)) {
      if (!inList) {
        html += '<ul class="md-list">';
        inList = true;
      }
      const item = trimmed.replace(/^[-*•·]\s+/, '');
      html += `<li>${formatInline(formatListLabel(item))}</li>`;
      continue;
    }

    closeList();

    if (isEmojiHeading(trimmed)) {
      html += `<div class="md-emoji-heading">${formatInline(trimmed)}</div>`;
      continue;
    }

    const headingMatch = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      html += `<div class="md-heading h${level}">${formatInline(headingMatch[2])}</div>`;
      continue;
    }

    if (!trimmed) {
      html += '<div class="md-blank"></div>';
      continue;
    }

    html += `<div class="md-line">${formatInline(trimmed)}</div>`;
  }

  closeList();
  return html;
};

const formatSourceLoc = (source) => {
  if (!source) return '';
  const parts = [];
  if (source.md_headings) parts.push(source.md_headings);
  if (source.pages && source.pages.length) parts.push(`页 ${source.pages.join(',')}`);
  if (source.slides && source.slides.length) parts.push(`幻灯片 ${source.slides.join(',')}`);
  if (source.paragraphs && source.paragraphs.length) parts.push(`段落 ${source.paragraphs.join(',')}`);
  if (source.tables && source.tables.length) parts.push(`表格 ${source.tables.join(',')}`);
  if (source.chunk_index !== undefined && source.chunk_index !== null) {
    parts.push(`Chunk ${source.chunk_index}`);
  }
  return parts.join(' · ');
};

fetchKnowledgeBases();
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
  background: linear-gradient(135deg, #cdd7ff 0%, #eef2ff 45%, #f7eaff 100%);
  border-radius: 28px;
  overflow: auto;
  font-family: "Noto Sans SC", "Source Han Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
  color: #1f2a44;
}

.knowledge-page::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 12% 18%, rgba(111, 140, 255, 0.28), transparent 45%),
    radial-gradient(circle at 90% 8%, rgba(245, 189, 255, 0.35), transparent 40%),
    radial-gradient(circle at 80% 80%, rgba(169, 210, 255, 0.3), transparent 40%);
  pointer-events: none;
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
  color: #6a728d;
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
  color: #5c647f;
}

.knowledge-page input,
.knowledge-page textarea,
.knowledge-page select {
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(111, 136, 255, 0.25);
  background: #fff;
  font-size: 13px;
}

.knowledge-page button {
  border: none;
  padding: 10px 16px;
  border-radius: 14px;
  background: linear-gradient(135deg, #6f88ff, #8d6bff);
  color: #fff;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 12px 22px rgba(108, 125, 255, 0.25);
}

.knowledge-page button.ghost {
  background: rgba(255, 255, 255, 0.9);
  color: #45507a;
  border: 1px solid rgba(111, 136, 255, 0.2);
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
  background: rgba(207, 234, 255, 0.6);
  color: #2c5a86;
}

.knowledge-page .error {
  background: rgba(255, 221, 228, 0.7);
  color: #a83c50;
}

.knowledge-page .card {
  background: rgba(255, 255, 255, 0.92);
  border-radius: 22px;
  padding: 18px;
  box-shadow: 0 22px 50px rgba(58, 72, 125, 0.16);
  border: 1px solid rgba(225, 231, 255, 0.9);
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

.knowledge-page .chat-log {
  background: #f6f8ff;
  border-radius: 18px;
  padding: 14px;
  max-height: 220px;
  overflow-y: auto;
}

.knowledge-page .chat-bubble {
  padding: 10px 12px;
  border-radius: 14px;
  margin-bottom: 10px;
  background: #fff;
  box-shadow: 0 10px 22px rgba(58, 72, 125, 0.08);
}

.knowledge-page .chat-bubble.user {
  margin-left: auto;
  background: linear-gradient(135deg, #6f88ff, #8d6bff);
  color: #fff;
}

.knowledge-page .chat-bubble strong {
  display: block;
  font-size: 12px;
  opacity: 0.75;
  margin-bottom: 6px;
}

.knowledge-page .chat-bubble p {
  margin: 0;
  line-height: 1.5;
}

.knowledge-page .message-content {
  line-height: 1.6;
  word-break: break-word;
}

.knowledge-page .source-list {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(111, 136, 255, 0.08);
  font-size: 12px;
  color: #4b567a;
}

.knowledge-page .source-title {
  font-weight: 600;
  margin-bottom: 6px;
}

.knowledge-page .source-list ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 4px;
}

.knowledge-page .source-name {
  font-weight: 600;
}

.knowledge-page .source-meta {
  margin-left: 6px;
  color: #6b7390;
}

.knowledge-page .message-content code {
  font-family: "JetBrains Mono", "Fira Code", "Consolas", monospace;
  font-size: 12px;
  background: rgba(99, 102, 241, 0.12);
  padding: 2px 6px;
  border-radius: 6px;
}

.knowledge-page .md-heading {
  font-weight: 700;
  margin: 8px 0 4px;
}

.knowledge-page .md-heading.h1 {
  font-size: 16px;
}

.knowledge-page .md-heading.h2 {
  font-size: 15px;
}

.knowledge-page .md-heading.h3 {
  font-size: 14px;
}

.knowledge-page .md-heading.h4,
.knowledge-page .md-heading.h5,
.knowledge-page .md-heading.h6 {
  font-size: 13px;
}

.knowledge-page .md-list {
  margin: 6px 0 6px 18px;
  padding: 0;
}

.knowledge-page .md-list li {
  margin: 2px 0;
}

.knowledge-page .md-line {
  margin: 2px 0;
}

.knowledge-page .md-blank {
  height: 6px;
}

.knowledge-page .md-emoji-heading {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 700;
  font-size: 14px;
  margin: 8px 0 6px;
  padding: 6px 10px;
  border-radius: 10px;
  background: rgba(111, 136, 255, 0.08);
  color: #2b3563;
}

.knowledge-page .chat-input {
  display: flex;
  gap: 10px;
  align-items: center;
  background: #fff;
  border-radius: 16px;
  padding: 12px;
  box-shadow: inset 0 0 0 1px rgba(218, 225, 255, 0.9);
}

.knowledge-page .chat-input input {
  flex: 1;
  border: none;
  outline: none;
  padding: 6px 8px;
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
