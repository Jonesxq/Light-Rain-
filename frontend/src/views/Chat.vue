<template>
  <div class="chat-layout">
    <aside class="chat-sidebar">
      <div class="sidebar-brand">
        <div class="brand-icon">雨</div>
        <div>
          <div class="brand-title">小雨</div>
          <div class="brand-subtitle">对话与知识库</div>
        </div>
      </div>
      <div class="sidebar-header">
        <button class="new-chat" @click="createSession">新对话</button>
        <button class="kb-link" @click="goKnowledge">我的知识库</button>
        <span class="shortcut">Ctrl K 快捷开启对话</span>
      </div>
      <div class="sidebar-section">
        <h3>对话历史</h3>
        <ul class="session-list">
          <li v-for="session in sessions" :key="session.id" :class="{ active: session.id === activeSessionId }">
            <button @click="selectSession(session.id)">
              <span>{{ getSessionTitle(session) }}</span>
            </button>
            <button class="delete-session" @click.stop="deleteSession(session.id)">删除</button>
          </li>
        </ul>
      </div>
      <button class="ghost refresh" @click="fetchSessions">刷新</button>
    </aside>

    <main class="chat-main">
      <header class="chat-topbar">
        <div>
          <h1>聊天中心</h1>
          <p>和模型对话，管理会话。</p>
        </div>
        <div class="actions topbar-actions">
          <label>
            API Base
            <input v-model="apiBase" @change="persistApiBase" placeholder="http://127.0.0.1:8000/api/v1" />
          </label>
          <div class="actions">
            <button class="ghost" @click="openKnowledgeSelector">知识库问答</button>
            <button v-if="knowledgeMode" class="ghost exit-kb" @click="exitKnowledgeMode">
              退出知识库问答
            </button>
            <button class="ghost" @click="logout">退出登录</button>
          </div>
        </div>
      </header>

    <div v-if="notice" class="notice">{{ notice }}</div>
    <div v-if="error" class="error">{{ error }}</div>

      <div class="chat-panel">
        <div class="chat-log" ref="chatLogRef">
          <div v-if="!chatMessages.length" class="empty-state">
            <h2>我是小雨，我能帮助您查询天气和联网搜索，也能基于您的知识库给你解答，请问有什么能帮助您？</h2>
            <p>选择左侧历史对话或直接输入问题开始聊天。</p>
          </div>
          <div v-for="message in chatMessages" :key="message.id" :class="['chat-message', message.role]">
            <div
              class="avatar"
              :class="message.role === 'user' ? 'user-avatar' : 'assistant-avatar'"
            ></div>
            <div class="chat-bubble">
              <div class="bubble-meta">
                <strong>{{ message.role === 'user' ? '我' : '助手' }}</strong>
                <small>{{ formatTime(message.created_at) }}</small>
              </div>
              <div v-if="message.role === 'assistant' && message.isLoading" class="assistant-loading">
                <span class="spinner" aria-hidden="true"></span>
                <span class="loading-text">正在思考...</span>
              </div>
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
        </div>
        <form class="chat-input" @submit.prevent="sendMessage">
          <div class="input-wrap">
            <span v-if="knowledgeMode && selectedKnowledgeBase" class="mode-badge">
              知识库：{{ selectedKnowledgeBase.name }}
            </span>
            <input v-model="chatInput" :placeholder="inputPlaceholder" />
          </div>
          <button type="submit">发送</button>
        </form>
      </div>
    </main>

    <Modal v-if="showKnowledgeSelector" @close="closeKnowledgeSelector">
      <h3>选择知识库</h3>
      <p>请选择要基于哪个知识库进行问答。</p>
      <div v-if="knowledgeBases.length" class="doc-list">
        <button
          v-for="kb in knowledgeBases"
          :key="kb.id"
          class="kb-item"
          @click="selectKnowledgeBase(kb)"
        >
          <strong>{{ kb.name }}</strong>
          <span>#{{ kb.id }}</span>
        </button>
      </div>
      <div v-else class="placeholder">暂无知识库，请先创建。</div>
    </Modal>

    <CenterToast :message="successMessage" />
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue';
import { useRouter } from 'vue-router';
import { apiFetch, clearTokens, getApiBase, getToken, setApiBase } from '../api/client.js';
import Modal from '../components/Modal.vue';
import CenterToast from '../components/CenterToast.vue';
import { useCenterToast } from '../composables/useCenterToast.js';

const router = useRouter();
const apiBase = ref(getApiBase());
const notice = ref('');
const error = ref('');
const { message: successMessage, show: showSuccess } = useCenterToast();

const sessions = ref([]);
const activeSessionId = ref(null);
const sessionTitle = ref('新对话');
const chatMessages = ref([]);
const sessionTitleMap = ref({});
const chatInput = ref('');
const knowledgeBases = ref([]);
const knowledgeMode = ref(false);
const selectedKnowledgeBase = ref(null);
const showKnowledgeSelector = ref(false);
const chatLogRef = ref(null);

const inputPlaceholder = computed(() => {
  if (knowledgeMode.value && selectedKnowledgeBase.value) {
    return `向知识库「${selectedKnowledgeBase.value.name}」提问`;
  }
  return '输入问题，按回车发送';
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

const persistApiBase = () => {
  setApiBase(apiBase.value);
  setNotice('API Base 已更新');
};

const goKnowledge = () => {
  router.push('/knowledge');
};

const fetchKnowledgeBases = async () => {
  try {
    const data = await apiFetch('/knowledge/list');
    knowledgeBases.value = data || [];
  } catch (err) {
    setError(`获取知识库失败：${err.message}`);
  }
};

const openKnowledgeSelector = async () => {
  showKnowledgeSelector.value = true;
  await fetchKnowledgeBases();
};

const closeKnowledgeSelector = () => {
  showKnowledgeSelector.value = false;
};

const selectKnowledgeBase = (kb) => {
  selectedKnowledgeBase.value = kb;
  knowledgeMode.value = true;
  showKnowledgeSelector.value = false;
  setNotice(`已进入知识库问答：${kb.name}`);
};

const exitKnowledgeMode = () => {
  knowledgeMode.value = false;
  selectedKnowledgeBase.value = null;
  setNotice('已退出知识库问答');
};

const logout = () => {
  clearTokens();
  router.push('/login');
};

const fetchSessions = async () => {
  try {
    const data = await apiFetch('/chat/sessions');
    sessions.value = data || [];
  } catch (err) {
    setError(`获取会话失败：${err.message}`);
  }
};

const createSession = async () => {
  try {
    const data = await apiFetch('/chat/sessions', {
      method: 'POST',
      body: { title: sessionTitle.value || '新对话' },
    });
    sessions.value.unshift(data);
    sessionTitleMap.value[data.id] = '';
    activeSessionId.value = data.id;
    await fetchMessages();
    setNotice('会话创建成功');
  } catch (err) {
    setError(`创建会话失败：${err.message}`);
  }
};

const selectSession = async (sessionId) => {
  activeSessionId.value = sessionId;
  await fetchMessages();
};

const fetchMessages = async () => {
  if (!activeSessionId.value) return;
  try {
    const data = await apiFetch(`/chat/sessions/${activeSessionId.value}/messages`);
    chatMessages.value = data || [];
    syncSessionTitle(activeSessionId.value, chatMessages.value);
    scrollToBottom();
  } catch (err) {
    setError(`获取历史消息失败：${err.message}`);
  }
};

const sendMessage = async () => {
  if (!chatInput.value.trim()) return;

  if (!activeSessionId.value) {
    try {
      const newSession = await apiFetch('/chat/sessions', {
        method: 'POST',
        body: { title: '新对话' },
      });
      sessions.value.unshift(newSession);
      activeSessionId.value = newSession.id;
    } catch (err) {
      setError(`创建会话失败：${err.message}`);
      return;
    }
  }

  const userMessage = {
    id: Date.now(),
    role: 'user',
    content: chatInput.value,
    created_at: new Date().toISOString(),
  };
  chatMessages.value.push(userMessage);
  syncSessionTitle(activeSessionId.value, chatMessages.value);
  scrollToBottom();

  const assistantMessage = {
    id: `stream-${Date.now()}`,
    role: 'assistant',
    content: '',
    created_at: new Date().toISOString(),
    isLoading: true,
  };
  chatMessages.value.push(assistantMessage);
  scrollToBottom();

  try {
    if (knowledgeMode.value && selectedKnowledgeBase.value) {
      const data = await apiFetch('/chat/knowledge', {
        method: 'POST',
        body: {
          kb_id: selectedKnowledgeBase.value.id,
          message: chatInput.value,
          session_id: activeSessionId.value,
        },
      });
      applyFinalMessage(assistantMessage, data);
    } else {
      const data = await apiFetch(`/chat/sessions/${activeSessionId.value}/send`, {
        method: 'POST',
        body: { message: chatInput.value },
      });
      applyFinalMessage(assistantMessage, data);
    }
    chatInput.value = '';
  } catch (err) {
    assistantMessage.content = `发送失败：${err.message}`;
    assistantMessage.isLoading = false;
    setError(`发送失败：${err.message}`);
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

const getSessionTitle = (session) => {
  const mappedTitle = sessionTitleMap.value[session.id];
  return mappedTitle || session.title || '新对话';
};

const syncSessionTitle = (sessionId, messages) => {
  if (!sessionId) return;
  if (sessionTitleMap.value[sessionId]) return;
  const firstQuestion = (messages || []).find(
    (message) => message.role === 'user' && message.content && message.content.trim(),
  );
  if (!firstQuestion) return;
  sessionTitleMap.value[sessionId] = firstQuestion.content.trim().slice(0, 15);
};

const applyFinalMessage = (targetMessage, finalMessage) => {
  if (!finalMessage) return;
  targetMessage.id = finalMessage.id || targetMessage.id;
  targetMessage.created_at = finalMessage.created_at || targetMessage.created_at;
  targetMessage.model_name = finalMessage.model_name || targetMessage.model_name;
  targetMessage.content = finalMessage.content || targetMessage.content;
  targetMessage.sources = finalMessage.sources || targetMessage.sources;
  targetMessage.isLoading = false;
  scrollToBottom();
};

const deleteSession = async (sessionId) => {
  const confirmed = window.confirm('您确定要删除吗？');
  if (!confirmed) return;
  try {
    await apiFetch(`/chat/sessions/${sessionId}`, { method: 'DELETE' });
    sessions.value = sessions.value.filter((session) => session.id !== sessionId);
    if (activeSessionId.value === sessionId) {
      activeSessionId.value = null;
      chatMessages.value = [];
    }
  } catch (err) {
    setError(`删除会话失败：${err.message}`);
  }
};

const scrollToBottom = () => {
  nextTick(() => {
    const log = chatLogRef.value;
    if (!log) return;
    log.scrollTop = log.scrollHeight;
  });
};

fetchSessions();
</script>

<style scoped>
.chat-layout {
  position: relative;
  width: 1200px;
  height: 760px;
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 48px);
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 22px;
  padding: 24px;
  background: linear-gradient(135deg, #cdd7ff 0%, #eef2ff 45%, #f7eaff 100%);
  font-family: "Noto Sans SC", "Source Han Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
  color: #1f2a44;
  margin: 24px auto;
  border-radius: 28px;
  overflow: hidden;
}

.chat-layout::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 12% 18%, rgba(111, 140, 255, 0.28), transparent 45%),
    radial-gradient(circle at 90% 8%, rgba(245, 189, 255, 0.35), transparent 40%),
    radial-gradient(circle at 80% 80%, rgba(169, 210, 255, 0.3), transparent 40%);
  pointer-events: none;
}

.chat-layout > .chat-sidebar,
.chat-layout > .chat-main {
  position: relative;
  z-index: 1;
}

.chat-sidebar {
  display: flex;
  flex-direction: column;
  padding: 20px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.78);
  box-shadow: 0 24px 50px rgba(77, 96, 164, 0.18);
  backdrop-filter: blur(10px);
  min-height: 0;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 16px;
  border-bottom: 1px solid rgba(130, 150, 210, 0.2);
}

.brand-icon {
  width: 42px;
  height: 42px;
  border-radius: 14px;
  background: linear-gradient(135deg, #6f88ff, #a66bff);
  color: #fff;
  display: grid;
  place-items: center;
  font-weight: 700;
  letter-spacing: 0.5px;
}

.brand-title {
  font-size: 18px;
  font-weight: 700;
}

.brand-subtitle {
  font-size: 12px;
  color: #6b728a;
}

.sidebar-header {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 18px 0;
}

.new-chat,
.kb-link {
  width: 100%;
  border-radius: 14px;
  padding: 10px 14px;
  font-weight: 600;
  border: none;
  cursor: pointer;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.new-chat {
  background: linear-gradient(135deg, #6f88ff, #8d6bff);
  color: #fff;
  box-shadow: 0 12px 22px rgba(108, 125, 255, 0.3);
}

.kb-link {
  background: #fff;
  border: 1px solid rgba(111, 136, 255, 0.25);
  color: #2b3563;
  box-shadow: 0 8px 18px rgba(94, 112, 190, 0.12);
}

.new-chat:hover,
.kb-link:hover {
  transform: translateY(-1px);
}

.shortcut {
  font-size: 12px;
  color: #7a84a6;
}

.sidebar-section h3 {
  font-size: 14px;
  color: #4b567a;
  margin-bottom: 10px;
}

.sidebar-section {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.session-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  padding-right: 6px;
  flex: 1;
  min-height: 0;
}

.session-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px;
  border-radius: 12px;
  background: rgba(245, 246, 255, 0.9);
  transition: background 0.2s ease, box-shadow 0.2s ease;
}

.session-list li.active {
  background: rgba(111, 136, 255, 0.15);
  box-shadow: inset 0 0 0 1px rgba(111, 136, 255, 0.35);
}

.session-list button {
  border: none;
  background: transparent;
  cursor: pointer;
  color: inherit;
  font-size: 13px;
}

.session-list button span {
  display: inline-block;
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.delete-session {
  margin-left: auto;
  font-size: 12px;
  color: #c24d67;
}

.ghost {
  border: 1px solid rgba(111, 136, 255, 0.2);
  background: rgba(255, 255, 255, 0.85);
  color: #45507a;
  border-radius: 12px;
  padding: 8px 12px;
  cursor: pointer;
  transition: background 0.2s ease;
}

.exit-kb {
  border-color: rgba(255, 153, 153, 0.4);
  color: #b5535c;
}

.refresh {
  margin-top: auto;
}

.chat-main {
  display: flex;
  flex-direction: column;
  padding: 24px;
  border-radius: 26px;
  background: rgba(255, 255, 255, 0.92);
  box-shadow: 0 26px 60px rgba(58, 72, 125, 0.18);
  min-height: 0;
}

.chat-topbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
}

.chat-topbar h1 {
  margin: 0;
  font-size: 26px;
}

.chat-topbar p {
  margin: 6px 0 0;
  color: #6a728d;
}

.topbar-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: flex-end;
}

.topbar-actions label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: #5c647f;
}

.topbar-actions input {
  width: 280px;
  padding: 8px 10px;
  border-radius: 10px;
  border: 1px solid rgba(111, 136, 255, 0.25);
  background: #fff;
  font-size: 12px;
}

.notice,
.error {
  margin: 16px 0 0;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px;
}

.notice {
  background: rgba(207, 234, 255, 0.6);
  color: #2c5a86;
}

.error {
  background: rgba(255, 221, 228, 0.7);
  color: #a83c50;
}

.chat-panel {
  margin-top: 18px;
  background: #f6f8ff;
  border-radius: 22px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  flex: 1;
  min-height: 0;
}

.chat-log {
  flex: 1;
  overflow-y: auto;
  padding-right: 6px;
}

.empty-state {
  background: #fff;
  border-radius: 18px;
  padding: 26px;
  text-align: center;
  box-shadow: inset 0 0 0 1px rgba(225, 231, 255, 0.9);
}

.empty-state h2 {
  font-size: 18px;
  margin-bottom: 10px;
}

.empty-state p {
  color: #7b839e;
}

.chat-message {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 14px;
}

.chat-message.user {
  flex-direction: row-reverse;
}

.avatar {
  width: 38px;
  height: 38px;
  border-radius: 50%;
  flex-shrink: 0;
  position: relative;
  box-shadow: 0 10px 20px rgba(58, 72, 125, 0.18);
}

.avatar::after {
  content: "";
  position: absolute;
  inset: 4px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.7);
}

.assistant-avatar {
  background:
    radial-gradient(circle at 30% 30%, #ffffff, transparent 55%),
    linear-gradient(135deg, #7ee7ff 0%, #5b8dff 50%, #7a5cff 100%);
}

.user-avatar {
  background:
    radial-gradient(circle at 70% 30%, #fff1f2, transparent 55%),
    linear-gradient(135deg, #ff9bb0 0%, #ffb86b 50%, #ffd36b 100%);
}

.chat-bubble {
  max-width: 70%;
  padding: 12px 14px;
  border-radius: 16px;
  background: #fff;
  box-shadow: 0 10px 24px rgba(58, 72, 125, 0.08);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.chat-message.user .chat-bubble {
  background: linear-gradient(135deg, #6f88ff, #8d6bff);
  color: #fff;
}

.bubble-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 12px;
  opacity: 0.75;
}

.chat-message.user .bubble-meta {
  justify-content: flex-end;
  gap: 8px;
}

.chat-bubble strong {
  font-weight: 600;
}

.chat-bubble p {
  margin: 0;
  line-height: 1.5;
}

.message-content {
  line-height: 1.6;
  word-break: break-word;
}

.source-list {
  margin-top: 8px;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(111, 136, 255, 0.08);
  font-size: 12px;
  color: #4b567a;
}

.source-title {
  font-weight: 600;
  margin-bottom: 6px;
}

.source-list ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 4px;
}

.source-name {
  font-weight: 600;
}

.source-meta {
  margin-left: 6px;
  color: #6b7390;
}

.message-content code {
  font-family: "JetBrains Mono", "Fira Code", "Consolas", monospace;
  font-size: 12px;
  background: rgba(99, 102, 241, 0.12);
  padding: 2px 6px;
  border-radius: 6px;
}

.md-heading {
  font-weight: 700;
  margin: 8px 0 4px;
}

.md-heading.h1 {
  font-size: 16px;
}

.md-heading.h2 {
  font-size: 15px;
}

.md-heading.h3 {
  font-size: 14px;
}

.md-heading.h4,
.md-heading.h5,
.md-heading.h6 {
  font-size: 13px;
}

.md-list {
  margin: 6px 0 6px 18px;
  padding: 0;
}

.md-list li {
  margin: 2px 0;
}

.md-line {
  margin: 2px 0;
}

.md-blank {
  height: 6px;
}

.md-emoji-heading {
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

.chat-bubble small {
  font-size: 11px;
}

.assistant-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  color: #5b65a2;
}

.spinner {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 2px solid rgba(111, 136, 255, 0.25);
  border-top-color: #6f88ff;
  animation: spin 0.9s linear infinite;
}

.loading-text {
  letter-spacing: 0.2px;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.chat-input {
  display: flex;
  gap: 10px;
  align-items: center;
  background: #fff;
  border-radius: 16px;
  padding: 12px;
  box-shadow: inset 0 0 0 1px rgba(218, 225, 255, 0.9);
}

.input-wrap {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
}

.mode-badge {
  align-self: flex-start;
  background: rgba(111, 136, 255, 0.15);
  color: #4852a8;
  border-radius: 10px;
  padding: 2px 8px;
  font-size: 12px;
}

.chat-input input {
  border: none;
  outline: none;
  font-size: 14px;
  padding: 6px 8px;
}

.chat-input button {
  border: none;
  padding: 10px 18px;
  border-radius: 14px;
  background: linear-gradient(135deg, #6f88ff, #8d6bff);
  color: #fff;
  font-weight: 600;
  cursor: pointer;
}

@media (max-width: 1080px) {
  .chat-layout {
    grid-template-columns: 1fr;
    width: 100%;
    height: auto;
    max-height: none;
    margin: 16px auto;
  }

  .chat-sidebar {
    order: 2;
  }

  .chat-main {
    order: 1;
  }

  .topbar-actions {
    align-items: flex-start;
  }

  .topbar-actions input {
    width: 100%;
  }

  .chat-bubble {
    max-width: 85%;
  }
}
</style>
