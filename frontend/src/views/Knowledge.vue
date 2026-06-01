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

        <section class="panel patch-panel">
          <div class="panel-head">
            <h2 class="title-section">待写入 Wiki</h2>
            <span class="count-chip">{{ wikiPatches.items.length }} 条</span>
          </div>

          <div v-if="!activeKb" class="empty-block">请选择知识库后查看待审核内容。</div>
          <div v-else-if="wikiPatches.loading" class="empty-block">正在读取待审核内容...</div>
          <div v-else-if="!wikiPatches.items.length" class="empty-block">
            当前没有待写入 Wiki 的答案。
          </div>

          <div v-else class="patch-list">
            <article v-for="patch in wikiPatches.items" :key="patch.id" class="patch-card">
              <div class="patch-card-head">
                <div class="patch-target">
                  <span class="material-symbols-outlined" aria-hidden="true">rate_review</span>
                  <span>{{ patch.target_path }}</span>
                </div>
                <span class="patch-confidence">{{ formatPatchConfidence(patch) }}</span>
              </div>

              <div class="patch-meta">
                <span>{{ formatPatchOperation(patch.operation) }}</span>
                <span>{{ formatRelativeTime(patch.created_at) }}</span>
              </div>

              <p v-if="patch.question" class="patch-question">{{ patch.question }}</p>
              <p v-if="patch.answer" class="patch-answer">{{ clipText(patch.answer, 220) }}</p>

              <pre class="patch-markdown">{{ clipText(patch.patch_markdown, 520) }}</pre>

              <div class="patch-actions">
                <button
                  class="patch-action-btn accept"
                  type="button"
                  :disabled="wikiPatchBusyId === patch.id"
                  @click="applyWikiPatch(patch)"
                >
                  采纳
                </button>
                <button
                  class="patch-action-btn reject"
                  type="button"
                  :disabled="wikiPatchBusyId === patch.id"
                  @click="rejectWikiPatch(patch)"
                >
                  拒绝
                </button>
              </div>
            </article>
          </div>
        </section>

        <section class="panel wiki-panel">
          <div class="panel-head">
            <div>
              <h2 class="title-section">知识库 Wiki</h2>
            </div>
            <div class="panel-head-actions">
              <span class="count-chip">{{ wikiPages.items.length }} 页</span>
              <button
                class="icon-ghost"
                type="button"
                :title="wikiRefreshLoading ? '正在刷新 Wiki' : '刷新 Wiki'"
                :disabled="!activeKb || wikiPages.loading || wikiRefreshLoading"
                @click="refreshWikiPages"
              >
                <span class="material-symbols-outlined" aria-hidden="true">refresh</span>
              </button>
            </div>
          </div>

          <div v-if="!activeKb" class="empty-block">请选择知识库后查看 Wiki。</div>

          <div v-else class="wiki-browser">
            <aside class="wiki-page-list" aria-label="Wiki 页面列表">
              <div v-if="wikiPages.loading" class="empty-block">正在读取 Wiki 页面...</div>
              <div v-else-if="!wikiPages.items.length" class="empty-block">暂无 Wiki 页面。</div>

              <template v-else>
                <button
                  v-for="page in wikiPages.items"
                  :key="page.id"
                  class="wiki-page-row"
                  :class="{ active: selectedWikiPageId === page.id }"
                  type="button"
                  @click="selectWikiPage(page)"
                >
                  <span class="wiki-page-icon" :class="getWikiPageToneClass(page)">
                    <span class="material-symbols-outlined" aria-hidden="true">
                      {{ getWikiPageIcon(page) }}
                    </span>
                  </span>
                  <span class="wiki-page-copy">
                    <span class="wiki-page-title">{{ page.title || page.path }}</span>
                    <span class="wiki-page-meta">
                      {{ formatWikiPageType(page.page_type) }} · {{ page.path }}
                    </span>
                  </span>
                </button>
              </template>
            </aside>

            <article class="wiki-preview">
              <div v-if="wikiPageContent.loading" class="empty-block">正在读取页面正文...</div>

              <template v-else-if="wikiPageContent.page">
                <header class="wiki-preview-head">
                  <div>
                    <p class="wiki-preview-type">
                      {{ formatWikiPageType(wikiPageContent.page.page_type) }}
                    </p>
                    <h3>{{ wikiPageContent.page.title || wikiPageContent.page.path }}</h3>
                  </div>
                  <span class="wiki-preview-time">
                    {{ formatRelativeTime(wikiPageContent.page.updated_at) }}
                  </span>
                </header>

                <div class="wiki-path-row">
                  <span class="material-symbols-outlined" aria-hidden="true">article</span>
                  <span>{{ wikiPageContent.page.path }}</span>
                </div>

                <pre class="wiki-markdown">{{ wikiPageContent.page.content || '这个 Wiki 页面暂时没有正文。' }}</pre>
              </template>

              <div v-else class="empty-block">请选择一个 Wiki 页面。</div>
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
const wikiPatches = ref({ items: [], loading: false });
const wikiPatchBusyId = ref(null);
const wikiPages = ref({ items: [], loading: false });
const wikiRefreshLoading = ref(false);
const selectedWikiPageId = ref(null);
const wikiPageContent = ref({ page: null, loading: false });
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

const fetchWikiPatches = async ({ silent = false } = {}) => {
  if (!activeKb.value) {
    wikiPatches.value.items = [];
    wikiPatches.value.loading = false;
    return;
  }

  wikiPatches.value.loading = true;
  try {
    const data = await apiFetch(`/knowledge/${activeKb.value.id}/wiki/patches?status=pending`);
    wikiPatches.value.items = data || [];
  } catch (err) {
    if (!silent) setError(`获取 Wiki 待审核内容失败：${err.message}`);
  } finally {
    wikiPatches.value.loading = false;
  }
};

const resetWikiBrowser = () => {
  wikiPages.value.items = [];
  wikiPages.value.loading = false;
  wikiRefreshLoading.value = false;
  selectedWikiPageId.value = null;
  wikiPageContent.value = { page: null, loading: false };
};

const sortWikiPages = (items) => {
  const pageTypeOrder = {
    index: 0,
    topic: 1,
    source: 2,
    schema: 3,
    log: 4,
  };
  return [...items].sort((left, right) => {
    const leftOrder = pageTypeOrder[left.page_type] ?? 9;
    const rightOrder = pageTypeOrder[right.page_type] ?? 9;
    if (leftOrder !== rightOrder) return leftOrder - rightOrder;
    return String(left.path || '').localeCompare(String(right.path || ''), 'zh-Hans-CN');
  });
};

const selectWikiPage = async (page, { silent = false } = {}) => {
  if (!activeKb.value || !page) return;
  const kbId = activeKb.value.id;
  selectedWikiPageId.value = page.id;
  wikiPageContent.value.loading = true;

  try {
    const data = await apiFetch(`/knowledge/${kbId}/wiki/pages/${page.id}`);
    if (activeKb.value?.id !== kbId) return;
    wikiPageContent.value.page = data;
  } catch (err) {
    if (!silent) setError(`获取 Wiki 页面失败：${err.message}`);
    if (selectedWikiPageId.value === page.id) {
      wikiPageContent.value.page = null;
    }
  } finally {
    if (activeKb.value?.id === kbId) {
      wikiPageContent.value.loading = false;
    }
  }
};

const findDefaultWikiPage = (items, currentId = null, preferPath = null) =>
  items.find((page) => preferPath && page.path === preferPath) ||
  items.find((page) => currentId && page.id === currentId) ||
  items.find((page) => page.page_type === 'topic') ||
  items.find((page) => page.path === 'index.md') ||
  items[0] ||
  null;

const getSelectedWikiPagePath = () =>
  wikiPageContent.value.page?.path ||
  wikiPages.value.items.find((page) => page.id === selectedWikiPageId.value)?.path ||
  null;

const fetchWikiPages = async ({ silent = false, preferPath = null } = {}) => {
  if (!activeKb.value) {
    resetWikiBrowser();
    return;
  }

  const kbId = activeKb.value.id;
  wikiPages.value.loading = true;
  try {
    const data = await apiFetch(`/knowledge/${kbId}/wiki/pages`);
    if (activeKb.value?.id !== kbId) return;

    const items = sortWikiPages(data || []);
    wikiPages.value.items = items;
    const nextPage = findDefaultWikiPage(items, selectedWikiPageId.value, preferPath);

    if (nextPage) {
      await selectWikiPage(nextPage, { silent: true });
    } else {
      selectedWikiPageId.value = null;
      wikiPageContent.value.page = null;
    }
  } catch (err) {
    if (!silent) setError(`获取 Wiki 页面列表失败：${err.message}`);
  } finally {
    if (activeKb.value?.id === kbId) {
      wikiPages.value.loading = false;
    }
  }
};

const refreshWikiPages = async () => {
  if (!activeKb.value || wikiRefreshLoading.value) return;

  const kbId = activeKb.value.id;
  const preferPath = getSelectedWikiPagePath();
  wikiRefreshLoading.value = true;
  wikiPages.value.loading = true;

  try {
    const result = await apiFetch(`/knowledge/${kbId}/wiki/rebuild`, {
      method: 'POST',
      timeoutMs: 120000,
    });
    if (activeKb.value?.id !== kbId) return;

    await Promise.all([
      fetchWikiPatches({ silent: true }),
      fetchWikiPages({ silent: true, preferPath }),
    ]);

    if (result?.success === false) {
      const errorCount = result.errors?.length || 0;
      setError(
        errorCount
          ? `Wiki 已刷新，但 ${errorCount} 个文档重新编译失败。`
          : 'Wiki 刷新完成，但后端报告未完全成功。',
      );
      return;
    }

    setNotice('Wiki 已刷新');
  } catch (err) {
    if (activeKb.value?.id === kbId) {
      setError(`刷新 Wiki 失败：${err.message}`);
    }
  } finally {
    wikiRefreshLoading.value = false;
    if (activeKb.value?.id === kbId) {
      wikiPages.value.loading = false;
    }
  }
};

const fetchActiveKnowledgeBaseData = async ({ silent = false } = {}) => {
  await Promise.all([
    fetchDocuments({ silent }),
    fetchWikiPatches({ silent }),
    fetchWikiPages({ silent }),
  ]);
};

const fetchKnowledgeBases = async ({ preferKbId = null } = {}) => {
  try {
    const data = await apiFetch('/knowledge/list');
    knowledgeBases.value = data || [];
    if (!knowledgeBases.value.length) {
      activeKb.value = null;
      documents.value.items = [];
      wikiPatches.value.items = [];
      resetWikiBrowser();
      stopDocumentPolling();
      return;
    }

    const currentId = preferKbId ?? activeKb.value?.id;
    const nextKb =
      knowledgeBases.value.find((item) => item.id === currentId) || knowledgeBases.value[0];
    const changed = !activeKb.value || activeKb.value.id !== nextKb.id;
    activeKb.value = nextKb;

    if (changed || !documents.value.items.length) {
      await fetchActiveKnowledgeBaseData({ silent: true });
    } else {
      await Promise.all([
        fetchWikiPatches({ silent: true }),
        fetchWikiPages({ silent: true }),
      ]);
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
  wikiPatches.value.items = [];
  resetWikiBrowser();
  await fetchActiveKnowledgeBaseData({ silent: true });
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
    await Promise.all([
      fetchKnowledgeBases({ preferKbId: activeKb.value.id }),
      fetchWikiPatches({ silent: true }),
      fetchWikiPages({ silent: true }),
    ]);
    updateDocumentPolling();
  } catch (err) {
    setError(`删除文档失败：${err.message}`);
  }
};

const applyWikiPatch = async (patch) => {
  if (!activeKb.value || wikiPatchBusyId.value) return;
  const confirmed = window.confirm(`采纳后会写入「${patch.target_path}」，继续吗？`);
  if (!confirmed) return;

  wikiPatchBusyId.value = patch.id;
  try {
    const appliedPatch = await apiFetch(`/knowledge/${activeKb.value.id}/wiki/patches/${patch.id}/apply`, {
      method: 'POST',
    });
    setNotice('已写入 Wiki');
    await Promise.all([
      fetchWikiPatches({ silent: true }),
      fetchWikiPages({ silent: true, preferPath: appliedPatch?.target_path }),
    ]);
  } catch (err) {
    setError(`写入 Wiki 失败：${err.message}`);
    await fetchWikiPatches({ silent: true });
  } finally {
    wikiPatchBusyId.value = null;
  }
};

const rejectWikiPatch = async (patch) => {
  if (!activeKb.value || wikiPatchBusyId.value) return;
  const confirmed = window.confirm('确认拒绝这条待写入内容吗？');
  if (!confirmed) return;

  wikiPatchBusyId.value = patch.id;
  try {
    await apiFetch(`/knowledge/${activeKb.value.id}/wiki/patches/${patch.id}/reject`, {
      method: 'POST',
    });
    setNotice('已拒绝该条 Wiki 写入');
    await fetchWikiPatches({ silent: true });
  } catch (err) {
    setError(`拒绝失败：${err.message}`);
  } finally {
    wikiPatchBusyId.value = null;
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

const clipText = (value, maxLength = 180) => {
  const text = String(value || '').trim();
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength).trim()}...`;
};

const formatPatchConfidence = (patch) => {
  const confidence = Number(patch?.confidence || 0);
  return `${Math.round(Math.max(0, Math.min(1, confidence)) * 100)}%`;
};

const formatPatchOperation = (operation) => {
  const labels = {
    append: '追加',
    create: '新建',
    replace_section: '替换段落',
  };
  return labels[operation] || operation || '更新';
};

const formatWikiPageType = (pageType) => {
  const labels = {
    index: '首页',
    topic: '主题页',
    source: '来源页',
    schema: '结构页',
    log: '日志页',
  };
  return labels[pageType] || pageType || '页面';
};

const getWikiPageIcon = (page) => {
  const pageType = page?.page_type;
  if (pageType === 'index') return 'home';
  if (pageType === 'topic') return 'auto_stories';
  if (pageType === 'source') return 'article';
  if (pageType === 'schema') return 'account_tree';
  if (pageType === 'log') return 'history';
  return 'description';
};

const getWikiPageToneClass = (page) => {
  const pageType = page?.page_type;
  if (pageType === 'topic') return 'tone-topic';
  if (pageType === 'source') return 'tone-source';
  if (pageType === 'schema') return 'tone-schema';
  if (pageType === 'log') return 'tone-log';
  return 'tone-index';
};

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

.patch-panel {
  grid-column: span 7 / span 7;
  padding: 2rem;
}

.wiki-panel {
  grid-column: span 12 / span 12;
  padding: 2rem;
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

.panel-head-actions {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  flex-shrink: 0;
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

.icon-ghost:disabled {
  color: #cbd5e1;
  cursor: not-allowed;
  background: transparent;
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

.patch-list {
  display: grid;
  gap: 0.875rem;
}

.patch-card {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 0.75rem;
  padding: 1rem;
  background: #fbfdff;
}

.patch-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.patch-target {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  color: #0f172a;
  font-size: 0.875rem;
  font-weight: 800;
  line-height: 1.35;
  word-break: break-word;
}

.patch-target .material-symbols-outlined {
  color: #047857;
  font-size: 1.2rem;
  flex-shrink: 0;
}

.patch-confidence {
  flex-shrink: 0;
  border-radius: 999px;
  padding: 0.25rem 0.55rem;
  background: #dcfce7;
  color: #166534;
  font-size: 0.6875rem;
  font-weight: 800;
}

.patch-meta {
  margin-top: 0.375rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  color: #64748b;
  font-size: 0.6875rem;
  font-weight: 700;
}

.patch-question {
  margin: 0.8rem 0 0;
  color: #0f172a;
  font-size: 0.875rem;
  font-weight: 700;
  line-height: 1.55;
  word-break: break-word;
}

.patch-answer {
  margin: 0.45rem 0 0;
  color: #334155;
  font-size: 0.8125rem;
  line-height: 1.65;
  word-break: break-word;
}

.patch-markdown {
  margin: 0.75rem 0 0;
  max-height: 11rem;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  border-radius: 0.625rem;
  padding: 0.75rem;
  background: #f1f5f9;
  color: #334155;
  font-size: 0.75rem;
  line-height: 1.55;
  font-family: "Noto Sans SC", "Inter", sans-serif;
}

.patch-actions {
  margin-top: 0.875rem;
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}

.patch-action-btn {
  border: none;
  border-radius: 999px;
  min-width: 4.75rem;
  padding: 0.55rem 0.875rem;
  font-size: 0.8125rem;
  font-weight: 800;
  cursor: pointer;
  transition: opacity 200ms ease-out, transform 200ms ease-out;
}

.patch-action-btn:hover {
  transform: translateY(-1px);
}

.patch-action-btn:disabled {
  cursor: wait;
  opacity: 0.55;
  transform: none;
}

.patch-action-btn.accept {
  background: #047857;
  color: #fff;
}

.patch-action-btn.reject {
  background: #fee2e2;
  color: #991b1b;
}

.wiki-browser {
  display: grid;
  grid-template-columns: minmax(16rem, 0.8fr) minmax(0, 1.4fr);
  gap: 1rem;
  min-height: 28rem;
}

.wiki-page-list {
  min-width: 0;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 0.75rem;
  background: #f8fafc;
  padding: 0.5rem;
  overflow: auto;
  max-height: 36rem;
}

.wiki-page-row {
  width: 100%;
  min-width: 0;
  border: none;
  border-radius: 0.625rem;
  background: transparent;
  padding: 0.75rem;
  display: flex;
  align-items: flex-start;
  gap: 0.75rem;
  text-align: left;
  cursor: pointer;
  transition: background-color 200ms ease-out, box-shadow 200ms ease-out;
}

.wiki-page-row:hover,
.wiki-page-row.active {
  background: #fff;
  box-shadow: 0 8px 20px rgba(15, 23, 42, 0.06);
}

.wiki-page-icon {
  width: 2.25rem;
  height: 2.25rem;
  border-radius: 0.5rem;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.wiki-page-icon .material-symbols-outlined {
  font-size: 1.15rem;
}

.wiki-page-copy {
  min-width: 0;
  display: grid;
  gap: 0.125rem;
}

.wiki-page-title {
  min-width: 0;
  color: #0f172a;
  font-size: 0.875rem;
  font-weight: 800;
  line-height: 1.4;
  word-break: break-word;
}

.wiki-page-meta {
  min-width: 0;
  color: #64748b;
  font-size: 0.6875rem;
  font-weight: 600;
  line-height: 1.45;
  word-break: break-word;
}

.wiki-preview {
  min-width: 0;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 0.75rem;
  background: #fff;
  padding: 1.25rem;
  overflow: hidden;
}

.wiki-preview-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.75rem;
}

.wiki-preview-type {
  margin: 0 0 0.25rem;
  color: #2563eb;
  font-size: 0.6875rem;
  font-weight: 800;
}

.wiki-preview-head h3 {
  margin: 0;
  color: #0f172a;
  font-size: 1.125rem;
  line-height: 1.45;
  word-break: break-word;
}

.wiki-preview-time {
  flex-shrink: 0;
  color: #94a3b8;
  font-size: 0.75rem;
  font-weight: 700;
}

.wiki-path-row {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  max-width: 100%;
  border-radius: 999px;
  padding: 0.35rem 0.65rem;
  background: #eef2ff;
  color: #3155a4;
  font-size: 0.75rem;
  font-weight: 700;
}

.wiki-path-row .material-symbols-outlined {
  flex-shrink: 0;
  font-size: 1rem;
}

.wiki-path-row span:last-child {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wiki-markdown {
  margin: 1rem 0 0;
  min-height: 21rem;
  max-height: 48rem;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  border-radius: 0.75rem;
  border: 1px solid rgba(148, 163, 184, 0.14);
  padding: 1rem;
  background: #fbfdff;
  color: #1f2937;
  font-family: "Noto Sans SC", "Inter", sans-serif;
  font-size: 0.875rem;
  line-height: 1.8;
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

.tone-index {
  background: #eff6ff;
  color: #2563eb;
}

.tone-topic {
  background: #ecfdf5;
  color: #047857;
}

.tone-source {
  background: #f8fafc;
  color: #475569;
}

.tone-schema {
  background: #eef2ff;
  color: #4f46e5;
}

.tone-log {
  background: #fff7ed;
  color: #c2410c;
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
  .list-panel,
  .patch-panel,
  .wiki-panel {
    grid-column: auto;
    grid-row: auto;
  }

  .patch-panel {
    order: 2;
  }

  .wiki-panel {
    order: 3;
  }

  .files-panel {
    order: 4;
  }

  .wiki-browser {
    grid-template-columns: 1fr;
    min-height: 0;
  }

  .wiki-page-list {
    max-height: 18rem;
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
