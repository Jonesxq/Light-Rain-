<template>
  <div class="page ai-news-page">
    <header class="header">
      <div>
        <h1>AI 资讯</h1>
        <p>自动聚合近 7 天最新 AI 动态。</p>
      </div>
      <div class="header-actions">
        <div class="actions action-bar">
          <button class="ghost" @click="goChat">聊天</button>
          <button class="ghost" @click="goMy">我的</button>
          <button class="ghost" @click="goKnowledge">知识库</button>
          <button class="ghost" @click="goUsage">使用量看板</button>
          <button class="ghost" @click="goSettings">模型设置</button>
          <button class="ghost" @click="logout">退出登录</button>
        </div>
      </div>
    </header>

    <div v-if="notice" class="notice">{{ notice }}</div>
    <div v-if="error" class="error">{{ error }}</div>

    <section class="card summary-card">
      <div class="card-head">
        <h2>最新 10 条</h2>
        <div class="actions">
          <button @click="refreshNews" :disabled="loading">{{ loading ? '加载中...' : '刷新' }}</button>
        </div>
      </div>
      <div class="summary-meta">
        <span>更新时间：{{ fetchedAtLabel }}</span>
        <span v-if="fromCache">来源：缓存</span>
        <span v-else>来源：实时</span>
      </div>
    </section>

    <section class="card news-list">
      <div v-if="!items.length && !loading" class="empty">暂无资讯</div>
      <div v-for="item in items" :key="item.link" class="news-item card-soft hover-lift">
        <div v-if="item.image_url" class="thumb">
          <img :src="item.image_url" alt="" />
        </div>
        <div class="news-content">
          <a :href="item.link" target="_blank" rel="noopener" class="title">{{ item.title }}</a>
          <div class="meta">
            <span>{{ item.source || '未知来源' }}</span>
            <span v-if="item.date">· {{ item.date }}</span>
          </div>
          <p v-if="item.snippet" class="snippet">{{ item.snippet }}</p>
        </div>
      </div>
    </section>

    <CenterToast :message="successMessage" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { apiFetch, clearTokens } from '../api/client.js';
import CenterToast from '../components/CenterToast.vue';
import { useCenterToast } from '../composables/useCenterToast.js';

const router = useRouter();
const notice = ref('');
const error = ref('');
const loading = ref(false);
const items = ref([]);
const fetchedAt = ref('');
const fromCache = ref(false);
const { message: successMessage, show: showSuccess } = useCenterToast();

const fetchedAtLabel = computed(() => {
  if (!fetchedAt.value) return '未获取';
  return fetchedAt.value.replace('T', ' ').replace('Z', '');
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

const goChat = () => router.push('/chat');
const goMy = () => router.push('/my');
const goKnowledge = () => router.push('/knowledge');
const goUsage = () => router.push('/usage');
const goSettings = () => router.push('/settings');

const logout = () => {
  clearTokens();
  router.push('/login');
};

const loadNews = async (refresh = false) => {
  loading.value = true;
  error.value = '';
  try {
    const query = refresh ? '?limit=10&refresh=1' : '?limit=10';
    const data = await apiFetch(`/news/ai/latest${query}`);
    items.value = data?.items || [];
    fetchedAt.value = data?.fetched_at || '';
    fromCache.value = Boolean(data?.from_cache);
  } catch (err) {
    if (err.message && err.message.includes('SERPER_API_KEY')) {
      setError('请先在后端配置 SERPER_API_KEY 才能使用 AI 资讯。');
    } else {
      setError(err.message || '加载失败');
    }
  } finally {
    loading.value = false;
  }
};

const refreshNews = () => loadNews(true);

onMounted(() => {
  loadNews(false);
});
</script>

<style scoped>
.ai-news-page {
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

.ai-news-page::before {
  content: none;
  display: none;
}

.ai-news-page > * {
  position: relative;
  z-index: 1;
}

.summary-meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--text-soft);
}

.news-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.news-item {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 16px;
  animation: fade-up 0.35s ease both;
}

.thumb {
  width: 120px;
  height: 80px;
  border-radius: 12px;
  overflow: hidden;
  background: var(--surface-strong);
  display: flex;
  align-items: center;
  justify-content: center;
}

.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-strong);
  text-decoration: none;
}

.title:hover {
  text-decoration: underline;
}

.meta {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-soft);
}

.snippet {
  margin-top: 8px;
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.6;
}

.empty {
  font-size: 12px;
  color: var(--text-soft);
}

@media (max-width: 1080px) {
  .ai-news-page {
    width: 100%;
    height: auto;
    max-height: none;
    margin: 16px auto;
  }

  .header {
    flex-direction: column;
    align-items: flex-start;
  }

  .news-item {
    grid-template-columns: 1fr;
  }

  .thumb {
    width: 100%;
    height: 180px;
  }
}
</style>
