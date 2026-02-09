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
          <button class="ghost" @click="goSettings">模型设置</button>
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
                <button
                  class="source-link"
                  type="button"
                  :disabled="!canPreviewSource(source)"
                  @click="openSourcePreview(source, resolveQueryForMessage(knowledgeMessages, index))"
                >
                  <span class="source-name">{{ source.file_name || '未知文档' }}</span>
                  <span v-if="formatSourceLoc(source)" class="source-meta">
                    {{ formatSourceLoc(source) }}
                  </span>
                </button>
              </li>
            </ul>
          </div>
        </div>
      </div>
      <form class="chat-input" @submit.prevent="askKnowledge">
        <input v-model="knowledgeChat.message" placeholder="输入问题" />
        <button type="submit" :disabled="isStreaming">发送</button>
      </form>
    </section>

    <Modal v-if="previewOpen" @close="closePreview">
      <div class="source-preview">
        <div class="source-preview-header">
          <h3>引用预览</h3>
          <div v-if="previewData" class="source-preview-meta">
            <span class="source-preview-name">{{ previewData.file_name || '未知文档' }}</span>
            <span v-if="formatPreviewLoc(previewData)" class="source-preview-loc">
              {{ formatPreviewLoc(previewData) }}
            </span>
          </div>
        </div>
        <div v-if="previewLoading" class="source-preview-loading">正在加载...</div>
        <div v-else-if="previewError" class="source-preview-error">{{ previewError }}</div>
        <div v-else class="source-preview-content" v-html="previewHtml"></div>
      </div>
    </Modal>

    <CenterToast :message="successMessage" />
  </div>
</template>

<script setup>
import { ref, reactive, onBeforeUnmount } from 'vue';
import { useRouter } from 'vue-router';
import { apiFetch, apiStream, clearTokens, getApiBase, setApiBase } from '../api/client.js';
import Modal from '../components/Modal.vue';
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
const isStreaming = ref(false);
let streamController = null;
const activeKb = ref(null);
const documents = ref({ items: [] });
const previewOpen = ref(false);
const previewLoading = ref(false);
const previewError = ref('');
const previewData = ref(null);
const previewHtml = ref('');
let previewRequestId = 0;
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

const persistApiBase = () => {
  setApiBase(apiBase.value);
  setNotice('API Base 已更新');
};

const goChat = () => {
  router.push('/chat');
};

const goSettings = () => {
  router.push('/settings');
};

const logout = () => {
  if (streamController) {
    streamController.abort();
    streamController = null;
    isStreaming.value = false;
  }
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

const askKnowledge = async () => {
  if (!knowledgeChat.value.kbId) {
    setError('请选择知识库');
    return;
  }
  if (!knowledgeChat.value.message.trim()) return;
  if (isStreaming.value) {
    setError('正在生成回复，请稍候');
    return;
  }

  try {
    isStreaming.value = true;
    streamController = new AbortController();
    const inputText = knowledgeChat.value.message;
    const payload = {
      kb_id: knowledgeChat.value.kbId,
      message: inputText,
    };
    if (knowledgeChat.value.sessionId) {
      payload.session_id = Number(knowledgeChat.value.sessionId);
    }
    knowledgeMessages.value.push({ role: 'user', content: inputText });
    const assistantMessage = reactive({ role: 'assistant', content: '', sources: [], isLoading: true });
    knowledgeMessages.value.push(assistantMessage);
    knowledgeChat.value.message = '';

    let streamError = false;
    const handlePayload = (payloadData) => {
      if (!payloadData) return;
      if (typeof payloadData === 'object') {
        if (payloadData.event === 'error') {
          streamError = true;
          const errMessage = payloadData.message || '生成失败';
          assistantMessage.content = `发送失败：${errMessage}`;
          assistantMessage.isLoading = false;
          setError(`知识库问答失败：${errMessage}`);
          return;
        }
        if (payloadData.event === 'done' && payloadData.message) {
          assistantMessage.content = payloadData.message.content || assistantMessage.content;
          assistantMessage.sources = payloadData.message.sources || [];
          assistantMessage.isLoading = false;
          return;
        }
        if (typeof payloadData.content === 'string') {
          assistantMessage.content += payloadData.content;
        }
        return;
      }
      if (typeof payloadData === 'string') {
        assistantMessage.content += payloadData;
      }
    };

    await apiStream('/chat/knowledge/stream', {
      method: 'POST',
      body: payload,
      signal: streamController.signal,
      onMessage: handlePayload,
    });

    if (assistantMessage.isLoading) {
      assistantMessage.isLoading = false;
    }
    if (!streamError && !assistantMessage.content) {
      assistantMessage.content = '未收到回复，请稍后重试。';
      setError('未收到回复，请稍后重试。');
    }
  } catch (err) {
    if (err.message !== '请求已取消') {
      setError(`知识库问答失败：${err.message}`);
    }
  } finally {
    isStreaming.value = false;
    streamController = null;
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

const getApiRoot = () => {
  const base = apiBase.value || '';
  if (!base) return window.location.origin;
  if (/^https?:\/\//i.test(base)) {
    try {
      const url = new URL(base);
      url.pathname = url.pathname.replace(/\/api\/v1\/?$/, '');
      return url.toString().replace(/\/$/, '');
    } catch {
      return base.replace(/\/api\/v1\/?$/, '');
    }
  }
  if (base.startsWith('/')) {
    return window.location.origin;
  }
  return base.replace(/\/api\/v1\/?$/, '');
};

const resolveMediaUrl = (rawUrl) => {
  const url = (rawUrl || '').trim();
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  if (url.startsWith('//')) return `${window.location.protocol}${url}`;
  const root = getApiRoot();
  if (url.startsWith('/')) return `${root}${url}`;
  return `${root}/${url.replace(/^\.?\//, '')}`;
};

const mergeImageLines = (lines) => {
  const merged = [];
  for (let i = 0; i < lines.length; i += 1) {
    const current = lines[i];
    const trimmed = current.trim();
    if (/^!\[[^\]]*\]$/.test(trimmed) && i + 1 < lines.length) {
      const nextTrimmed = lines[i + 1].trim();
      if (/^\([^)]+\)$/.test(nextTrimmed)) {
        merged.push(`${trimmed}${nextTrimmed}`);
        i += 1;
        continue;
      }
    }
    merged.push(current);
  }
  return merged;
};

const formatListLabel = (text) => {
  if (!text) return '';
  return text.replace(/^([^：:]+[：:])\s*/, '<strong>$1</strong> ');
};

const isEmojiHeading = (text) =>
  /^[\u{1F000}-\u{1FAFF}]/u.test(text);

const formatMessage = (raw) => {
  if (!raw) return '';
  const escaped = escapeHtml(String(raw));
  const lines = mergeImageLines(escaped.split(/\r?\n/));
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

    const imageMatch = trimmed.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
    if (imageMatch) {
      const altText = imageMatch[1] || 'image';
      const resolvedUrl = resolveMediaUrl(imageMatch[2]);
      html += `<div class="md-image"><img class="chat-image" src="${resolvedUrl}" alt="${altText}" loading="lazy" /></div>`;
      continue;
    }

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

const canPreviewSource = (source) =>
  source &&
  source.doc_id !== undefined &&
  source.doc_id !== null &&
  source.chunk_index !== undefined &&
  source.chunk_index !== null;

const resolveQueryForMessage = (messages, index) => {
  for (let i = index - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message && message.role === 'user' && message.content && message.content.trim()) {
      return message.content;
    }
  }
  return '';
};

const STOPWORDS = new Set([
  'the', 'and', 'for', 'with', 'that', 'this', 'from', 'are', 'was', 'were', 'you', 'your', 'about', 'have', 'has',
  'had', 'will', 'would', 'could', 'should', 'what', 'which', 'when', 'where', 'why', 'how', 'please', 'than', 'then',
  'also', 'into', 'over', 'under', 'between', 'after', 'before', 'there', 'their', 'them', 'they', 'ours', 'ourselves',
  '这些', '那些', '什么', '怎么', '如何', '为什么', '是否', '可以', '一个', '我们', '你们', '他们', '以及', '进行', '相关', '需要',
  '请问', '关于', '就是', '不是', '以及', '还有', '如果', '其中', '因为', '所以', '但是', '因为', '那么', '已经', '目前',
]);

const extractKeywords = (query) => {
  if (!query) return [];
  const matches =
    String(query).match(/[A-Za-z0-9]{3,}|[\u4e00-\u9fff]{2,}|[\u3040-\u30ff]{2,}|[\uac00-\ud7af]{2,}/g) || [];
  const seen = new Set();
  const candidates = [];
  let idx = 0;
  for (const raw of matches) {
    const term = raw.trim();
    if (!term) continue;
    const key = term.toLowerCase();
    if (seen.has(key)) continue;
    if (STOPWORDS.has(key) || STOPWORDS.has(term)) continue;
    seen.add(key);
    candidates.push({ term, index: idx });
    idx += 1;
  }
  if (!candidates.length) return [];
  const ranked = candidates
    .sort((a, b) => {
      if (b.term.length !== a.term.length) return b.term.length - a.term.length;
      return a.index - b.index;
    })
    .slice(0, 8)
    .map((item) => item.term);
  return ranked;
};

const escapeRegex = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const highlightChunk = (text, keywords) => {
  let html = escapeHtml(String(text || ''));
  if (keywords && keywords.length) {
    const sorted = [...keywords].sort((a, b) => b.length - a.length);
    const pattern = new RegExp(`(${sorted.map(escapeRegex).join('|')})`, 'gi');
    html = html.replace(pattern, '<mark>$1</mark>');
  }
  return html.replace(/\r?\n/g, '<br>');
};

const formatPreviewLoc = (data) => {
  if (!data) return '';
  const parts = [];
  if (data.md_headings) parts.push(data.md_headings);
  if (data.pages && data.pages.length) parts.push(`页 ${data.pages.join(',')}`);
  if (data.slides && data.slides.length) parts.push(`幻灯片 ${data.slides.join(',')}`);
  if (data.paragraphs && data.paragraphs.length) parts.push(`段落 ${data.paragraphs.join(',')}`);
  if (data.tables && data.tables.length) parts.push(`表格 ${data.tables.join(',')}`);
  if (data.chunk_index !== undefined && data.chunk_index !== null) {
    parts.push(`Chunk ${data.chunk_index}`);
  }
  return parts.join(' · ');
};

const openSourcePreview = async (source, query) => {
  if (!canPreviewSource(source)) return;
  previewRequestId += 1;
  const requestId = previewRequestId;
  previewOpen.value = true;
  previewLoading.value = true;
  previewError.value = '';
  previewData.value = null;
  previewHtml.value = '';
  try {
    const data = await apiFetch(`/knowledge/documents/${source.doc_id}/chunks/${source.chunk_index}`);
    if (requestId !== previewRequestId) return;
    previewData.value = data;
    const keywords = extractKeywords(query || '');
    previewHtml.value = highlightChunk(data.content || '', keywords) || '暂无内容';
  } catch (err) {
    if (requestId !== previewRequestId) return;
    previewError.value = err.message || '加载失败';
  } finally {
    if (requestId === previewRequestId) {
      previewLoading.value = false;
    }
  }
};

const closePreview = () => {
  previewOpen.value = false;
  previewLoading.value = false;
  previewError.value = '';
  previewData.value = null;
  previewHtml.value = '';
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

.knowledge-page button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
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
  color: #b91c1c;
  background: rgba(254, 226, 226, 0.6);
  padding: 6px 8px;
  border-radius: 8px;
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

.knowledge-page .message-content :deep(.md-image) {
  margin: 8px 0;
  display: flex;
  justify-content: flex-start;
  max-width: 320px;
  width: 100%;
  background: #fff;
  border-radius: 12px;
  padding: 6px;
}

.knowledge-page .message-content :deep(.chat-image) {
  width: 100%;
  max-width: 320px;
  max-height: 180px;
  object-fit: contain;
  display: block;
  border-radius: 12px;
  background: #fff;
}

@media (max-width: 900px) {
  .knowledge-page .message-content :deep(.md-image) {
    max-width: 240px;
  }

  .knowledge-page .message-content :deep(.chat-image) {
    max-width: 240px;
    max-height: 150px;
  }
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

.knowledge-page .source-link {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border: none;
  background: transparent;
  padding: 0;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.knowledge-page .source-link:hover:not(:disabled) {
  text-decoration: underline;
}

.knowledge-page .source-link:disabled {
  cursor: not-allowed;
  opacity: 0.6;
  text-decoration: none;
}

.knowledge-page .source-name {
  font-weight: 600;
}

.knowledge-page .source-meta {
  margin-left: 6px;
  color: #6b7390;
}

.knowledge-page .source-preview {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.knowledge-page .source-preview-header h3 {
  margin: 0 0 6px;
}

.knowledge-page .source-preview-meta {
  font-size: 12px;
  color: #6b7390;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.knowledge-page .source-preview-name {
  font-weight: 600;
}

.knowledge-page .source-preview-content {
  max-height: 320px;
  overflow: auto;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: #f8fafc;
  line-height: 1.6;
}

.knowledge-page .source-preview-content mark {
  background: #fde68a;
  color: #7c2d12;
  padding: 0 2px;
  border-radius: 3px;
}

.knowledge-page .source-preview-loading,
.knowledge-page .source-preview-error {
  font-size: 13px;
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
