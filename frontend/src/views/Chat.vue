<template>
  <div class="chat-page">
    <div v-if="mobileSidebarOpen" class="sidebar-backdrop" @click="closeMobileSidebar"></div>

    <aside class="workspace-sidebar" :class="{ open: mobileSidebarOpen }">
      <div class="sidebar-top">
        <div class="sidebar-brand">
          <div class="brand-icon">
            <span class="material-symbols-outlined" aria-hidden="true">auto_awesome</span>
          </div>
          <div class="brand-copy">
            <div class="brand-title">小雨</div>
            <div class="brand-subtitle">对话与知识库</div>
          </div>
        </div>

        <button class="new-chat-btn" @click="createSession">
          <span class="material-symbols-outlined nav-icon" aria-hidden="true">add_comment</span>
          <span>开启新对话</span>
        </button>

        <nav class="workspace-nav">
          <div class="history-block">
            <button class="workspace-nav-item history-trigger" :class="{ active: historyPanelOpen }" @click="toggleHistoryPanel">
              <span class="material-symbols-outlined nav-icon" aria-hidden="true">history</span>
              <span>历史记录</span>
            </button>
            <div class="history-panel" :class="{ open: historyPanelOpen }">
              <div class="session-filter">
                <input
                  v-model="sessionQuery"
                  placeholder="搜索会话标题"
                  @input="scheduleSessionSearch"
                  ref="sessionSearchRef"
                />
              </div>
              <div v-if="!sessions.length" class="session-empty">暂无聊天历史</div>
              <ul v-else class="session-list">
                <li v-for="session in sessions" :key="session.id" :class="{ active: session.id === activeSessionId }">
                  <button class="session-entry" @click="selectSession(session.id)">
                    <span class="session-title">{{ getSessionTitle(session) }}</span>
                    <span v-if="session.is_pinned" class="session-flag">置顶</span>
                    <span v-if="session.is_archived" class="session-flag archived">归档</span>
                    <span v-if="session.tags && session.tags.length" class="session-tags">
                      <span v-for="tag in session.tags.slice(0, 2)" :key="tag" class="session-tag">
                        {{ tag }}
                      </span>
                    </span>
                  </button>
                  <button class="session-menu-trigger" @click.stop="toggleSessionMenu(session.id)">⋯</button>
                  <button class="delete-session" @click.stop="deleteSession(session.id)">删除</button>
                  <div v-if="sessionMenuId === session.id" class="session-menu">
                    <button @click.stop="renameSession(session)">重命名</button>
                    <button @click.stop="togglePinSession(session)">{{ session.is_pinned ? '取消置顶' : '置顶' }}</button>
                    <button @click.stop="toggleArchiveSession(session)">{{ session.is_archived ? '取消归档' : '归档' }}</button>
                    <button @click.stop="editSessionTags(session)">编辑标签</button>
                    <button @click.stop="exportSession(session, 'md')">导出 Markdown</button>
                    <button @click.stop="exportSession(session, 'json')">导出 JSON</button>
                  </div>
                </li>
              </ul>
            </div>
          </div>

          <button class="workspace-nav-item" @click="goKnowledge(); closeMobileSidebar()">
            <span class="material-symbols-outlined nav-icon" aria-hidden="true">folder_shared</span>
            <span>我的知识库</span>
          </button>
          <button class="workspace-nav-item" @click="goAiNews(); closeMobileSidebar()">
            <span class="material-symbols-outlined nav-icon" aria-hidden="true">newspaper</span>
            <span>AI资讯</span>
          </button>
        </nav>
      </div>

      <div class="sidebar-footer">
        <div class="footer-links">
          <button class="footer-link" @click="goSettings(); closeMobileSidebar()">
            <span class="material-symbols-outlined nav-icon" aria-hidden="true">settings</span>
            <span>设置</span>
          </button>
          <button class="footer-link danger" @click="logout">
            <span class="material-symbols-outlined nav-icon" aria-hidden="true">logout</span>
            <span>退出登录</span>
          </button>
        </div>
        <button type="button" class="profile-card profile-link" @click="goMy(); closeMobileSidebar()">
          <div
            class="profile-avatar"
            :class="{ 'has-image': !!profileAvatarUrl }"
            :style="profileAvatarStyle"
          >
            {{ profileAvatarFallback }}
          </div>
          <div>
            <p class="profile-name">{{ profileName }}</p>
            <p class="profile-email">{{ profileEmail }}</p>
          </div>
        </button>
      </div>
    </aside>

    <main class="workspace-main">
      <header class="workspace-header">
        <div class="header-left">
          <button class="icon-btn mobile-only" type="button" @click="toggleMobileSidebar">☰</button>
        </div>
        <div v-if="knowledgeMode" class="workspace-top-actions">
          <button type="button" class="top-chip subtle" @click="exitKnowledgeMode">
            退出知识库
          </button>
        </div>
      </header>

      <div v-if="notice" class="notice">{{ notice }}</div>
      <div v-if="error" class="error">{{ error }}</div>

      <section
        class="chat-shell"
        :class="{ dragging: isDragging }"
        @dragover.prevent="handleDragOver"
        @dragleave.prevent="handleDragLeave"
        @drop.prevent="handleDrop"
      >
        <div v-if="isDragging" class="drop-mask">松开鼠标上传临时资料</div>
        <div class="chat-log" ref="chatLogRef">
          <div v-if="!chatMessages.length" class="empty-state">
            <p>我是小雨，能基于知识库问答，能联网搜索也能生成你需要的图片，请问有什么能帮您。</p>
          </div>

          <div
            v-for="(message, index) in chatMessages"
            :key="message.id || index"
            :id="message.id ? `msg-${message.id}` : null"
            :class="['chat-message', message.role, { highlight: message.id === highlightMessageId }]"
          >
            <div class="avatar" :class="message.role === 'user' ? 'user-avatar' : 'assistant-avatar'"></div>
            <div class="chat-bubble">
              <div class="bubble-meta">
                <strong>{{ message.role === 'user' ? '我' : '助手' }}</strong>
                <small>
                  {{ formatTimeCached(message.created_at) }}
                  <span v-if="message.edited_at"> · 已编辑</span>
                </small>
              </div>
              <div v-if="message.role === 'assistant' && message.isLoading" class="assistant-loading">
                <span class="spinner" aria-hidden="true"></span>
                <span class="loading-text">{{ message.statusText || '正在思考...' }}</span>
              </div>
              <div class="message-content" v-html="getFormattedMessage(message)"></div>
              <div v-if="!message.isLoading" class="message-actions">
                <button
                  v-if="message.role === 'user'"
                  type="button"
                  class="ghost ghost-small"
                  :disabled="isStreaming"
                  @click="startEdit(message)"
                >
                  编辑
                </button>
                <button
                  v-if="message.role === 'assistant'"
                  type="button"
                  class="ghost ghost-small"
                  :disabled="isStreaming"
                  @click="regenerateMessage(message)"
                >
                  重新生成
                </button>
                <button
                  v-if="message.role === 'assistant'"
                  type="button"
                  class="ghost ghost-small"
                  :disabled="isStreaming || memeGeneratingId === message.id"
                  @click="generateMeme(message)"
                >
                  {{ memeGeneratingId === message.id ? '生成中...' : '表情包' }}
                </button>
                <button type="button" class="ghost ghost-small" @click="copyMessage(message)">复制</button>
                <button type="button" class="ghost ghost-small" @click="quoteMessage(message)">引用</button>
                <button
                  v-if="message.role === 'assistant'"
                  type="button"
                  class="ghost ghost-small"
                  @click="toggleFavorite(message)"
                >
                  {{ message.is_favorite ? '取消收藏' : '收藏' }}
                </button>
                <button
                  v-if="isSuperuser && message.role === 'assistant'"
                  type="button"
                  class="ghost ghost-small"
                  @click="openDebug(message)"
                >
                  调试
                </button>
              </div>
              <div v-if="message.sources && message.sources.length" class="source-list">
                <div class="source-title">引用来源</div>
                <ul>
                  <li
                    v-for="(source, sIndex) in message.sources"
                    :key="sIndex"
                    :id="message.id ? `source-${message.id}-${sIndex + 1}` : null"
                  >
                    <button v-if="source.url" class="source-link" type="button" @click="openWebSource(source)">
                      <span class="source-name">{{ source.title || source.file_name || '网页来源' }}</span>
                      <span v-if="getSourceLoc(source)" class="source-meta">{{ getSourceLoc(source) }}</span>
                      <span v-if="source.snippet" class="source-snippet">{{ truncateText(source.snippet, 120) }}</span>
                    </button>
                    <button
                      v-else
                      class="source-link"
                      type="button"
                      :disabled="!canPreviewSource(source)"
                      @click="openSourcePreview(source, getPreviewQuery(index))"
                    >
                      <span class="source-name">{{ source.file_name || '未知文档' }}</span>
                      <span v-if="getSourceLoc(source)" class="source-meta">{{ getSourceLoc(source) }}</span>
                    </button>
                  </li>
                </ul>
              </div>
              <div
                v-if="message.role === 'assistant' && message.disclaimers && message.disclaimers.length"
                class="disclaimer-list"
              >
                <div
                  v-for="(item, dIndex) in message.disclaimers"
                  :key="`${message.id || index}-disclaimer-${dIndex}`"
                  class="disclaimer-card"
                  :class="`disclaimer-${item.severity || 'warning'}`"
                >
                  <div class="disclaimer-title">{{ item.title }}</div>
                  <div class="disclaimer-body">{{ item.body }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="composer-stack">
          <div v-if="attachments.length" class="attachment-strip">
            <div v-for="att in attachments" :key="att.id" class="attachment-pill">
              <span>{{ att.file_name }}</span>
              <button type="button" @click="removeAttachment(att)">x</button>
            </div>
            <button type="button" class="ghost ghost-small" @click="clearAttachments">清空</button>
          </div>
          <div v-if="suggestionLoading || suggestions.length" class="suggestion-bar">
            <span class="suggestion-title">你可能要问</span>
            <div class="suggestion-list">
              <button
                v-for="(item, idx) in suggestions"
                :key="`${item}-${idx}`"
                type="button"
                class="suggestion-chip"
                @click="applySuggestion(item)"
              >
                {{ item }}
              </button>
              <span v-if="suggestionLoading" class="suggestion-loading">正在生成提示...</span>
            </div>
          </div>
          <div v-if="editingMessage" class="edit-banner">
            <span>正在编辑：{{ truncateText(editingMessage.content, 40) }}</span>
            <button type="button" class="ghost ghost-small" @click="cancelEdit">取消</button>
          </div>
          <form class="chat-input" @submit.prevent="sendMessage">
            <div class="input-wrap">
              <span v-if="knowledgeMode && selectedKnowledgeBase" class="mode-badge">
                知识库：{{ selectedKnowledgeBase.name }}
              </span>
              <textarea
                v-model="chatInput"
                :placeholder="inputPlaceholder"
                rows="1"
                @keydown="handleInputKeydown"
                ref="chatInputRef"
              ></textarea>
            </div>
            <div class="input-actions">
              <button type="button" class="tool-chip" @click="triggerAttachmentInput">
                <span class="material-symbols-outlined" aria-hidden="true">attach_file</span>
                <span>上传文件</span>
              </button>
              <button
                type="button"
                class="tool-chip"
                :class="{ active: deepThinkEnabled }"
                :disabled="knowledgeMode"
                title="更强推理与结构化回答"
                @click="deepThinkEnabled = !deepThinkEnabled"
              >
                <span class="material-symbols-outlined" aria-hidden="true">psychology</span>
                <span>深度思考</span>
              </button>
              <button
                type="button"
                class="tool-chip"
                :class="{ active: deepSearchEnabled }"
                :disabled="knowledgeMode"
                title="自动检索网页并附引用"
                @click="deepSearchEnabled = !deepSearchEnabled"
              >
                <span class="material-symbols-outlined" aria-hidden="true">travel_explore</span>
                <span>联网搜索</span>
              </button>
              <button type="button" class="tool-chip kb-chip" @click="openKnowledgeSelector">
                <span class="material-symbols-outlined" aria-hidden="true">database</span>
                <span>知识库问答</span>
              </button>
              <button type="submit" class="send-btn" :disabled="isStreaming">发送</button>
            </div>
            <input
              ref="attachmentInputRef"
              class="file-input"
              type="file"
              multiple
              accept=".pdf,.docx,.txt,.md,.png,.jpg,.jpeg"
              @change="handleAttachmentSelect"
            />
          </form>
        </div>
      </section>
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

    <Modal v-if="debugOpen" @close="closeDebug">
      <div class="debug-panel">
        <div class="debug-header">
          <h3>提示词调试</h3>
          <div v-if="debugSnapshot" class="debug-meta">
            <span>#{{ debugSnapshot.message_id }}</span>
            <span>模式：{{ debugSnapshot.mode }}</span>
            <span>{{ formatTime(debugSnapshot.created_at) }}</span>
          </div>
        </div>
        <div v-if="debugLoading" class="debug-loading">正在加载...</div>
        <div v-else-if="debugError" class="debug-error">{{ debugError }}</div>
        <div v-else-if="debugSnapshot" class="debug-body">
          <div class="debug-actions">
            <button type="button" class="ghost ghost-small" @click="copyDebugJson">复制 JSON</button>
            <button type="button" class="ghost ghost-small" @click="copyDebugSections">复制分段</button>
          </div>
          <div v-if="!debugSections.length" class="debug-empty">暂无调试信息。</div>
          <div v-for="section in debugSections" :key="section.key" class="debug-section">
            <div class="debug-section-header">
              <h4>{{ section.label }}</h4>
              <button type="button" class="ghost ghost-small" @click="copyDebugSection(section)">复制</button>
            </div>
            <pre class="debug-block"><code>{{ section.value }}</code></pre>
          </div>
        </div>
        <div v-else class="debug-empty">暂无调试信息。</div>
      </div>
    </Modal>

    <CenterToast :message="successMessage" />
  </div>
</template>

<script setup>
import { ref, computed, nextTick, reactive, onBeforeUnmount, onMounted, watch } from 'vue';
import { useRouter } from 'vue-router';
import { apiFetch, apiStream, clearTokens } from '../api/client.js';
import Modal from '../components/Modal.vue';
import CenterToast from '../components/CenterToast.vue';
import { useCenterToast } from '../composables/useCenterToast.js';

const router = useRouter();
const notice = ref('');
const error = ref('');
const { message: successMessage, show: showSuccess } = useCenterToast();

const sessions = ref([]);
const sessionQuery = ref('');
const showArchived = ref(true);
const sessionMenuId = ref(null);
const activeSessionId = ref(null);
const sessionTitle = ref('新对话');
const chatMessages = ref([]);
const editingMessageId = ref(null);
const previewOpen = ref(false);
const previewLoading = ref(false);
const previewError = ref('');
const previewData = ref(null);
const previewHtml = ref('');
let previewRequestId = 0;
const sessionTitleMap = ref({});
const chatInput = ref('');
const isStreaming = ref(false);
let streamController = null;
let pendingUserMessageId = null;
const highlightMessageId = ref(null);
const knowledgeBases = ref([]);
const knowledgeMode = ref(false);
const selectedKnowledgeBase = ref(null);
const showKnowledgeSelector = ref(false);
const chatLogRef = ref(null);
const chatInputRef = ref(null);
const sessionSearchRef = ref(null);
const attachments = ref([]);
const attachmentInputRef = ref(null);
const isDragging = ref(false);
const kbDocuments = ref([]);
const docLoading = ref(false);
const docError = ref('');
let docPollTimer = null;
let sessionSearchTimer = null;
const suggestions = ref([]);
const suggestionLoading = ref(false);
const suggestionError = ref('');
let suggestionTimer = null;
const memeGeneratingId = ref(null);
const deepThinkEnabled = ref(false);
const deepSearchEnabled = ref(false);
const isSuperuser = ref(false);
const currentUserEmail = ref(localStorage.getItem('chatUserEmail') || '');
const currentUsername = ref(localStorage.getItem('chatUsername') || '');
const profileAvatarUrl = ref(localStorage.getItem('chatUserAvatar') || '');
const isMobileLayout = ref(false);
const mobileSidebarOpen = ref(false);
const historyPanelOpen = ref(false);
const debugOpen = ref(false);
const debugLoading = ref(false);
const debugError = ref('');
const debugSnapshot = ref(null);
const debugMessageId = ref(null);
const messageHtmlCache = new WeakMap();
const sourceLocCache = new WeakMap();
const timeCache = new Map();
let sessionFetchRequestId = 0;
let suggestionFetchRequestId = 0;
const profileName = computed(() => {
  const username = String(currentUsername.value || '').trim();
  if (username) return username;
  const email = String(currentUserEmail.value || '').trim();
  if (email.includes('@')) return email.split('@')[0];
  return email || '用户';
});
const profileEmail = computed(() => String(currentUserEmail.value || '').trim() || '未获取邮箱');
const profileAvatarFallback = computed(() => {
  const source = profileName.value || '用户';
  return source.charAt(0);
});
const profileAvatarStyle = computed(() => {
  const avatar = String(profileAvatarUrl.value || '').trim();
  if (!avatar) return {};
  return {
    backgroundImage: `url("${avatar}")`,
  };
});
const inputPlaceholder = computed(() => {
  if (knowledgeMode.value && selectedKnowledgeBase.value) {
    return `向知识库「${selectedKnowledgeBase.value.name}」提问`;
  }
  return '输入问题，按回车发送';
});

const kbDocumentsPreview = computed(() => {
  const items = Array.isArray(kbDocuments.value) ? [...kbDocuments.value] : [];
  items.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  return items.slice(0, 3);
});

const editingMessage = computed(() =>
  chatMessages.value.find((message) => message.id === editingMessageId.value) || null,
);

const favoriteMessages = computed(() =>
  chatMessages.value.filter((message) => message.role === 'assistant' && message.is_favorite),
);

const previewQueryByMessageIndex = computed(() => {
  const queries = [];
  let latestUserQuery = '';
  for (let i = 0; i < chatMessages.value.length; i += 1) {
    queries[i] = latestUserQuery;
    const message = chatMessages.value[i];
    if (message && message.role === 'user' && message.content && message.content.trim()) {
      latestUserQuery = message.content.trim();
    }
  }
  return queries;
});

const debugSections = computed(() => {
  const payload = debugSnapshot.value?.payload || {};
  const sections = [];
  const pushSection = (key, label, value) => {
    if (value === undefined || value === null) return;
    if (typeof value === 'string' && !value.trim()) return;
    if (Array.isArray(value) && !value.length) return;
    sections.push({ key, label, value: formatDebugValue(value) });
  };
  pushSection('system_prompt', 'System Prompt', payload.system_prompt);
  pushSection('user_input', 'User Input', payload.user_input);
  pushSection('chat_history', 'History', payload.chat_history);
  pushSection('tools', 'Tools', payload.tools);
  pushSection('tool', 'Tool', payload.tool);
  pushSection('deep_search', 'Deep Search', payload.deep_search);
  pushSection('deep_think', 'Deep Think', payload.deep_think);
  pushSection('rag', 'RAG', payload.rag);
  pushSection('temp_context', 'Temp Context', payload.temp_context);
  pushSection('model_name', 'Model', payload.model_name);
  return sections;
});

const ATTACHMENT_EXTS = ['.pdf', '.docx', '.txt', '.md', '.png', '.jpg', '.jpeg'];
const MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024;
const MOBILE_LAYOUT_BREAKPOINT = 1080;

const setNotice = (message) => {
  showSuccess(message);
  notice.value = '';
  error.value = '';
};

const setError = (message) => {
  error.value = message;
  notice.value = '';
};

const syncStoredProfile = () => {
  const assistantAvatar = localStorage.getItem('chatAssistantAvatar') || '';
  const userAvatar = localStorage.getItem('chatUserAvatar') || '';
  profileAvatarUrl.value = userAvatar;

  if (assistantAvatar) {
    document.documentElement.style.setProperty('--chat-assistant-avatar-image', `url("${assistantAvatar}")`);
  } else {
    document.documentElement.style.removeProperty('--chat-assistant-avatar-image');
  }

  if (userAvatar) {
    document.documentElement.style.setProperty('--chat-user-avatar-image', `url("${userAvatar}")`);
  } else {
    document.documentElement.style.removeProperty('--chat-user-avatar-image');
  }
};

const handleProfileStorageChange = (event) => {
  const watchKeys = new Set(['chatUserAvatar', 'chatAssistantAvatar', 'chatUserEmail', 'chatUsername']);
  if (!event || !event.key || watchKeys.has(event.key)) {
    currentUserEmail.value = localStorage.getItem('chatUserEmail') || currentUserEmail.value;
    currentUsername.value = localStorage.getItem('chatUsername') || currentUsername.value;
    syncStoredProfile();
  }
};


const formatDebugValue = (value) => {
  if (value === undefined || value === null) return '';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const fetchCurrentUser = async () => {
  try {
    const data = await apiFetch('/users/me');
    isSuperuser.value = !!data?.is_superuser;
    currentUserEmail.value = String(data?.email || '').trim();
    currentUsername.value = String(data?.username || '').trim();
    if (currentUserEmail.value) {
      localStorage.setItem('chatUserEmail', currentUserEmail.value);
    } else {
      localStorage.removeItem('chatUserEmail');
    }
    if (currentUsername.value) {
      localStorage.setItem('chatUsername', currentUsername.value);
    } else {
      localStorage.removeItem('chatUsername');
    }
  } catch {
    isSuperuser.value = false;
    currentUserEmail.value = localStorage.getItem('chatUserEmail') || '';
    currentUsername.value = localStorage.getItem('chatUsername') || '';
  }
};


const truncateText = (text, length = 30) => {
  const value = String(text || '');
  if (value.length <= length) return value;
  return `${value.slice(0, length)}…`;
};

const scheduleSessionSearch = () => {
  if (sessionSearchTimer) {
    clearTimeout(sessionSearchTimer);
  }
  sessionSearchTimer = setTimeout(() => {
    fetchSessions();
  }, 300);
};

const focusSessionSearch = () => {
  historyPanelOpen.value = true;
  nextTick(() => {
    if (sessionSearchRef.value) {
      sessionSearchRef.value.focus();
    }
  });
};

const closeHistoryPanel = () => {
  historyPanelOpen.value = false;
};

const toggleHistoryPanel = () => {
  historyPanelOpen.value = !historyPanelOpen.value;
  if (historyPanelOpen.value) {
    nextTick(() => {
      sessionSearchRef.value?.focus();
    });
  }
};

const syncLayoutMode = () => {
  const isMobile = window.innerWidth <= MOBILE_LAYOUT_BREAKPOINT;
  isMobileLayout.value = isMobile;
  if (!isMobile) {
    mobileSidebarOpen.value = false;
  }
};

const toggleMobileSidebar = () => {
  if (!isMobileLayout.value) return;
  mobileSidebarOpen.value = !mobileSidebarOpen.value;
  if (!mobileSidebarOpen.value) {
    closeHistoryPanel();
  }
};

const closeMobileSidebar = () => {
  mobileSidebarOpen.value = false;
  closeHistoryPanel();
};

const syncBodyScrollLock = () => {
  if (typeof document === 'undefined') return;
  if (isMobileLayout.value && mobileSidebarOpen.value) {
    document.body.style.overflow = 'hidden';
  } else {
    document.body.style.overflow = '';
  }
};

const resizeInput = () => {
  const input = chatInputRef.value;
  if (!input) return;
  input.style.height = 'auto';
  input.style.height = `${Math.min(input.scrollHeight, 220)}px`;
};

const toggleArchivedView = () => {
  showArchived.value = !showArchived.value;
  fetchSessions();
};

const clearSuggestions = () => {
  suggestionFetchRequestId += 1;
  suggestions.value = [];
  suggestionError.value = '';
  suggestionLoading.value = false;
};

const fetchSuggestions = async () => {
  if (!activeSessionId.value) {
    clearSuggestions();
    return;
  }
  const meaningful = chatMessages.value.filter(
    (message) => message.role === 'user' || message.role === 'assistant',
  );
  if (meaningful.length < 2) {
    clearSuggestions();
    return;
  }
  suggestionFetchRequestId += 1;
  const requestId = suggestionFetchRequestId;
  suggestionLoading.value = true;
  suggestionError.value = '';
  try {
    const data = await apiFetch(`/chat/sessions/${activeSessionId.value}/suggestions`, {
      method: 'POST',
      body: { limit: 3 },
    });
    if (requestId !== suggestionFetchRequestId) return;
    suggestions.value = Array.isArray(data?.suggestions) ? data.suggestions : [];
  } catch (err) {
    if (requestId !== suggestionFetchRequestId) return;
    suggestionError.value = err.message || '获取提示失败';
    suggestions.value = [];
  } finally {
    if (requestId === suggestionFetchRequestId) {
      suggestionLoading.value = false;
    }
  }
};

const scheduleSuggestionRefresh = () => {
  if (suggestionTimer) {
    clearTimeout(suggestionTimer);
  }
  suggestionTimer = setTimeout(() => {
    fetchSuggestions();
  }, 300);
};

const applySuggestion = (text) => {
  if (!text) return;
  chatInput.value = text;
  nextTick(() => {
    if (chatInputRef.value) {
      chatInputRef.value.focus();
    }
  });
};

const handleCodeCopy = async (event) => {
  const target = event.target;
  if (!(target instanceof Element)) return;
  const cite = target.closest('.md-cite');
  if (cite) {
    const citeIndex = cite.getAttribute('data-cite');
    const messageEl = cite.closest('.chat-message');
    if (!citeIndex || !messageEl || !messageEl.id) return;
    const messageId = messageEl.id.replace('msg-', '');
    const sourceEl = document.getElementById(`source-${messageId}-${citeIndex}`);
    if (sourceEl) {
      sourceEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
    return;
  }
  const button = target.closest('.code-copy');
  if (!button) return;
  const encoded = button.getAttribute('data-code') || '';
  if (!encoded) return;
  const code = decodeURIComponent(encoded);
  try {
    await navigator.clipboard.writeText(code);
    setNotice('代码已复制');
  } catch (err) {
    setError('复制失败，请检查浏览器权限');
  }
};

const formatFileSize = (size) => {
  const bytes = Number(size || 0);
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(1)} GB`;
};

const scrollToMessage = (messageId) => {
  if (!messageId) return;
  nextTick(() => {
    const el = document.getElementById(`msg-${messageId}`);
    if (!el) return;
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    highlightMessageId.value = messageId;
    window.clearTimeout(scrollToMessage._timer);
    scrollToMessage._timer = window.setTimeout(() => {
      highlightMessageId.value = null;
    }, 1200);
  });
};

const toggleSessionMenu = (sessionId) => {
  sessionMenuId.value = sessionMenuId.value === sessionId ? null : sessionId;
};

const closeSessionMenu = () => {
  sessionMenuId.value = null;
};

const handleInputKeydown = (event) => {
  if (event.key === 'Enter' && !event.shiftKey) {
    event.preventDefault();
    sendMessage();
  }
};

const cancelEdit = () => {
  editingMessageId.value = null;
  chatInput.value = '';
};

const startEdit = (message) => {
  if (!message || message.role !== 'user') return;
  if (isStreaming.value) return;
  editingMessageId.value = message.id;
  chatInput.value = message.content || '';
};

const copyMessage = async (message) => {
  try {
    await navigator.clipboard.writeText(message?.content || '');
    setNotice('已复制到剪贴板');
  } catch (err) {
    setError('复制失败，请检查浏览器权限');
  }
};

const quoteMessage = (message) => {
  if (!message) return;
  const content = String(message.content || '').trim();
  if (!content) return;
  const clipped = content.length > 200 ? `${content.slice(0, 200)}…` : content;
  const quoted = clipped
    .split(/\r?\n/)
    .map((line) => `> ${line}`)
    .join('\n');
  chatInput.value = chatInput.value
    ? `${chatInput.value.trim()}\n\n${quoted}\n\n`
    : `${quoted}\n\n`;
};

const toggleFavorite = async (message) => {
  if (!message || message.role !== 'assistant') return;
  try {
    const data = await apiFetch(`/chat/messages/${message.id}/favorite`, {
      method: 'PATCH',
      body: { is_favorite: !message.is_favorite },
    });
    message.is_favorite = data.is_favorite;
    setNotice(message.is_favorite ? '已收藏' : '已取消收藏');
  } catch (err) {
    setError(`收藏操作失败：${err.message}`);
  }
};

const generateMeme = async (message) => {
  if (!message || message.role !== 'assistant') return;
  if (isStreaming.value) {
    setError('正在生成回复，请稍候');
    return;
  }
  if (memeGeneratingId.value) {
    setError('正在生成表情包，请稍候');
    return;
  }
  memeGeneratingId.value = message.id;

  const placeholder = reactive({
    id: `meme-${Date.now()}`,
    role: 'assistant',
    content: '',
    created_at: new Date().toISOString(),
    isLoading: true,
  });
  chatMessages.value.push(placeholder);
  scrollToBottom();

  try {
    const data = await apiFetch(`/chat/messages/${message.id}/meme`, { method: 'POST' });
    applyFinalMessage(placeholder, data);
  } catch (err) {
    placeholder.content = `表情包生成失败：${err.message}`;
    placeholder.isLoading = false;
    setError(`表情包生成失败：${err.message}`);
  } finally {
    memeGeneratingId.value = null;
    scrollToBottom();
  }
};

const openDebug = async (message) => {
  if (!message || !message.id) return;
  if (!isSuperuser.value) {
    setError('无权限查看调试信息');
    return;
  }
  debugOpen.value = true;
  debugLoading.value = true;
  debugError.value = '';
  debugSnapshot.value = null;
  debugMessageId.value = message.id;
  try {
    const data = await apiFetch(`/chat/messages/${message.id}/debug`);
    debugSnapshot.value = data;
  } catch (err) {
    debugError.value = err.message || '获取调试信息失败';
  } finally {
    debugLoading.value = false;
  }
};

const closeDebug = () => {
  debugOpen.value = false;
  debugLoading.value = false;
  debugError.value = '';
  debugSnapshot.value = null;
  debugMessageId.value = null;
};

const copyDebugText = async (text) => {
  if (!text) return;
  try {
    await navigator.clipboard.writeText(text);
    setNotice('已复制');
  } catch {
    setError('复制失败，请检查浏览器权限');
  }
};

const copyDebugJson = () => {
  if (!debugSnapshot.value) return;
  const text = JSON.stringify(debugSnapshot.value, null, 2);
  copyDebugText(text);
};

const copyDebugSections = () => {
  if (!debugSections.value.length) return;
  const text = debugSections.value
    .map((section) => `### ${section.label}\n${section.value}`)
    .join('\n\n');
  copyDebugText(text);
};

const copyDebugSection = (section) => {
  if (!section) return;
  copyDebugText(section.value);
};

const findMessageIndex = (messageId) =>
  chatMessages.value.findIndex((message) => message.id === messageId);

const truncateMessagesAfter = (messageId) => {
  const idx = findMessageIndex(messageId);
  if (idx === -1) return;
  chatMessages.value = chatMessages.value.slice(0, idx + 1);
};

const confirmOverwrite = (messageId) => {
  const idx = findMessageIndex(messageId);
  if (idx === -1) return true;
  if (idx < chatMessages.value.length - 1) {
    return window.confirm('该操作会删除这条消息之后的所有内容，是否继续？');
  }
  return true;
};

const findPreviousUserMessage = (startIndex) => {
  for (let i = startIndex - 1; i >= 0; i -= 1) {
    const message = chatMessages.value[i];
    if (message?.role === 'user') return message;
  }
  return null;
};

const goKnowledge = () => {
  router.push('/knowledge');
};

const goSettings = () => {
  router.push('/settings');
};

const goUsage = () => {
  router.push('/usage');
};

const goAiNews = () => {
  router.push('/ai-news');
};

const goMy = () => {
  router.push('/my');
};

const fetchKnowledgeBases = async () => {
  try {
    const data = await apiFetch('/knowledge/list');
    knowledgeBases.value = data || [];
  } catch (err) {
    setError(`获取知识库失败：${err.message}`);
  }
};

const fetchKbDocuments = async ({ silent = false } = {}) => {
  if (!selectedKnowledgeBase.value) {
    if (!silent) {
      docError.value = '请先选择知识库';
    }
    return;
  }
  if (!silent) {
    docLoading.value = true;
    docError.value = '';
  }
  try {
    const data = await apiFetch(`/knowledge/${selectedKnowledgeBase.value.id}/documents`);
    kbDocuments.value = Array.isArray(data) ? data : [];
    docError.value = '';
    updateDocPolling();
  } catch (err) {
    if (!silent) {
      docError.value = err.message || '加载失败';
    }
  } finally {
    if (!silent) {
      docLoading.value = false;
    }
  }
};

const hasProcessingDocs = () =>
  (kbDocuments.value || []).some((doc) => ['processing', 'uploading'].includes(doc.status));

const startDocPolling = () => {
  if (docPollTimer) return;
  docPollTimer = setInterval(() => {
    fetchKbDocuments({ silent: true });
  }, 3000);
};

const stopDocPolling = () => {
  if (!docPollTimer) return;
  clearInterval(docPollTimer);
  docPollTimer = null;
};

const updateDocPolling = () => {
  if (hasProcessingDocs()) {
    startDocPolling();
  } else {
    stopDocPolling();
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
  docError.value = '';
  docLoading.value = false;
  setNotice(`已进入知识库问答：${kb.name}`);
  fetchKbDocuments();
};

const exitKnowledgeMode = () => {
  knowledgeMode.value = false;
  selectedKnowledgeBase.value = null;
  kbDocuments.value = [];
  docError.value = '';
  docLoading.value = false;
  stopDocPolling();
  setNotice('已退出知识库问答');
};

const logout = () => {
  if (streamController) {
    streamController.abort();
    streamController = null;
    isStreaming.value = false;
  }
  stopDocPolling();
  clearTokens();
  router.push('/login');
};

const handleSessionMenuOutside = (event) => {
  const target = event.target;
  if (!(target instanceof Element)) return;
  if (target.closest('.session-menu') || target.closest('.session-menu-trigger')) {
    return;
  }
  if (!target.closest('.history-block')) {
    closeHistoryPanel();
  }
  closeSessionMenu();
};

const fetchMessages = async () => {
  if (!activeSessionId.value) {
    chatMessages.value = [];
    clearSuggestions();
    return;
  }
  try {
    const data = await apiFetch(`/chat/sessions/${activeSessionId.value}/messages`);
    chatMessages.value = (data || []).map((message) => ({
      ...message,
      isLoading: false,
    }));
    syncSessionTitle(activeSessionId.value, chatMessages.value);
    scrollToBottom();
    scheduleSuggestionRefresh();
  } catch (err) {
    setError(`获取消息失败：${err.message}`);
  }
};

const fetchSessions = async () => {
  sessionFetchRequestId += 1;
  const requestId = sessionFetchRequestId;
  try {
    const params = new URLSearchParams();
    const query = sessionQuery.value.trim();
    if (query) params.set('q', query);
    if (showArchived.value) params.set('include_archived', 'true');
    const qs = params.toString();
    const data = await apiFetch(`/chat/sessions${qs ? `?${qs}` : ''}`);
    if (requestId !== sessionFetchRequestId) return;
    sessions.value = data || [];
    if (!sessions.value.length && !showArchived.value && !query) {
      const fallback = await apiFetch('/chat/sessions?include_archived=true');
      if (requestId !== sessionFetchRequestId) return;
      if (Array.isArray(fallback) && fallback.length) {
        sessions.value = fallback;
        showArchived.value = true;
        setNotice('已显示归档会话');
      }
    }
    if (activeSessionId.value && !sessions.value.some((session) => session.id === activeSessionId.value)) {
      if (!showArchived.value) {
        activeSessionId.value = null;
        chatMessages.value = [];
        clearSuggestions();
      }
    }
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
    closeHistoryPanel();
    if (isMobileLayout.value) {
      closeMobileSidebar();
    }
    setNotice('会话创建成功');
  } catch (err) {
    setError(`创建会话失败：${err.message}`);
  }
};

const updateSessionRequest = async (sessionId, payload) => {
  const data = await apiFetch(`/chat/sessions/${sessionId}`, {
    method: 'PATCH',
    body: payload,
  });
  return data;
};

const renameSession = async (session) => {
  if (!session) return;
  const title = window.prompt('请输入新的会话标题', session.title || '');
  if (title === null) return;
  const trimmed = title.trim();
  if (!trimmed) return;
  try {
    const data = await updateSessionRequest(session.id, { title: trimmed });
    session.title = data.title;
    sessionTitleMap.value[session.id] = data.title;
    setNotice('会话已重命名');
    closeSessionMenu();
    await fetchSessions();
  } catch (err) {
    setError(`更新失败：${err.message}`);
  }
};

const togglePinSession = async (session) => {
  if (!session) return;
  try {
    const data = await updateSessionRequest(session.id, { is_pinned: !session.is_pinned });
    session.is_pinned = data.is_pinned;
    setNotice(data.is_pinned ? '已置顶会话' : '已取消置顶');
    closeSessionMenu();
    await fetchSessions();
  } catch (err) {
    setError(`更新失败：${err.message}`);
  }
};

const toggleArchiveSession = async (session) => {
  if (!session) return;
  try {
    const data = await updateSessionRequest(session.id, { is_archived: !session.is_archived });
    session.is_archived = data.is_archived;
    setNotice(data.is_archived ? '会话已归档' : '会话已取消归档');
    closeSessionMenu();
    await fetchSessions();
  } catch (err) {
    setError(`更新失败：${err.message}`);
  }
};

const editSessionTags = async (session) => {
  if (!session) return;
  const current = Array.isArray(session.tags) ? session.tags.join(', ') : '';
  const input = window.prompt('请输入标签，逗号分隔', current);
  if (input === null) return;
  const tags = input
    .split(',')
    .map((tag) => tag.trim())
    .filter(Boolean);
  try {
    const data = await updateSessionRequest(session.id, { tags });
    session.tags = data.tags || [];
    setNotice('标签已更新');
    closeSessionMenu();
    await fetchSessions();
  } catch (err) {
    setError(`更新失败：${err.message}`);
  }
};

const selectSession = async (sessionId) => {
  closeSessionMenu();
  activeSessionId.value = sessionId;
  await fetchMessages();
  closeHistoryPanel();
  if (isMobileLayout.value) {
    closeMobileSidebar();
  }
};



const downloadFile = (filename, content, type) => {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
};

const buildMarkdownExport = (session, messages) => {
  const title = session?.title || '会话导出';
  let md = `# ${title}\n\n`;
  for (const message of messages || []) {
    const roleLabel = message.role === 'user'
      ? '用户'
      : message.role === 'assistant'
        ? '助手'
        : message.role;
    md += `## ${roleLabel}\n\n`;
    md += `${message.content || ''}\n\n`;
  }
  return md.trim() + '\n';
};

const exportSession = async (session, format) => {
  if (!session) return;
  try {
    const messages = await apiFetch(`/chat/sessions/${session.id}/messages`);
    const safeName = (session.title || 'chat').replace(/[\\/:*?"<>|]/g, '_');
    if (format === 'md') {
      const content = buildMarkdownExport(session, messages || []);
      downloadFile(`${safeName}.md`, content, 'text/markdown;charset=utf-8');
    } else {
      const payload = {
        session: {
          id: session.id,
          title: session.title,
          is_pinned: session.is_pinned,
          is_archived: session.is_archived,
          tags: session.tags || [],
          created_at: session.created_at,
          updated_at: session.updated_at,
        },
        messages: (messages || []).map((message) => ({
          role: message.role,
          content: message.content,
          created_at: message.created_at,
        })),
      };
      downloadFile(`${safeName}.json`, JSON.stringify(payload, null, 2), 'application/json;charset=utf-8');
    }
    setNotice('导出已开始');
    closeSessionMenu();
  } catch (err) {
    setError(`导出失败：${err.message}`);
  }
};

const fetchAttachments = async () => {
  try {
    const data = await apiFetch('/chat/attachments');
    attachments.value = data || [];
  } catch (err) {
    setError(`获取临时资料失败：${err.message}`);
  }
};

const triggerAttachmentInput = () => {
  if (attachmentInputRef.value) {
    attachmentInputRef.value.click();
  }
};

const getFileExt = (name) => {
  const idx = name.lastIndexOf('.');
  if (idx === -1) return '';
  return name.slice(idx).toLowerCase();
};

const uploadAttachment = async (file) => {
  const ext = getFileExt(file.name || '');
  if (!ATTACHMENT_EXTS.includes(ext)) {
    setError(`不支持的文件类型：${ext || '未知'}`);
    return;
  }
  if (file.size > MAX_ATTACHMENT_SIZE) {
    setError('文件大小不能超过 10MB');
    return;
  }
  const formData = new FormData();
  formData.append('file', file);
  try {
    const data = await apiFetch('/chat/attachments/upload', {
      method: 'POST',
      body: formData,
      timeoutMs: 60000,
    });
    attachments.value = [data, ...attachments.value];
    setNotice('临时资料已上传');
  } catch (err) {
    setError(`上传失败：${err.message}`);
  }
};

const uploadFiles = async (files) => {
  for (const file of files) {
    await uploadAttachment(file);
  }
};

const handleAttachmentSelect = (event) => {
  const files = Array.from(event.target.files || []);
  if (!files.length) return;
  uploadFiles(files);
  event.target.value = '';
};

const removeAttachment = async (attachment) => {
  if (!attachment) return;
  try {
    await apiFetch(`/chat/attachments/${attachment.id}`, { method: 'DELETE' });
    attachments.value = attachments.value.filter((item) => item.id !== attachment.id);
    setNotice('已移除临时资料');
  } catch (err) {
    setError(`移除失败：${err.message}`);
  }
};

const clearAttachments = async () => {
  if (!attachments.value.length) return;
  const confirmed = window.confirm('确定清理所有临时资料吗？');
  if (!confirmed) return;
  const items = [...attachments.value];
  await Promise.allSettled(
    items.map((item) => apiFetch(`/chat/attachments/${item.id}`, { method: 'DELETE' })),
  );
  await fetchAttachments();
  setNotice('已清理临时资料');
};

const handleDragOver = (event) => {
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = 'copy';
  }
  isDragging.value = true;
};

const handleDragLeave = (event) => {
  if (event.currentTarget && event.relatedTarget && event.currentTarget.contains(event.relatedTarget)) {
    return;
  }
  isDragging.value = false;
};

const handleDrop = (event) => {
  isDragging.value = false;
  const files = Array.from(event.dataTransfer?.files || []);
  if (!files.length) return;
  uploadFiles(files);
};

const sendMessage = async () => {
  if (!chatInput.value.trim()) return;
  if (isStreaming.value) {
    setError('正在生成回复，请稍候');
    return;
  }

  if (editingMessageId.value) {
    const targetId = editingMessageId.value;
    if (!confirmOverwrite(targetId)) return;
    const idx = findMessageIndex(targetId);
    if (idx === -1) {
      cancelEdit();
      return;
    }
    const targetMessage = chatMessages.value[idx];
    const originalContent = targetMessage.content;
    targetMessage.content = chatInput.value.trim();
    targetMessage.edited_at = new Date().toISOString();
    truncateMessagesAfter(targetId);

    const assistantMessage = reactive({
      id: `stream-${Date.now()}`,
      role: 'assistant',
      content: '',
      created_at: new Date().toISOString(),
      isLoading: true,
      statusText: '',
    });
    chatMessages.value.push(assistantMessage);
    scrollToBottom();

    try {
      isStreaming.value = true;
      streamController = new AbortController();
      const inputText = chatInput.value.trim();
      chatInput.value = '';
      editingMessageId.value = null;
      let streamError = false;
      const handlePayload = (payload) => {
        if (!payload) return;
        if (typeof payload === 'object') {
          if (payload.event === 'stage') {
            assistantMessage.statusText = payload.message || '正在思考...';
            return;
          }
          if (payload.event === 'error') {
            streamError = true;
            const errMessage = payload.message || '生成失败';
            assistantMessage.content = `发送失败：${errMessage}`;
            assistantMessage.isLoading = false;
            setError(`发送失败：${errMessage}`);
            return;
          }
          if (payload.event === 'done' && payload.message) {
            applyFinalMessage(assistantMessage, payload.message);
            return;
          }
          if (typeof payload.content === 'string') {
            assistantMessage.content += payload.content;
            scrollToBottom();
          }
          return;
        }
        if (typeof payload === 'string') {
          assistantMessage.content += payload;
          scrollToBottom();
        }
      };

      await apiStream(`/chat/messages/${targetId}/resend/stream`, {
        method: 'POST',
        body: {
          message: inputText,
          deep_search: deepSearchEnabled.value && !knowledgeMode.value,
          deep_think: deepThinkEnabled.value && !knowledgeMode.value,
        },
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
        assistantMessage.content = `发送失败：${err.message}`;
        setError(`发送失败：${err.message}`);
      }
      assistantMessage.isLoading = false;
      targetMessage.content = originalContent;
      await fetchMessages();
    } finally {
      isStreaming.value = false;
      streamController = null;
      scrollToBottom();
    }
    return;
  }

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

  const inputText = chatInput.value.trim();
  const userMessage = {
    id: Date.now(),
    role: 'user',
    content: inputText,
    created_at: new Date().toISOString(),
  };
  pendingUserMessageId = userMessage.id;
  chatMessages.value.push(userMessage);
  syncSessionTitle(activeSessionId.value, chatMessages.value);
  scrollToBottom();

  const assistantMessage = reactive({
    id: `stream-${Date.now()}`,
    role: 'assistant',
    content: '',
    created_at: new Date().toISOString(),
    isLoading: true,
    statusText: '',
  });
  chatMessages.value.push(assistantMessage);
  scrollToBottom();

  try {
    isStreaming.value = true;
    streamController = new AbortController();
    chatInput.value = '';
    let streamError = false;
    const handlePayload = (payload) => {
      if (!payload) return;
      if (typeof payload === 'object') {
        if (payload.event === 'stage') {
          assistantMessage.statusText = payload.message || '正在思考...';
          return;
        }
        if (payload.event === 'error') {
          streamError = true;
          const errMessage = payload.message || '生成失败';
          assistantMessage.content = `发送失败：${errMessage}`;
          assistantMessage.isLoading = false;
          setError(`发送失败：${errMessage}`);
          return;
        }
        if (payload.event === 'done' && payload.message) {
          applyFinalMessage(assistantMessage, payload.message);
          if (payload.user_message_id && pendingUserMessageId) {
            const pending = chatMessages.value.find(
              (message) => message.id === pendingUserMessageId,
            );
            if (pending) {
              pending.id = payload.user_message_id;
            }
            pendingUserMessageId = null;
          }
          return;
        }
        if (typeof payload.content === 'string') {
          assistantMessage.content += payload.content;
          scrollToBottom();
        }
        return;
      }
      if (typeof payload === 'string') {
        assistantMessage.content += payload;
        scrollToBottom();
      }
      };

    if (knowledgeMode.value && selectedKnowledgeBase.value) {
      await apiStream('/chat/knowledge/stream', {
        method: 'POST',
        body: {
          kb_id: selectedKnowledgeBase.value.id,
          message: inputText,
          session_id: activeSessionId.value,
        },
        signal: streamController.signal,
        onMessage: handlePayload,
      });
    } else {
      await apiStream(`/chat/sessions/${activeSessionId.value}/stream`, {
        method: 'POST',
        body: {
          message: inputText,
          deep_search: deepSearchEnabled.value && !knowledgeMode.value,
          deep_think: deepThinkEnabled.value && !knowledgeMode.value,
        },
        signal: streamController.signal,
        onMessage: handlePayload,
      });
    }
    if (assistantMessage.isLoading) {
      assistantMessage.isLoading = false;
    }
    if (!streamError && !assistantMessage.content) {
      assistantMessage.content = '未收到回复，请稍后重试。';
      setError('未收到回复，请稍后重试。');
    }
  } catch (err) {
    if (err.message !== '请求已取消') {
      assistantMessage.content = `发送失败：${err.message}`;
      setError(`发送失败：${err.message}`);
    }
    assistantMessage.isLoading = false;
    await fetchMessages();
  } finally {
    isStreaming.value = false;
    streamController = null;
    scrollToBottom();
  }
};

const regenerateMessage = async (message) => {
  if (!message || message.role !== 'assistant') return;
  if (isStreaming.value) {
    setError('正在生成回复，请稍候');
    return;
  }
  const idx = findMessageIndex(message.id);
  if (idx === -1) return;
  const userMessage = findPreviousUserMessage(idx);
  if (!userMessage) {
    setError('未找到对应的用户消息');
    return;
  }
  if (!confirmOverwrite(userMessage.id)) return;
  truncateMessagesAfter(userMessage.id);

  const assistantMessage = reactive({
    id: `stream-${Date.now()}`,
    role: 'assistant',
    content: '',
    created_at: new Date().toISOString(),
    isLoading: true,
    statusText: '',
  });
  chatMessages.value.push(assistantMessage);
  scrollToBottom();

  try {
    isStreaming.value = true;
    streamController = new AbortController();
    let streamError = false;
    const handlePayload = (payload) => {
      if (!payload) return;
      if (typeof payload === 'object') {
        if (payload.event === 'stage') {
          assistantMessage.statusText = payload.message || '正在思考...';
          return;
        }
        if (payload.event === 'error') {
          streamError = true;
          const errMessage = payload.message || '生成失败';
          assistantMessage.content = `发送失败：${errMessage}`;
          assistantMessage.isLoading = false;
          setError(`发送失败：${errMessage}`);
          return;
        }
        if (payload.event === 'done' && payload.message) {
          applyFinalMessage(assistantMessage, payload.message);
          return;
        }
        if (typeof payload.content === 'string') {
          assistantMessage.content += payload.content;
          scrollToBottom();
        }
        return;
      }
      if (typeof payload === 'string') {
        assistantMessage.content += payload;
        scrollToBottom();
      }
    };

    await apiStream(`/chat/messages/${message.id}/regenerate/stream`, {
      method: 'POST',
      body: {
        deep_search: deepSearchEnabled.value && !knowledgeMode.value,
        deep_think: deepThinkEnabled.value && !knowledgeMode.value,
      },
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
      assistantMessage.content = `发送失败：${err.message}`;
      setError(`发送失败：${err.message}`);
    }
    assistantMessage.isLoading = false;
  } finally {
    isStreaming.value = false;
    streamController = null;
    pendingUserMessageId = null;
    scrollToBottom();
  }
};

const MAX_TIME_CACHE_SIZE = 500;

const formatTimeCached = (time) => {
  if (!time) return '';
  const key = String(time);
  if (timeCache.has(key)) {
    return timeCache.get(key);
  }
  const value = new Date(key).toLocaleString();
  if (timeCache.size >= MAX_TIME_CACHE_SIZE) {
    const firstKey = timeCache.keys().next().value;
    if (firstKey !== undefined) {
      timeCache.delete(firstKey);
    }
  }
  timeCache.set(key, value);
  return value;
};

const formatTime = formatTimeCached;

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
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\[(\d+)\]/g, '<sup class="md-cite" data-cite="$1">[$1]</sup>');

const getApiRoot = () => window.location.origin;

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

const formatMessage = (raw, role = 'assistant') => {
  if (!raw) return '';
  const rawLines = mergeImageLines(String(raw).split(/\r?\n/));
  let html = '';
  let inList = false;
  let inQuote = false;
  let inCode = false;
  let codeLang = '';
  let codeLines = [];

  const closeList = () => {
    if (inList) {
      html += '</ul>';
      inList = false;
    }
  };

  const closeQuote = () => {
    if (inQuote) {
      html += '</blockquote>';
      inQuote = false;
    }
  };

  const flushCode = () => {
    if (!inCode) return;
    const rawCode = codeLines.join('\n');
    const escapedCode = escapeHtml(rawCode);
    const safeLang = escapeHtml(codeLang || 'code');
    const encoded = encodeURIComponent(rawCode);
    const copyButton = role === 'assistant'
      ? `<button type="button" class="code-copy" data-code="${encoded}">复制</button>`
      : '';
    html += `<div class="md-code">`;
    html += `<div class="code-header"><span class="code-lang">${safeLang}</span>${copyButton}</div>`;
    html += `<pre><code>${escapedCode}</code></pre>`;
    html += `</div>`;
    inCode = false;
    codeLang = '';
    codeLines = [];
  };

  for (const rawLine of rawLines) {
    const rawTrimmed = rawLine.trim();
    if (rawTrimmed.startsWith('```')) {
      closeList();
      closeQuote();
      if (inCode) {
        flushCode();
      } else {
        inCode = true;
        codeLang = rawTrimmed.slice(3).trim();
        codeLines = [];
      }
      continue;
    }

    if (inCode) {
      codeLines.push(rawLine);
      continue;
    }

    if (/^[-*•·]\s+/.test(rawTrimmed)) {
      if (!inList) {
        html += '<ul class="md-list">';
        inList = true;
      }
      const itemRaw = rawTrimmed.replace(/^[-*•·]\s+/, '');
      const itemText = formatInline(formatListLabel(escapeHtml(itemRaw)));
      html += `<li>${itemText}</li>`;
      continue;
    }

    closeList();

    const imageMatch = rawTrimmed.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
    if (imageMatch) {
      closeQuote();
      const altText = escapeHtml(imageMatch[1] || 'image');
      const resolvedUrl = resolveMediaUrl(imageMatch[2]);
      const safeUrl = escapeHtml(resolvedUrl);
      html += `<div class="md-image"><img class="chat-image" src="${safeUrl}" alt="${altText}" loading="lazy" /></div>`;
      continue;
    }

    if (/^>\s*/.test(rawTrimmed)) {
      if (!inQuote) {
        html += '<blockquote class="md-quote">';
        inQuote = true;
      }
      const quoteRaw = rawTrimmed.replace(/^>\s?/, '');
      html += `<div>${formatInline(escapeHtml(quoteRaw))}</div>`;
      continue;
    }

    closeQuote();

    if (isEmojiHeading(rawTrimmed)) {
      html += `<div class="md-emoji-heading">${formatInline(escapeHtml(rawTrimmed))}</div>`;
      continue;
    }

    const headingMatch = rawTrimmed.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      const level = headingMatch[1].length;
      html += `<div class="md-heading h${level}">${formatInline(escapeHtml(headingMatch[2]))}</div>`;
      continue;
    }

    if (!rawTrimmed) {
      closeQuote();
      html += '<div class="md-blank"></div>';
      continue;
    }

    html += `<div class="md-line">${formatInline(escapeHtml(rawTrimmed))}</div>`;
  }

  closeList();
  closeQuote();
  flushCode();
  return html;
};

const getFormattedMessage = (message) => {
  if (!message) return '';
  const content = String(message.content || '');
  const role = message.role || 'assistant';
  const cached = messageHtmlCache.get(message);
  if (cached && cached.content === content && cached.role === role) {
    return cached.html;
  }
  const html = formatMessage(content, role);
  messageHtmlCache.set(message, { content, role, html });
  return html;
};

const formatSourceLoc = (source) => {
  if (!source) return '';
  if (source.url && !source.doc_id) {
    try {
      const host = new URL(source.url).hostname.replace(/^www\./, '');
      return host || '网页';
    } catch {
      return '网页';
    }
  }
  const parts = [];
  if (source.md_headings) parts.push(source.md_headings);
  if (source.pages && source.pages.length) parts.push(`页 ${source.pages.join(',')}`);
  if (source.slides && source.slides.length) parts.push(`幻灯片 ${source.slides.join(',')}`);
  if (source.paragraphs && source.paragraphs.length) parts.push(`段落 ${source.paragraphs.join(',')}`);
  if (source.tables && source.tables.length) parts.push(`表格 ${source.tables.join(',')}`);
  if (source.chunk_index !== undefined && source.chunk_index !== null) {
    parts.push(`Chunk ${source.chunk_index}`);
  } else if (source.chunk_id !== undefined && source.chunk_id !== null) {
    parts.push(`片段 #${source.chunk_id}`);
  }
  return parts.join(' · ');
};

const getSourceLoc = (source) => {
  if (!source || typeof source !== 'object') return '';
  if (sourceLocCache.has(source)) {
    return sourceLocCache.get(source);
  }
  const value = formatSourceLoc(source);
  sourceLocCache.set(source, value);
  return value;
};

const canPreviewSource = (source) =>
  source &&
  source.doc_id !== undefined &&
  source.doc_id !== null &&
  (
    (source.chunk_id !== undefined && source.chunk_id !== null) ||
    (source.chunk_index !== undefined && source.chunk_index !== null)
  );

const openWebSource = (source) => {
  if (!source || !source.url) return;
  window.open(source.url, '_blank', 'noopener');
};

const getPreviewQuery = (index) => previewQueryByMessageIndex.value[index] || '';

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
    const hasChunkId = source.chunk_id !== undefined && source.chunk_id !== null;
    const previewPath = hasChunkId
      ? `/knowledge/documents/${source.doc_id}/chunks/by-id/${source.chunk_id}`
      : `/knowledge/documents/${source.doc_id}/chunks/${source.chunk_index}`;
    const data = await apiFetch(previewPath);
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
    await fetchKbDocuments({ silent: true });
  } catch (err) {
    setError(`重建失败：${err.message}`);
  }
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
  if (finalMessage.disclaimers !== undefined) {
    targetMessage.disclaimers = finalMessage.disclaimers;
  }
  if (finalMessage.risk_tags !== undefined) {
    targetMessage.risk_tags = finalMessage.risk_tags;
  }
  if (finalMessage.is_favorite !== undefined) {
    targetMessage.is_favorite = finalMessage.is_favorite;
  }
  if (finalMessage.edited_at !== undefined) {
    targetMessage.edited_at = finalMessage.edited_at;
  }
  targetMessage.isLoading = false;
  targetMessage.statusText = '';
  scrollToBottom();
  scheduleSuggestionRefresh();
};

const deleteSession = async (sessionId) => {
  closeSessionMenu();
  const confirmed = window.confirm('您确定要删除吗？');
  if (!confirmed) return;
  try {
    await apiFetch(`/chat/sessions/${sessionId}`, { method: 'DELETE' });
    sessions.value = sessions.value.filter((session) => session.id !== sessionId);
    if (activeSessionId.value === sessionId) {
      activeSessionId.value = null;
      chatMessages.value = [];
      clearSuggestions();
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

onMounted(() => {
  syncStoredProfile();
  fetchCurrentUser();
  fetchSessions();
  fetchAttachments();
  syncLayoutMode();
  syncBodyScrollLock();
  document.addEventListener('click', handleSessionMenuOutside);
  window.addEventListener('resize', syncLayoutMode);
  window.addEventListener('storage', handleProfileStorageChange);
  if (chatLogRef.value) {
    chatLogRef.value.addEventListener('click', handleCodeCopy);
  }
  nextTick(() => {
    resizeInput();
  });
});

watch(knowledgeMode, (value) => {
  if (value) {
    deepSearchEnabled.value = false;
    deepThinkEnabled.value = false;
  }
});

watch(chatInput, () => {
  nextTick(() => {
    resizeInput();
  });
});

watch([mobileSidebarOpen, isMobileLayout], () => {
  syncBodyScrollLock();
});

onBeforeUnmount(() => {
  stopDocPolling();
  if (streamController) {
    streamController.abort();
    streamController = null;
  }
  sessionFetchRequestId += 1;
  suggestionFetchRequestId += 1;
  previewRequestId += 1;
  window.clearTimeout(scrollToMessage._timer);
  if (sessionSearchTimer) {
    clearTimeout(sessionSearchTimer);
  }
  if (suggestionTimer) {
    clearTimeout(suggestionTimer);
  }
  window.removeEventListener('resize', syncLayoutMode);
  window.removeEventListener('storage', handleProfileStorageChange);
  document.body.style.overflow = '';
  document.removeEventListener('click', handleSessionMenuOutside);
  if (chatLogRef.value) {
    chatLogRef.value.removeEventListener('click', handleCodeCopy);
  }
});
</script>

<style scoped>
@import url("https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Noto+Sans+SC:wght@400;500;600;700;800&display=swap");
@import url("https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap");

.chat-layout {
  position: fixed;
  inset: 0;
  width: 100vw;
  height: 100vh;
  max-width: none;
  max-height: none;
  display: grid;
  grid-template-columns: 252px 1fr;
  gap: 16px;
  padding: clamp(10px, 1.6vw, 18px);
  isolation: isolate;
  background:
    radial-gradient(1200px circle at 8% 8%, rgba(56, 189, 248, 0.15), transparent 56%),
    radial-gradient(1000px circle at 92% 12%, rgba(99, 102, 241, 0.14), transparent 52%),
    linear-gradient(180deg, #f7f8fb 0%, #f2f4f8 100%);
  font-family: var(--font-sans);
  color: var(--text-strong);
  margin: 0;
  border-radius: 0;
  border: none;
  box-shadow: none;
  overflow: hidden;
}

.chat-layout::before {
  content: "";
  position: absolute;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background:
    linear-gradient(90deg, rgba(255, 255, 255, 0.54) 0%, rgba(255, 255, 255, 0) 28%),
    radial-gradient(900px circle at 88% 90%, rgba(148, 163, 184, 0.12), transparent 70%);
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
  border-radius: var(--radius-lg);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.93) 0%, rgba(248, 250, 252, 0.92) 100%);
  box-shadow: 0 18px 38px rgba(15, 23, 42, 0.08);
  border: 1px solid rgba(203, 213, 225, 0.75);
  backdrop-filter: blur(12px);
  height: 100%;
  min-height: 0;
  max-height: none;
  overflow: hidden;
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 14px;
  border-bottom: 1px solid rgba(203, 213, 225, 0.75);
}

.brand-icon {
  width: 42px;
  height: 42px;
  border-radius: 12px;
  background: var(--accent-gradient);
  color: #fff;
  display: grid;
  place-items: center;
  font-weight: 700;
  letter-spacing: 0.5px;
  box-shadow: 0 10px 20px rgba(59, 130, 246, 0.26);
}

.brand-title {
  font-size: 18px;
  font-weight: 700;
}

.brand-subtitle {
  font-size: 12px;
  color: var(--text-soft);
}

.sidebar-header {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 18px 0;
}

.sidebar-section h3 {
  font-size: 12px;
  color: #6b7280;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-bottom: 10px;
}

.sidebar-section {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.sidebar-menu {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 8px 0 12px;
}

.sidebar-menu.compact {
  padding: 0 0 10px;
}

.menu-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 10px;
  border-radius: 11px;
  border: none;
  background: rgba(255, 255, 255, 0.7);
  color: #1f2937;
  font-size: 13px;
  font-weight: 600;
  box-shadow: inset 0 0 0 1px rgba(203, 213, 225, 0.8);
  cursor: pointer;
  transition: background 0.2s ease, transform 0.2s ease, box-shadow 0.2s ease;
}

.menu-item:hover {
  background: rgba(255, 255, 255, 0.96);
  box-shadow: inset 0 0 0 1px rgba(148, 163, 184, 0.75);
  transform: translateY(-1px);
}

.menu-item.ghost {
  background: rgba(255, 255, 255, 0.9);
}

.menu-icon {
  width: 20px;
  height: 20px;
  border-radius: 6px;
  border: 1px solid rgba(148, 163, 184, 0.45);
  background: rgba(255, 255, 255, 0.85);
  display: grid;
  place-items: center;
  font-size: 12px;
  color: var(--text-muted);
}

.menu-icon::before {
  content: attr(data-icon);
  font-weight: 700;
}

.sidebar-extra-spacer {
  margin-top: auto;
}

.workspace-meta {
  width: min(100%, 1080px);
  margin: 0 auto 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: #94a3b8;
  letter-spacing: 0.02em;
}

.workspace-label {
  font-weight: 700;
  color: #64748b;
}

.workspace-sep {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: #cbd5e1;
}

.workspace-status {
  color: #475569;
}

.chat-main-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  width: min(100%, 1080px);
  margin: 0 auto;
  padding: 8px 10px;
  border-radius: 14px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(8px);
}

.chat-main-actions .ghost {
  box-shadow: none;
  padding: 6px 12px;
  font-size: 12px;
  border-radius: 999px;
  border-color: rgba(203, 213, 225, 0.85);
  background: rgba(248, 250, 252, 0.9);
}

.chat-main-actions .ghost:hover:not(:disabled) {
  background: rgba(255, 255, 255, 0.98);
}

.session-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 10px 10px 8px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.82);
  border: 1px solid rgba(203, 213, 225, 0.72);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.75);
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

.session-filter input {
  width: 100%;
  border: 1px solid rgba(203, 213, 225, 0.82);
  background: rgba(248, 250, 252, 0.92);
  color: #111827;
  border-radius: 10px;
  padding: 8px 10px;
  font-size: 12px;
  outline: none;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.session-filter input:focus {
  border-color: rgba(59, 130, 246, 0.55);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.14);
  background: #fff;
}

.session-empty {
  font-size: 12px;
  color: #94a3b8;
  padding: 10px 6px;
}

.ghost-small {
  padding: 6px 10px;
  font-size: 12px;
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
  scrollbar-gutter: stable;
}

.session-list li {
  display: flex;
  align-items: center;
  gap: 8px;
  position: relative;
  padding: 6px;
  border-radius: 12px;
  background: transparent;
  transition: background 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.session-list li.active {
  background: rgba(59, 130, 246, 0.11);
  box-shadow: inset 0 0 0 1px rgba(59, 130, 246, 0.3);
}

.session-list li:hover {
  background: rgba(241, 245, 249, 0.95);
}

.session-entry {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 4px 8px;
  align-items: center;
  text-align: left;
  padding: 4px 2px;
}

.session-list button {
  border: none;
  background: transparent;
  cursor: pointer;
  color: inherit;
  font-size: 13px;
}

.session-list .session-title {
  display: inline-block;
  max-width: 132px;
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-flag {
  justify-self: end;
  border-radius: 999px;
  padding: 1px 7px;
  font-size: 11px;
  line-height: 1.6;
  color: #1d4ed8;
  background: rgba(191, 219, 254, 0.7);
}

.session-flag.archived {
  color: #475569;
  background: rgba(226, 232, 240, 0.9);
}

.session-tags {
  grid-column: 1 / -1;
  display: flex;
  gap: 5px;
  flex-wrap: wrap;
}

.session-tag {
  border-radius: 999px;
  padding: 1px 6px;
  font-size: 10px;
  color: #475569;
  background: rgba(241, 245, 249, 0.95);
  border: 1px solid rgba(203, 213, 225, 0.8);
}

.session-menu-trigger {
  width: 24px;
  height: 24px;
  border-radius: 8px;
  font-size: 15px;
  line-height: 1;
  color: #64748b;
  opacity: 0;
  transform: translateY(2px);
  transition: opacity 0.2s ease, transform 0.2s ease, background 0.2s ease;
}

.session-list li:hover .session-menu-trigger,
.session-list li.active .session-menu-trigger {
  opacity: 1;
  transform: translateY(0);
}

.session-menu-trigger:hover {
  background: rgba(226, 232, 240, 0.9);
}

.delete-session {
  margin-left: auto;
  font-size: 12px;
  color: #c24164;
  border-radius: 8px;
  padding: 4px 7px;
  opacity: 0;
  transform: translateY(2px);
  transition: opacity 0.2s ease, transform 0.2s ease, background 0.2s ease;
}

.session-list li:hover .delete-session,
.session-list li.active .delete-session {
  opacity: 1;
  transform: translateY(0);
}

.delete-session:hover {
  background: rgba(254, 226, 226, 0.9);
}

.session-menu {
  position: absolute;
  right: 8px;
  top: calc(100% - 2px);
  z-index: 5;
  display: grid;
  gap: 4px;
  min-width: 148px;
  padding: 6px;
  border-radius: 11px;
  border: 1px solid rgba(203, 213, 225, 0.85);
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 14px 28px rgba(15, 23, 42, 0.14);
}

.session-menu button {
  text-align: left;
  border-radius: 8px;
  padding: 6px 8px;
  font-size: 12px;
  color: #334155;
}

.session-menu button:hover {
  background: rgba(241, 245, 249, 0.95);
}

.ghost {
  border: 1px solid rgba(203, 213, 225, 0.82);
  background: rgba(255, 255, 255, 0.9);
  color: #334155;
  border-radius: 12px;
  padding: 8px 12px;
  cursor: pointer;
  transition: background 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}

.ghost:hover:not(:disabled) {
  background: #fff;
  border-color: rgba(148, 163, 184, 0.86);
  transform: translateY(-1px);
}

.status-pill {
  padding: 2px 8px;
  border-radius: 999px;
  font-weight: 600;
  font-size: 11px;
  background: rgba(148, 163, 184, 0.2);
  color: #475569;
}

.status-pill.status-processing,
.status-pill.status-uploading {
  background: rgba(59, 130, 246, 0.18);
  color: #1d4ed8;
}

.status-pill.status-completed {
  background: rgba(34, 197, 94, 0.18);
  color: #15803d;
}

.status-pill.status-failed {
  background: rgba(239, 68, 68, 0.18);
  color: #b91c1c;
}

.doc-progress {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #6b7390;
}

.progress-bar {
  flex: 1;
  height: 6px;
  border-radius: 999px;
  background: rgba(99, 102, 241, 0.18);
  overflow: hidden;
  position: relative;
}

.progress-fill {
  height: 100%;
  width: 0%;
  background: linear-gradient(90deg, #6366f1, #8b5cf6);
  transition: width 0.4s ease;
}

.progress-bar.indeterminate .progress-fill {
  width: 40%;
  position: absolute;
  animation: progress-move 1.2s ease-in-out infinite;
}

.doc-error {
  font-size: 12px;
  color: #b91c1c;
  background: rgba(254, 226, 226, 0.6);
  padding: 6px 8px;
  border-radius: 8px;
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
  padding: 16px 18px 18px;
  border-radius: 26px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.96) 0%, rgba(250, 251, 253, 0.97) 100%);
  box-shadow: 0 24px 54px rgba(15, 23, 42, 0.1);
  border: 1px solid rgba(203, 213, 225, 0.76);
  min-height: 0;
  height: 100%;
  overflow: hidden;
}

.chat-topbar {
  display: flex;
  justify-content: flex-end;
  align-items: flex-start;
  gap: 16px;
}

.sidebar-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sidebar-actions button {
  width: 100%;
}

.chat-topbar h1 {
  margin: 0;
  font-size: 26px;
}

.chat-topbar p {
  margin: 6px 0 0;
  color: #6a728d;
}

.header-actions {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: flex-end;
}

.header-actions input {
  width: 280px;
}

.notice,
.error {
  margin: 16px 0 0;
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 13px;
  width: min(100%, 1080px);
  margin-left: auto;
  margin-right: auto;
}

.notice {
  background: var(--notice-bg);
  color: var(--notice-text);
}

.error {
  background: var(--error-bg);
  color: var(--error-text);
}

.chat-panel {
  margin-top: 10px;
  background: rgba(255, 255, 255, 0.84);
  border-radius: 22px;
  padding: 16px 18px;
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 14px;
  flex: 1;
  min-height: 0;
  border: 1px solid rgba(203, 213, 225, 0.7);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.82);
  overflow: hidden;
  max-height: none;
}

.chat-log {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  width: min(100%, 1060px);
  margin: 0 auto;
  padding: 6px 4px 10px;
  scrollbar-gutter: stable;
}

.chat-log::-webkit-scrollbar,
.session-list::-webkit-scrollbar {
  width: 8px;
}

.chat-log::-webkit-scrollbar-thumb,
.session-list::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.45);
  border-radius: 999px;
}

.empty-state {
  max-width: 820px;
  margin: 28px auto 0;
  background: rgba(248, 250, 252, 0.92);
  border-radius: 20px;
  padding: clamp(28px, 4vw, 44px) clamp(20px, 5vw, 46px);
  text-align: center;
  box-shadow: inset 0 0 0 1px rgba(203, 213, 225, 0.72);
}

.empty-state h2 {
  font-size: clamp(24px, 3.2vw, 36px);
  font-weight: 700;
  line-height: 1.3;
  margin: 0 auto 10px;
  max-width: 720px;
  color: #0f172a;
  letter-spacing: -0.01em;
}

.empty-state p {
  color: #64748b;
  margin: 0;
  font-size: 14px;
}

.empty-actions {
  margin-top: 18px;
  display: flex;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
}

.empty-chip {
  border: 1px solid rgba(203, 213, 225, 0.88);
  background: rgba(255, 255, 255, 0.94);
  color: #334155;
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}

.empty-chip:hover {
  transform: translateY(-1px);
  border-color: rgba(59, 130, 246, 0.45);
  box-shadow: 0 10px 20px rgba(59, 130, 246, 0.12);
}

.chat-message {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  margin-bottom: 16px;
  animation: message-enter 0.22s ease both;
}

.chat-message.highlight .chat-bubble {
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.34);
}

.chat-message.user {
  flex-direction: row-reverse;
}

.avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  flex-shrink: 0;
  position: relative;
  box-shadow: 0 6px 14px rgba(15, 23, 42, 0.16);
}

.avatar::after {
  content: "";
  position: absolute;
  inset: 3px;
  border-radius: 50%;
  border: 1px solid rgba(255, 255, 255, 0.7);
}

.assistant-avatar {
  background-image: var(--chat-assistant-avatar-image, none), var(--chat-assistant-avatar-bg);
  background-size: cover, cover;
  background-position: center, center;
}

.user-avatar {
  background-image: var(--chat-user-avatar-image, none), var(--chat-user-avatar-bg);
  background-size: cover, cover;
  background-position: center, center;
}

.chat-bubble {
  max-width: min(82%, 860px);
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.96);
  color: #111827;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.05);
  border: 1px solid rgba(226, 232, 240, 0.9);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.chat-message.user .chat-bubble {
  background: linear-gradient(135deg, #5ea8ff 0%, #5a7bff 100%);
  color: #fff;
  border-color: transparent;
  box-shadow: 0 10px 24px rgba(59, 130, 246, 0.28);
}

.bubble-meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: 11px;
  color: #94a3b8;
}

.chat-message.user .bubble-meta {
  justify-content: flex-end;
  gap: 8px;
  color: rgba(255, 255, 255, 0.86);
}

.chat-bubble strong {
  font-weight: 600;
}

.chat-bubble p {
  margin: 0;
  line-height: 1.55;
}

.message-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  opacity: 0;
  transform: translateY(2px);
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.chat-message:hover .message-actions {
  opacity: 1;
  transform: translateY(0);
}

.message-actions .ghost-small {
  border-radius: 999px;
  padding: 5px 10px;
  font-size: 11px;
}

.message-content {
  line-height: 1.6;
  word-break: break-word;
}

.message-content :deep(.md-image) {
  margin: 8px 0;
  display: flex;
  justify-content: flex-start;
  max-width: 360px;
  width: 100%;
  background: #fff;
  border-radius: 12px;
  padding: 6px;
}

.message-content :deep(.chat-image) {
  width: 100%;
  max-width: 360px;
  max-height: 190px;
  object-fit: contain;
  display: block;
  border-radius: 12px;
  background: #fff;
}

.chat-panel.dragging {
  border-color: rgba(59, 130, 246, 0.55);
  box-shadow: inset 0 0 0 2px rgba(59, 130, 246, 0.2);
}

.drop-mask {
  position: absolute;
  inset: 18px;
  z-index: 4;
  border-radius: 16px;
  border: 2px dashed rgba(59, 130, 246, 0.55);
  background: rgba(59, 130, 246, 0.12);
  display: grid;
  place-items: center;
  font-weight: 600;
  color: #1d4ed8;
  pointer-events: none;
}

@keyframes message-enter {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@media (max-width: 900px) {
  .message-content :deep(.md-image) {
    max-width: 240px;
  }

  .message-content :deep(.chat-image) {
    max-width: 240px;
    max-height: 150px;
  }
}

.source-list {
  margin-top: 8px;
  padding: 9px 11px;
  border-radius: 12px;
  background: rgba(241, 245, 249, 0.92);
  border: 1px solid rgba(203, 213, 225, 0.75);
  font-size: 12px;
  color: #475569;
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

.source-link {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 2px;
  border: none;
  background: transparent;
  padding: 0;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.source-link:hover:not(:disabled) {
  text-decoration: underline;
}

.source-link:disabled {
  cursor: not-allowed;
  opacity: 0.6;
  text-decoration: none;
}

.source-name {
  font-weight: 600;
}

.source-meta {
  margin-left: 6px;
  color: #6b7390;
}

.source-snippet {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
  line-height: 1.4;
}

.disclaimer-list {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.disclaimer-card {
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(251, 191, 36, 0.32);
  background: rgba(254, 243, 199, 0.45);
  color: #7a4b00;
  font-size: 12px;
  line-height: 1.4;
}

.disclaimer-card .disclaimer-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.disclaimer-card.disclaimer-info {
  border-color: rgba(147, 197, 253, 0.5);
  background: rgba(219, 234, 254, 0.7);
  color: #1e3a8a;
}

.disclaimer-card.disclaimer-critical {
  border-color: rgba(248, 113, 113, 0.5);
  background: rgba(254, 226, 226, 0.7);
  color: #991b1b;
}

.source-preview {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.source-preview-header h3 {
  margin: 0 0 6px;
}

.source-preview-meta {
  font-size: 12px;
  color: #6b7390;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.source-preview-name {
  font-weight: 600;
}

.source-preview-content {
  max-height: 320px;
  overflow: auto;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid rgba(226, 232, 240, 0.9);
  background: #f8fafc;
  line-height: 1.6;
}

.source-preview-content mark {
  background: #fde68a;
  color: #7c2d12;
  padding: 0 2px;
  border-radius: 3px;
}

.source-preview-loading,
.source-preview-error {
  font-size: 13px;
  color: #6b7390;
}

.debug-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  max-height: 70vh;
}

.debug-header h3 {
  margin: 0 0 6px;
}

.debug-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: #6b7390;
}

.debug-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
  overflow: auto;
  padding-right: 4px;
}

.debug-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.debug-section {
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 12px;
  padding: 10px 12px;
  background: #f8fafc;
}

.debug-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}

.debug-section-header h4 {
  margin: 0;
  font-size: 13px;
  color: #1f2a44;
}

.debug-block {
  margin: 0;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: "JetBrains Mono", "Fira Code", "Consolas", monospace;
}

.debug-loading,
.debug-error,
.debug-empty {
  font-size: 13px;
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

.md-quote {
  border-left: 3px solid rgba(99, 102, 241, 0.5);
  padding: 6px 10px;
  margin: 6px 0;
  background: rgba(99, 102, 241, 0.08);
  border-radius: 8px;
  color: #2b3563;
}

.md-code {
  margin: 8px 0;
  border: 1px solid rgba(226, 232, 240, 0.9);
  border-radius: 10px;
  background: #f8fafc;
  overflow: hidden;
}

.md-code .code-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  background: rgba(99, 102, 241, 0.08);
  border-bottom: 1px solid rgba(226, 232, 240, 0.9);
}

.md-code .code-lang {
  font-size: 11px;
  font-weight: 600;
  color: #4b567a;
  text-transform: uppercase;
}

.md-code .code-copy {
  border: none;
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.12);
  color: var(--accent-strong);
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.md-code .code-copy:hover {
  background: rgba(59, 130, 246, 0.2);
}

.md-code pre {
  margin: 0;
  padding: 12px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.6;
  background: transparent;
}

.md-code code {
  font-family: "JetBrains Mono", "Fira Code", "Consolas", monospace;
  background: transparent;
  padding: 0;
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
  border-top-color: var(--accent);
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

@keyframes progress-move {
  0% {
    left: -40%;
  }
  100% {
    left: 100%;
  }
}

.chat-input {
  display: flex;
  flex-direction: column;
  gap: 10px;
  align-items: stretch;
  width: min(100%, 1060px);
  margin: 0 auto;
  background: rgba(255, 255, 255, 0.98);
  border: 1px solid rgba(203, 213, 225, 0.82);
  border-radius: 20px;
  padding: 12px 14px;
  box-shadow: 0 14px 36px rgba(15, 23, 42, 0.08);
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.chat-input:focus-within {
  border-color: rgba(59, 130, 246, 0.55);
  box-shadow:
    0 14px 36px rgba(15, 23, 42, 0.1),
    0 0 0 3px rgba(59, 130, 246, 0.15);
}

.input-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.deep-chip {
  position: relative;
  border: 1px solid rgba(203, 213, 225, 0.84);
  background: rgba(248, 250, 252, 0.95);
  color: #334155;
  border-radius: 999px;
  padding: 7px 12px;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  transition: background 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
}

.deep-chip.active {
  background: rgba(59, 130, 246, 0.14);
  border-color: rgba(59, 130, 246, 0.45);
  color: #1d4ed8;
}

.deep-chip.active::after {
  content: none;
}

.deep-chip:hover:not(:disabled) {
  transform: translateY(-1px);
}

.deep-chip:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.attachment-strip {
  width: min(100%, 1060px);
  margin: 0 auto;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 14px;
  border: 1px dashed rgba(148, 163, 184, 0.55);
  background: rgba(248, 250, 252, 0.88);
}

.attachment-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  border-radius: 999px;
  padding: 4px 10px;
  background: rgba(226, 232, 240, 0.88);
  color: #334155;
  font-size: 12px;
}

.attachment-pill button {
  border: none;
  background: transparent;
  color: #64748b;
  padding: 0;
  font-size: 12px;
  cursor: pointer;
}

.file-input {
  display: none;
}

.edit-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 12px;
  background: rgba(99, 102, 241, 0.12);
  color: #2b3563;
  font-size: 12px;
  width: min(100%, 1060px);
  margin: 0 auto;
}

.suggestion-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 12px;
  background: rgba(59, 130, 246, 0.08);
  border: 1px solid rgba(59, 130, 246, 0.15);
  width: min(100%, 1060px);
  margin: 0 auto;
}

.suggestion-title {
  font-size: 12px;
  font-weight: 600;
  color: #5b65a2;
}

.suggestion-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.suggestion-chip {
  border: none;
  padding: 6px 12px;
  border-radius: 999px;
  background: rgba(59, 130, 246, 0.12);
  color: var(--accent-strong);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.suggestion-chip:hover {
  background: rgba(59, 130, 246, 0.18);
}

.suggestion-loading {
  font-size: 12px;
  color: #6b7390;
}

.deep-controls {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.deep-controls.disabled {
  opacity: 0.6;
}

.deep-toggle {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 12px;
  background: rgba(148, 163, 184, 0.12);
  border: 1px solid rgba(148, 163, 184, 0.25);
  font-size: 12px;
  color: #5b65a2;
}

.deep-toggle-control {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  color: #45507a;
}

.deep-toggle-control input {
  accent-color: var(--accent);
}

.deep-hint {
  color: #6b7390;
}

.md-cite {
  color: var(--accent-strong);
  cursor: pointer;
  font-weight: 600;
}

.md-cite:hover {
  text-decoration: underline;
}

.input-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
}

.mode-badge {
  align-self: flex-start;
  background: rgba(59, 130, 246, 0.12);
  color: var(--accent-strong);
  border-radius: 999px;
  padding: 2px 8px;
  font-size: 12px;
}

.chat-input textarea {
  border: none;
  outline: none;
  font-size: 15px;
  line-height: 1.6;
  min-height: 68px;
  padding: 6px 4px;
  resize: none;
  background: transparent;
  font-family: inherit;
  color: #0f172a;
}

.chat-input textarea::placeholder {
  color: #94a3b8;
}

.input-actions > .send-btn {
  margin-left: auto;
  border: none;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 9px 16px;
  border-radius: 12px;
  background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
  color: #fff;
  font-weight: 600;
  letter-spacing: 0.01em;
  cursor: pointer;
  box-shadow: 0 10px 22px rgba(15, 23, 42, 0.24);
}

.input-actions > .send-btn::after {
  content: "↗";
  font-size: 13px;
  line-height: 1;
}

.input-actions > .send-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  box-shadow: none;
}

@media (max-width: 1080px) {
  .chat-layout {
    grid-template-columns: 1fr;
    padding: 10px;
  }

  .chat-sidebar {
    order: 2;
  }

  .chat-main {
    order: 1;
    padding: 12px;
  }

  .chat-panel {
    padding: 12px;
  }

  .header-actions {
    align-items: flex-start;
  }

  .header-actions input {
    width: 100%;
  }

  .chat-main-actions {
    justify-content: flex-start;
  }

  .workspace-meta,
  .chat-main-actions,
  .notice,
  .error,
  .chat-log,
  .attachment-strip,
  .suggestion-bar,
  .edit-banner,
  .chat-input {
    width: 100%;
  }

  .chat-bubble {
    max-width: 94%;
  }

  .empty-actions {
    justify-content: flex-start;
  }

  .message-actions {
    opacity: 1;
    transform: none;
  }

  .session-menu-trigger,
  .delete-session {
    opacity: 1;
    transform: none;
  }

  .input-actions > .send-btn {
    margin-left: 0;
    width: 100%;
    justify-content: center;
  }
}

/* --- Editorial workspace override --- */
.chat-page {
  --bg: #f8f9fb;
  --surface-low: #f1f4f7;
  --surface-high: #ebeef1;
  --surface: #ffffff;
  --text: #2d3337;
  --text-soft: #5a6064;
  --text-dim: #7f8790;
  --blue: #005bc4;
  --blue-soft: #4388fd;
  --ghost-border: rgba(173, 179, 183, 0.15);
  --soft-shadow: 0 20px 40px rgba(0, 91, 196, 0.06);
  position: fixed;
  inset: 0;
  display: grid;
  grid-template-columns: 288px 1fr;
  overflow: hidden;
  background: var(--bg);
  color: var(--text);
  font-family: "Plus Jakarta Sans", "Noto Sans SC", sans-serif;
}

.chat-page *,
.chat-page *::before,
.chat-page *::after {
  box-sizing: border-box;
}

.chat-page .sidebar-backdrop {
  position: fixed;
  inset: 0;
  z-index: 20;
  background: rgba(45, 51, 55, 0.2);
  backdrop-filter: blur(3px);
}

.chat-page .material-symbols-outlined {
  font-family: "Material Symbols Outlined";
  font-weight: normal;
  font-style: normal;
  font-size: 20px;
  line-height: 1;
  display: inline-block;
  white-space: nowrap;
  word-wrap: normal;
  direction: ltr;
  -webkit-font-smoothing: antialiased;
  font-variation-settings: "FILL" 0, "wght" 400, "GRAD" 0, "opsz" 24;
}

.chat-page .workspace-sidebar {
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 26px 24px 14px;
  background: var(--surface-low);
}

.chat-page .sidebar-top {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
}

.chat-page .sidebar-brand {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 0 0 0 2px;
  margin-bottom: 34px;
  border-bottom: none;
}

.chat-page .brand-copy {
  display: grid;
  gap: 2px;
}

.chat-page .brand-icon {
  width: 40px;
  height: 40px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  color: #fff;
  background: linear-gradient(135deg, var(--blue) 0%, var(--blue-soft) 100%);
  box-shadow: 0 10px 24px rgba(0, 91, 196, 0.18);
}

.chat-page .brand-icon .material-symbols-outlined {
  font-size: 20px;
  font-variation-settings: "FILL" 1, "wght" 500, "GRAD" 0, "opsz" 24;
}

.chat-page .brand-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: -0.02em;
  line-height: 1;
  color: #1f2937;
}

.chat-page .brand-subtitle {
  margin: 0;
  font-size: 11px;
  color: #93a0ad;
  font-weight: 600;
}

.chat-page .new-chat-btn {
  border: none;
  width: 100%;
  border-radius: 14px;
  background: transparent;
  color: #1560cc;
  padding: 11px 10px;
  display: flex;
  align-items: center;
  gap: 10px;
  text-align: left;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: background 300ms ease-out, color 300ms ease-out, transform 300ms ease-out;
  transform: scale(0.98);
}

.chat-page .new-chat-btn:hover {
  background: rgba(255, 255, 255, 0.55);
}

.chat-page .workspace-nav {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  gap: 3px;
}

.chat-page .workspace-nav-item {
  border: none;
  width: 100%;
  border-radius: 14px;
  background: transparent;
  color: #667487;
  padding: 11px 10px;
  display: flex;
  align-items: center;
  gap: 10px;
  text-align: left;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: background 300ms ease-out, color 300ms ease-out, transform 300ms ease-out;
}

.chat-page .workspace-nav-item:hover {
  background: rgba(255, 255, 255, 0.52);
  color: #334155;
}

.chat-page .workspace-nav-item.active {
  color: #334155;
  background: rgba(255, 255, 255, 0.52);
}

.chat-page .history-block {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: auto;
  flex: 0 0 auto;
  gap: 6px;
}

.chat-page .history-trigger {
  flex: 0 0 auto;
}

.chat-page .history-trigger.active {
  background: rgba(255, 255, 255, 0.52);
  color: #334155;
}

.chat-page .history-panel {
  display: none;
  position: absolute;
  left: 0;
  right: 0;
  top: calc(100% + 6px);
  z-index: 25;
  max-height: min(46vh, 380px);
  padding: 10px;
  border-radius: 16px;
  background: rgba(255, 255, 255, 0.97);
  border: 1px solid var(--ghost-border);
  box-shadow: 0 22px 44px rgba(45, 51, 55, 0.12);
  backdrop-filter: blur(12px);
  flex-direction: column;
  gap: 8px;
}

.chat-page .history-panel.open {
  display: flex;
}

.chat-page .nav-icon {
  width: 22px;
  font-size: 19px;
  color: #738097;
  background: transparent;
  flex-shrink: 0;
}

.chat-page .session-filter input {
  width: 100%;
  border: 1px solid rgba(173, 179, 183, 0.22);
  background: var(--bg);
  border-radius: 13px;
  padding: 9px 12px;
  font-size: 13px;
  color: #2d3337;
  outline: none;
  transition: all 300ms ease-out;
}

.chat-page .session-filter input::placeholder {
  color: #98a1ab;
}

.chat-page .session-filter input:focus {
  border-color: rgba(67, 136, 253, 0.45);
  box-shadow: 0 0 0 4px rgba(67, 136, 253, 0.12);
}

.chat-page .session-empty {
  font-size: 12px;
  color: var(--text-dim);
  padding: 10px 6px;
}

.chat-page .session-list {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  padding: 0 3px 0 0;
}

.chat-page .session-list li {
  border-radius: 12px;
  padding: 5px;
}

.chat-page .session-list li:hover {
  background: #edf2f7;
}

.chat-page .session-list li.active {
  background: #e6eef9;
}

.chat-page .session-title {
  color: var(--text);
  font-size: 13px;
}

.chat-page .session-tag {
  border: none;
  background: #eef3f8;
  color: #617080;
}

.chat-page .session-menu {
  border: 1px solid var(--ghost-border);
  border-radius: 14px;
  box-shadow: var(--soft-shadow);
  backdrop-filter: blur(16px);
}

.chat-page .sidebar-footer {
  display: grid;
  gap: 8px;
  padding-top: 8px;
}

.chat-page .footer-links {
  display: grid;
  gap: 3px;
}

.chat-page .footer-link {
  border: none;
  background: transparent;
  border-radius: 14px;
  padding: 11px 10px;
  display: flex;
  align-items: center;
  gap: 10px;
  text-align: left;
  color: #667487;
  font-size: 15px;
  font-weight: 500;
  cursor: pointer;
  transition: background 300ms ease-out, color 300ms ease-out, transform 300ms ease-out;
}

.chat-page .footer-link:hover {
  background: rgba(255, 255, 255, 0.52);
  color: #334155;
}

.chat-page .footer-link.danger {
  color: #667487;
}

.chat-page .profile-card {
  width: 100%;
  border: none;
  border-top: 1px solid rgba(173, 179, 183, 0.2);
  border-radius: 0;
  margin-top: 8px;
  padding: 16px 0 2px;
  display: flex;
  align-items: center;
  gap: 11px;
  background: transparent;
  color: inherit;
}

.chat-page .profile-link {
  width: 100%;
  text-align: left;
  cursor: pointer;
  transition: background 300ms ease-out, box-shadow 300ms ease-out;
}

.chat-page .profile-link:hover {
  background: rgba(255, 255, 255, 0.4);
}

.chat-page .profile-link:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px rgba(90, 155, 253, 0.2);
}

.chat-page .profile-avatar {
  width: 40px;
  height: 40px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  color: #f4d58d;
  font-size: 15px;
  font-weight: 700;
  background: linear-gradient(135deg, #121212 0%, #242424 100%);
  background-size: cover;
  background-position: center;
  background-repeat: no-repeat;
}

.chat-page .profile-avatar.has-image {
  color: transparent;
  font-size: 0;
}

.chat-page .profile-name {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: #202a36;
}

.chat-page .profile-email {
  margin: 1px 0 0;
  font-size: 11px;
  color: var(--text-dim);
}

.chat-page .workspace-main {
  min-width: 0;
  min-height: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
  background: var(--bg);
}

.chat-page .workspace-header {
  width: 100%;
  margin: 0;
  padding: 28px 36px 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 0;
}

.chat-page .header-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.chat-page .icon-btn {
  width: 34px;
  height: 34px;
  border: none;
  border-radius: 999px;
  background: #edf2f7;
  color: #5f6772;
  font-size: 16px;
  cursor: pointer;
  transition: all 300ms ease-out;
}

.chat-page .icon-btn:hover {
  background: #e1e8f1;
}

.chat-page .workspace-meta {
  width: auto;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  color: var(--text-soft);
  font-size: 12px;
}

.chat-page .workspace-label {
  font-weight: 700;
  color: #111827;
  font-size: 24px;
  letter-spacing: -0.02em;
  line-height: 1.1;
}

.chat-page .spark-icon {
  color: #635983;
  font-size: 20px;
}

.chat-page .workspace-top-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.chat-page .top-chip {
  border: 1px solid rgba(67, 136, 253, 0.2);
  background: rgba(67, 136, 253, 0.08);
  color: #2c6dc9;
  border-radius: 999px;
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: all 300ms ease-out;
}

.chat-page .top-chip:hover {
  background: rgba(67, 136, 253, 0.14);
}

.chat-page .top-chip.subtle {
  background: rgba(148, 163, 184, 0.12);
  border-color: rgba(148, 163, 184, 0.22);
  color: #5f6873;
}

.chat-page .notice,
.chat-page .error {
  width: min(100%, 980px);
  margin: 8px auto 0;
  border-radius: 14px;
  padding: 11px 14px;
  font-size: 13px;
}

.chat-page .notice {
  background: rgba(67, 136, 253, 0.1);
  color: #2f67b8;
}

.chat-page .error {
  background: rgba(216, 87, 103, 0.12);
  color: #b24656;
}

.chat-page .chat-shell {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: transparent;
  padding: 0 36px 18px;
  overflow: hidden;
}

.chat-page .chat-shell.dragging {
  box-shadow: inset 0 0 0 2px rgba(90, 155, 253, 0.3);
}

.chat-page .drop-mask {
  position: absolute;
  inset: 12px 36px 24px;
  border-radius: 28px;
  border: 1px dashed rgba(67, 136, 253, 0.45);
  background: rgba(67, 136, 253, 0.12);
  display: grid;
  place-items: center;
  color: #2c69c3;
  font-weight: 700;
  z-index: 6;
}

.chat-page .chat-log {
  width: 100%;
  max-width: 1024px;
  margin: 0 auto;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 50px 6px 16px;
}

.chat-page .empty-state {
  width: 100%;
  max-width: 100%;
  min-height: 100%;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  text-align: center;
  padding: 0;
  background: transparent;
  box-shadow: none;
}

.chat-page .empty-state p {
  margin: 0;
  max-width: 860px;
  color: #596069;
  font-size: 30px;
  font-weight: 600;
  line-height: 1.45;
}

.chat-page .empty-cards {
  margin-top: 74px;
  width: 100%;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 18px;
}

.chat-page .empty-card {
  border: none;
  background: var(--surface);
  border-radius: 32px;
  padding: 28px 24px;
  text-align: left;
  display: grid;
  gap: 18px;
  cursor: pointer;
  min-height: 176px;
  transition: transform 300ms ease-out, box-shadow 300ms ease-out;
}

.chat-page .empty-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 20px 40px rgba(0, 91, 196, 0.06);
}

.chat-page .empty-card-copy {
  color: #2d3337;
  font-size: 18px;
  font-weight: 600;
  line-height: 1.38;
}

.chat-page .empty-card-icon {
  width: 52px;
  height: 52px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 24px;
}

.chat-page .empty-card-icon.tone-blue {
  color: #005bc4;
  background: #d8e3f8;
}

.chat-page .empty-card-icon.tone-purple {
  color: #635983;
  background: #d8cafc;
}

.chat-page .empty-card-icon.tone-cobalt {
  color: #ffffff;
  background: #4388fd;
}

.chat-page .chat-message {
  margin-bottom: 18px;
}

.chat-page .avatar {
  width: 30px;
  height: 30px;
  margin-top: 4px;
  box-shadow: none;
}

.chat-page .avatar::after {
  content: none;
}

.chat-page .assistant-avatar {
  background-image: none;
  background: linear-gradient(135deg, #d9e8fb, #c8ddf7);
}

.chat-page .user-avatar {
  background-image: none;
  background: linear-gradient(135deg, #6395e3, #5c87d6);
}

.chat-page .chat-bubble {
  max-width: min(86%, 860px);
  border-radius: 28px;
  padding: 18px 20px;
  border: none;
  background: var(--surface);
  box-shadow: 0 16px 30px rgba(45, 51, 55, 0.045);
  color: var(--text);
}

.chat-page .chat-message.user .chat-bubble {
  background: #dce9fb;
  color: var(--text);
  box-shadow: 0 14px 28px rgba(45, 51, 55, 0.04);
}

.chat-page .bubble-meta {
  font-size: 11px;
  color: #8a949e;
}

.chat-page .bubble-meta strong {
  font-size: 12px;
  color: #6c7680;
}

.chat-page .message-actions {
  transition: opacity 300ms ease-out;
}

.chat-page .source-list {
  border: none;
  border-radius: 18px;
  background: rgba(235, 241, 247, 0.8);
}

.chat-page .disclaimer-card {
  border: none;
  border-radius: 16px;
}

.chat-page .composer-stack {
  width: min(100%, 896px);
  margin: 0 auto;
  display: grid;
  gap: 8px;
  margin-top: auto;
  padding-bottom: 12px;
}

.chat-page .attachment-strip,
.chat-page .suggestion-bar,
.chat-page .edit-banner {
  width: 100%;
  margin: 0;
}

.chat-page .attachment-strip {
  border: none;
  border-radius: 18px;
  background: rgba(236, 242, 248, 0.92);
}

.chat-page .attachment-pill {
  background: #dde8f4;
}

.chat-page .suggestion-bar {
  border: none;
  border-radius: 16px;
  background: rgba(226, 236, 248, 0.85);
}

.chat-page .suggestion-title {
  color: #556172;
  font-weight: 700;
}

.chat-page .suggestion-chip {
  background: rgba(67, 136, 253, 0.14);
  color: #2f69bc;
}

.chat-page .edit-banner {
  border-radius: 16px;
  background: rgba(217, 228, 244, 0.86);
  color: #4f5d6d;
}

.chat-page .chat-input {
  width: 100%;
  margin: 0;
  border: none;
  border-radius: 42px;
  background: var(--surface);
  box-shadow: var(--soft-shadow);
  padding: 12px 14px;
  transition: box-shadow 300ms ease-out;
}

.chat-page .chat-input:focus-within {
  box-shadow:
    0 20px 40px rgba(45, 51, 55, 0.1),
    0 0 0 4px rgba(67, 136, 253, 0.14);
}

.chat-page .input-wrap {
  gap: 6px;
}

.chat-page .mode-badge {
  background: rgba(67, 136, 253, 0.12);
  color: #336ec2;
  font-weight: 700;
}

.chat-page .chat-input textarea {
  min-height: 34px;
  max-height: 220px;
  padding: 2px 4px;
  font-size: 16px;
  color: var(--text);
}

.chat-page .chat-input textarea::placeholder {
  color: #9aa4ae;
}

.chat-page .input-actions {
  gap: 8px;
  justify-content: space-between;
  align-items: center;
}

.chat-page .tool-chip {
  border: none;
  border-radius: 999px;
  padding: 7px 12px;
  background: #ebeef1;
  color: #5d6670;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  transition: all 300ms ease-out;
}

.chat-page .tool-chip .material-symbols-outlined {
  font-size: 15px;
}

.chat-page .tool-chip:hover:not(:disabled) {
  background: #e4e9ec;
}

.chat-page .tool-chip.active {
  background: rgba(67, 136, 253, 0.18);
  color: #2f67b8;
}

.chat-page .tool-chip:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.chat-page .kb-chip {
  background: rgba(67, 136, 253, 0.15);
  color: #2f67b8;
}

.chat-page .send-btn,
.chat-page .input-actions > .send-btn {
  margin-left: auto;
  border: none;
  border-radius: 999px;
  min-width: 104px;
  padding: 11px 22px;
  background: linear-gradient(135deg, var(--blue) 0%, var(--blue-soft) 100%);
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  box-shadow: 0 14px 28px rgba(0, 94, 184, 0.23);
}

.chat-page .send-btn::after,
.chat-page .input-actions > .send-btn::after {
  content: " >";
  margin-left: 4px;
  font-size: 14px;
}

.chat-page .mobile-only {
  display: none;
}

@media (max-width: 1080px) {
  .chat-page {
    grid-template-columns: 1fr;
  }

  .chat-page .workspace-sidebar {
    position: fixed;
    left: 0;
    top: 0;
    bottom: 0;
    width: min(86vw, 320px);
    z-index: 30;
    transform: translateX(-105%);
    transition: transform 300ms ease-out;
    box-shadow: var(--soft-shadow);
  }

  .chat-page .workspace-sidebar.open {
    transform: translateX(0);
  }

  .chat-page .workspace-header {
    padding: 16px 14px 0;
  }

  .chat-page .workspace-top-actions {
    display: none;
  }

  .chat-page .history-block {
    flex: 1;
    min-height: 0;
  }

  .chat-page .history-panel {
    position: static;
    max-height: none;
    box-shadow: none;
    border: none;
    padding: 8px 0 0;
    border-radius: 0;
    background: transparent;
    backdrop-filter: none;
  }

  .chat-page .chat-shell {
    padding: 0 14px 12px;
  }

  .chat-page .mobile-only {
    display: inline-grid;
    place-items: center;
  }
}

@media (max-width: 768px) {
  .chat-page .workspace-label {
    font-size: 20px;
  }

  .chat-page .chat-log {
    padding-top: 24px;
  }

  .chat-page .empty-state p {
    font-size: 14px;
  }

  .chat-page .empty-cards {
    margin-top: 32px;
    grid-template-columns: 1fr;
  }

  .chat-page .empty-card {
    min-height: 146px;
    border-radius: 24px;
  }

  .chat-page .empty-card-copy {
    font-size: 16px;
  }

  .chat-page .chat-bubble {
    max-width: 94%;
    border-radius: 22px;
    padding: 14px;
  }

  .chat-page .avatar {
    display: none;
  }

  .chat-page .chat-input {
    border-radius: 24px;
    padding: 10px;
  }

  .chat-page .chat-input textarea {
    font-size: 15px;
  }

  .chat-page .tool-chip {
    font-size: 11px;
    padding: 7px 10px;
  }

  .chat-page .composer-stack {
    width: 100%;
  }

  .chat-page .send-btn,
  .chat-page .input-actions > .send-btn {
    margin-left: 0;
    width: 100%;
    justify-content: center;
  }
}
</style>


