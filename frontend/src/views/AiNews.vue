<template>
  <main class="ai-news-page">
    <nav class="ai-news-topbar">
      <div class="ai-news-topbar-inner">
        <button class="ai-news-back" type="button" @click="goChat">返回聊天</button>
      </div>
    </nav>

    <section class="ai-news-main">
      <header class="ai-news-header">
        <h1>AI 资讯</h1>
        <p>自动聚合近 7 天最新 AI 动态。</p>
      </header>

      <div class="ai-news-tools">
        <button class="ai-news-refresh" type="button" :disabled="loading" @click="refreshNews">
          <span class="material-symbols-outlined" aria-hidden="true">refresh</span>
          {{ loading ? 'Loading' : 'Refresh' }}
        </button>
        <span class="ai-news-tools-meta" v-if="fetchedAtLabel">更新于 {{ fetchedAtLabel }}</span>
        <span class="ai-news-tools-meta" v-if="fetchedAtLabel">· {{ fromCache ? '缓存' : '实时' }}</span>
      </div>

      <div v-if="error" class="ai-news-error">{{ error }}</div>

      <section class="ai-news-feed">
        <div v-if="!mappedItems.length && !loading" class="ai-news-empty">暂无资讯</div>

        <article v-for="item in mappedItems" :key="item.link" class="ai-news-item">
          <a :href="item.link" target="_blank" rel="noopener" class="ai-news-item-main">
            <div class="ai-news-item-meta">
              <span class="ai-news-category">{{ item.categoryLabel }}</span>
              <span class="ai-news-dot"></span>
              <span class="ai-news-time">{{ item.timeLabel }}</span>
            </div>

            <h2 class="ai-news-title">{{ item.title }}</h2>
            <p class="ai-news-snippet">{{ item.snippet || '暂无摘要信息。' }}</p>

            <div class="ai-news-source">
              <span class="material-symbols-outlined" aria-hidden="true">{{ sourceIcon(item.categoryLabel) }}</span>
              <span>{{ item.source || 'Unknown Source' }}</span>
            </div>
          </a>

          <a
            :href="item.link"
            target="_blank"
            rel="noopener"
            class="ai-news-thumb"
            :class="{ placeholder: !item.image_url }"
          >
            <img v-if="item.image_url" :src="item.image_url" alt="" loading="lazy" />
            <span v-else class="material-symbols-outlined" aria-hidden="true">image</span>
          </a>
        </article>
      </section>
    </section>

    <CenterToast :message="successMessage" />
  </main>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { apiFetch } from '../api/client.js';
import CenterToast from '../components/CenterToast.vue';
import { useCenterToast } from '../composables/useCenterToast.js';

const router = useRouter();
const error = ref('');
const loading = ref(false);
const items = ref([]);
const fetchedAt = ref('');
const fromCache = ref(false);
const { message: successMessage } = useCenterToast();

const goChat = () => router.push('/chat');

const CATEGORY_RULES = [
  {
    label: 'POLICY',
    keywords: ['政策', '法案', '监管', '合规', '白宫', '欧盟', 'policy', 'regulat', 'government'],
  },
  {
    label: 'MARKET',
    keywords: ['市值', '投资', '融资', '估值', '财报', 'market', 'funding', 'valuation', 'stock'],
  },
  {
    label: 'ETHICS',
    keywords: ['版权', '伦理', '公平', '偏见', 'ethic', 'safety', 'copyright', 'lawsuit'],
  },
  {
    label: 'INTELLIGENCE',
    keywords: ['模型', '发布', 'openai', 'deepmind', 'llama', 'mistral', 'nvidia', 'ai'],
  },
];

const CATEGORY_ICON = {
  INTELLIGENCE: 'auto_awesome',
  MARKET: 'trending_up',
  POLICY: 'policy',
  ETHICS: 'gavel',
};

const resolveCategory = (item) => {
  const haystack = `${item.title || ''} ${item.source || ''} ${item.snippet || ''}`.toLowerCase();
  const hit = CATEGORY_RULES.find((rule) =>
    rule.keywords.some((keyword) => haystack.includes(keyword.toLowerCase())),
  );
  return hit?.label || 'INTELLIGENCE';
};

const sourceIcon = (category) => CATEGORY_ICON[category] || 'auto_awesome';

const toRelativeTime = (input) => {
  const raw = String(input || '').trim();
  if (!raw) return 'Just now';
  if (/(ago|前|昨天|刚刚|today|yesterday|hour|day|week|month|year)/i.test(raw)) return raw;

  const ts = Date.parse(raw);
  if (Number.isNaN(ts)) return raw;

  const delta = Date.now() - ts;
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  if (delta < minute) return 'Just now';
  if (delta < hour) return `${Math.floor(delta / minute)} minutes ago`;
  if (delta < day) return `${Math.floor(delta / hour)} hours ago`;
  if (delta < day * 2) return 'Yesterday';
  if (delta < day * 7) return `${Math.floor(delta / day)} days ago`;
  if (delta < day * 30) return `${Math.floor(delta / (day * 7))} weeks ago`;
  if (delta < day * 365) return `${Math.floor(delta / (day * 30))} months ago`;
  return `${Math.floor(delta / (day * 365))} years ago`;
};

const fetchedAtLabel = computed(() => {
  const raw = String(fetchedAt.value || '').trim();
  if (!raw) return '';
  const ts = Date.parse(raw);
  if (Number.isNaN(ts)) return raw.replace('T', ' ').replace('Z', '');
  return new Date(ts).toLocaleString();
});

const mappedItems = computed(() =>
  (items.value || []).map((item) => ({
    ...item,
    categoryLabel: resolveCategory(item),
    timeLabel: toRelativeTime(item.date || item.publishedAt || fetchedAt.value),
  })),
);

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
      error.value = '请先在后端配置 SERPER_API_KEY 才能使用 AI 资讯。';
    } else {
      error.value = err.message || '加载失败';
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

<style>
@import url("https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&family=Inter:wght@300;400;500;600&family=Noto+Sans+SC:wght@400;500;600;700;800&display=swap");
@import url("https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap");

.ai-news-page {
  min-height: 100vh;
  background: #f7f9fb;
  color: #2c3437;
  font-family: "Inter", "Noto Sans SC", sans-serif;
}

.ai-news-page .material-symbols-outlined {
  font-family: "Material Symbols Outlined";
  font-variation-settings: "FILL" 0, "wght" 400, "GRAD" 0, "opsz" 24;
}

.ai-news-topbar {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 30;
  background: rgba(247, 249, 251, 0.72);
  backdrop-filter: blur(18px);
  border-bottom: 1px solid rgba(172, 179, 183, 0.18);
}

.ai-news-topbar-inner {
  max-width: 60rem;
  margin: 0 auto;
  padding: 0.9rem 1.6rem;
  display: flex;
  justify-content: flex-end;
  align-items: center;
}

.ai-news-back {
  border: 1px solid rgba(116, 124, 128, 0.24) !important;
  background: rgba(255, 255, 255, 0.82) !important;
  color: #005bc4 !important;
  border-radius: 999px !important;
  box-shadow: none !important;
  transform: none !important;
  padding: 0.45rem 0.9rem !important;
  font-size: 0.8rem !important;
  font-weight: 600 !important;
  cursor: pointer;
}

.ai-news-back:hover {
  background: #fff !important;
  border-color: rgba(0, 91, 196, 0.32) !important;
}

.ai-news-main {
  max-width: 48rem;
  margin: 0 auto;
  padding: 7.8rem 1.5rem 6rem;
}

.ai-news-header {
  margin-bottom: 2.9rem;
}

.ai-news-header h1 {
  margin: 0;
  color: #2c3437;
  font-family: "Manrope", "Noto Sans SC", sans-serif;
  font-size: 3.5rem;
  font-weight: 800;
  line-height: 1.08;
  letter-spacing: -0.02em;
}

.ai-news-header p {
  margin: 0.5rem 0 0;
  color: #596064;
  font-size: 1.12rem;
  font-weight: 400;
}

.ai-news-tools {
  display: flex;
  gap: 0.6rem;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 1rem;
}

.ai-news-refresh {
  border: none !important;
  background: transparent !important;
  box-shadow: none !important;
  transform: none !important;
  color: #596064 !important;
  font-size: 0.8rem !important;
  font-weight: 500 !important;
  padding: 0 !important;
  display: inline-flex;
  gap: 0.2rem;
  align-items: center;
  cursor: pointer;
}

.ai-news-refresh .material-symbols-outlined {
  font-size: 1rem;
}

.ai-news-refresh:hover:not(:disabled) {
  color: #005bc4 !important;
}

.ai-news-refresh:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.ai-news-tools-meta {
  color: #747c80;
  font-size: 0.72rem;
  font-weight: 500;
}

.ai-news-error {
  margin-bottom: 0.9rem;
  border-radius: 0.75rem;
  padding: 0.62rem 0.85rem;
  color: #a83836;
  background: rgba(250, 116, 111, 0.2);
  font-size: 0.82rem;
}

.ai-news-feed {
  display: flex;
  flex-direction: column;
  gap: 3rem;
}

.ai-news-empty {
  color: #596064;
  font-size: 0.9rem;
}

.ai-news-item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 5rem;
  gap: 2rem;
  align-items: start;
}

.ai-news-item-main {
  text-decoration: none;
  color: inherit;
}

.ai-news-item-meta {
  display: flex;
  align-items: center;
  gap: 0.58rem;
}

.ai-news-category {
  color: #005bc4;
  font-size: 0.66rem;
  font-weight: 700;
  letter-spacing: 0.14em;
  text-transform: uppercase;
}

.ai-news-dot {
  width: 0.2rem;
  height: 0.2rem;
  border-radius: 999px;
  background: rgba(116, 124, 128, 0.5);
}

.ai-news-time {
  color: #596064;
  font-size: 0.72rem;
  font-weight: 500;
}

.ai-news-title {
  margin: 0.52rem 0 0;
  color: #2c3437;
  font-family: "Manrope", "Noto Sans SC", sans-serif;
  font-size: 1.95rem;
  font-weight: 700;
  line-height: 1.35;
  transition: color 300ms ease-out;
}

.ai-news-item:hover .ai-news-title {
  color: #005bc4;
}

.ai-news-snippet {
  margin: 0.34rem 0 0;
  color: #596064;
  font-size: 0.84rem;
  line-height: 1.55;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 1;
  overflow: hidden;
}

.ai-news-source {
  margin-top: 0.42rem;
  display: inline-flex;
  align-items: center;
  gap: 0.24rem;
  color: #747c80;
  font-size: 0.72rem;
  font-weight: 500;
}

.ai-news-source .material-symbols-outlined {
  font-size: 0.9rem;
}

.ai-news-thumb {
  width: 5rem;
  height: 5rem;
  border-radius: 0.75rem;
  overflow: hidden;
  background: #eaeff2;
  box-shadow: 0 10px 30px rgba(44, 52, 55, 0.06);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  text-decoration: none;
  color: inherit;
}

.ai-news-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: 0.92;
  transition: transform 500ms ease-out;
}

.ai-news-item:hover .ai-news-thumb img {
  transform: scale(1.05);
}

.ai-news-thumb.placeholder {
  background: radial-gradient(circle at 35% 30%, #fff, #eef4ff 42%, #d9e5ff 100%);
  color: #6993d8;
}

.ai-news-thumb.placeholder .material-symbols-outlined {
  font-size: 1.35rem;
}

@media (max-width: 900px) {
  .ai-news-main {
    padding-top: 7.2rem;
  }

  .ai-news-header h1 {
    font-size: 2.8rem;
  }

  .ai-news-title {
    font-size: 1.4rem;
  }
}

@media (max-width: 700px) {
  .ai-news-topbar-inner {
    padding: 0.8rem 1rem;
  }

  .ai-news-main {
    padding: 6.8rem 1rem 4.2rem;
  }

  .ai-news-header h1 {
    font-size: 2.2rem;
  }

  .ai-news-header p {
    font-size: 0.98rem;
  }

  .ai-news-feed {
    gap: 1.4rem;
  }

  .ai-news-item {
    grid-template-columns: minmax(0, 1fr) 4.5rem;
    gap: 0.75rem;
  }

  .ai-news-thumb {
    width: 4.5rem;
    height: 4.5rem;
  }
}
</style>
