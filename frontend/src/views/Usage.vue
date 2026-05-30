<template>
  <div class="page usage-page">
    <header class="header">
      <div>
        <h1>使用量与成本</h1>
        <p>追踪 token、请求、延迟与成本，掌握预算与限流情况。</p>
      </div>
      <div class="header-actions">
        <div class="actions action-bar">
          <button class="ghost" @click="goChat">返回聊天</button>
        </div>
      </div>
    </header>

    <div v-if="notice" class="notice">{{ notice }}</div>
    <div v-if="error" class="error">{{ error }}</div>

    <section class="summary-grid" v-if="overview">
      <div class="summary-card">
        <h3>总请求</h3>
        <div class="summary-value">{{ formatNumber(overview.total_requests) }}</div>
        <div class="summary-sub">近 {{ rangeDays }} 天</div>
      </div>
      <div class="summary-card">
        <h3>总 Token</h3>
        <div class="summary-value">{{ formatNumber(overview.total_tokens) }}</div>
        <div class="summary-sub">缺失 {{ formatNumber(overview.token_missing_count) }} 次</div>
      </div>
      <div class="summary-card">
        <h3>平均延迟</h3>
        <div class="summary-value">{{ formatMs(overview.avg_latency_ms) }}</div>
        <div class="summary-sub">全量请求平均</div>
      </div>
      <div class="summary-card highlight">
        <h3>总成本</h3>
        <div class="summary-value">${{ formatCost(overview.total_cost_usd) }}</div>
        <div class="summary-sub">近 {{ rangeDays }} 天</div>
      </div>
    </section>

    <section class="card budget-section" v-if="overview">
      <div class="card-head">
        <h2>预算与限流提醒</h2>
        <span class="hint">不阻断请求，仅提示</span>
      </div>
      <div class="budget-grid">
        <div class="budget-item">
          <div class="budget-title">月度预算</div>
          <div class="budget-value">
            <strong>${{ formatCost(overview.budget_status.monthly_cost_usd) }}</strong>
            <span>/ ${{ formatCost(overview.budget_status.monthly_budget_usd) }}</span>
          </div>
          <div class="progress">
            <div
              class="progress-fill"
              :style="{ width: `${Math.min(100, overview.budget_status.budget_used_ratio * 100)}%` }"
            ></div>
          </div>
          <div v-if="overview.budget_status.is_over_budget" class="warn">已超出预算</div>
        </div>
        <div class="budget-item">
          <div class="budget-title">今日请求</div>
          <div class="budget-value">
            <strong>{{ formatNumber(overview.rate_status.today_request_count) }}</strong>
            <span>/ {{ formatNumber(overview.rate_status.daily_request_limit) }}</span>
          </div>
          <div class="progress">
            <div
              class="progress-fill"
              :style="{ width: `${Math.min(100, overview.rate_status.rate_used_ratio * 100)}%` }"
            ></div>
          </div>
          <div v-if="overview.rate_status.is_over_limit" class="warn">已超出限额</div>
        </div>
      </div>
    </section>

    <section class="card chart-section">
      <div class="card-head">
        <h2>趋势</h2>
        <div class="chip-group">
          <button :class="{ active: metric === 'tokens' }" @click="metric = 'tokens'">Token</button>
          <button :class="{ active: metric === 'requests' }" @click="metric = 'requests'">请求</button>
          <button :class="{ active: metric === 'latency' }" @click="metric = 'latency'">延迟</button>
          <button :class="{ active: metric === 'cost' }" @click="metric = 'cost'">成本</button>
        </div>
      </div>
      <div class="chart" v-if="chartSeries.length">
        <div class="chart-bar" v-for="item in chartSeries" :key="item.date">
          <div class="bar" :style="{ height: `${item.height}%` }"></div>
          <span>{{ formatDateLabel(item.date) }}</span>
        </div>
      </div>
      <div v-else class="empty">暂无数据</div>
    </section>

    <section class="grid-two">
      <div class="card">
        <div class="card-head">
          <h2>按模型统计</h2>
        </div>
        <table class="table">
          <thead>
            <tr>
              <th>模型</th>
              <th>请求</th>
              <th>Token</th>
              <th>成本</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in overview?.by_model || []" :key="row.key">
              <td>{{ row.key }}</td>
              <td>{{ formatNumber(row.request_count) }}</td>
              <td>{{ formatNumber(row.total_tokens) }}</td>
              <td>${{ formatCost(row.total_cost_usd) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="card">
        <div class="card-head">
          <h2>按类型统计</h2>
        </div>
        <table class="table">
          <thead>
            <tr>
              <th>类型</th>
              <th>请求</th>
              <th>Token</th>
              <th>成本</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in overview?.by_type || []" :key="row.key">
              <td>{{ row.key }}</td>
              <td>{{ formatNumber(row.request_count) }}</td>
              <td>{{ formatNumber(row.total_tokens) }}</td>
              <td>${{ formatCost(row.total_cost_usd) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section class="card settings-card">
      <div class="card-head">
        <h2>预算与限流设置</h2>
        <span class="hint">保存后立即生效，仅提醒</span>
      </div>
      <div class="form-grid">
        <label>
          月度预算（USD）
          <input v-model="settingsForm.monthly_budget_usd" type="number" min="0" step="0.01" />
        </label>
        <label>
          每日请求限额
          <input v-model="settingsForm.daily_request_limit" type="number" min="0" step="1" />
        </label>
      </div>
      <div class="actions">
        <button @click="saveSettings">保存设置</button>
        <button class="ghost" @click="reloadAll">刷新</button>
      </div>
      <div v-if="overview" class="settings-hint">
        缺失 Token 的请求：{{ formatNumber(overview.token_missing_count) }} 次（不计入成本）
      </div>
    </section>

    <CenterToast :message="successMessage" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { apiFetch } from '../api/client.js';
import CenterToast from '../components/CenterToast.vue';
import { useCenterToast } from '../composables/useCenterToast.js';

const router = useRouter();
const notice = ref('');
const error = ref('');
const { message: successMessage, show: showSuccess } = useCenterToast();

const rangeDays = 30;
const overview = ref(null);
const timeseries = ref([]);
const metric = ref('tokens');
const settingsForm = ref({
  monthly_budget_usd: 0,
  daily_request_limit: 0,
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

const loadOverview = async () => {
  const data = await apiFetch(`/usage/overview?range_days=${rangeDays}`);
  overview.value = data;
};

const loadTimeseries = async () => {
  const data = await apiFetch(`/usage/timeseries?range_days=${rangeDays}`);
  timeseries.value = data?.series || [];
};

const loadSettings = async () => {
  const data = await apiFetch('/usage/settings/me');
  settingsForm.value.monthly_budget_usd = data?.monthly_budget_usd ?? 0;
  settingsForm.value.daily_request_limit = data?.daily_request_limit ?? 0;
};

const reloadAll = async () => {
  error.value = '';
  try {
    await Promise.all([loadOverview(), loadTimeseries(), loadSettings()]);
  } catch (err) {
    setError(err.message || '加载失败');
  }
};

const saveSettings = async () => {
  try {
    const payload = {
      monthly_budget_usd: Number(settingsForm.value.monthly_budget_usd || 0),
      daily_request_limit: Number(settingsForm.value.daily_request_limit || 0),
    };
    await apiFetch('/usage/settings/me', { method: 'PUT', body: payload });
    setNotice('设置已保存');
    await reloadAll();
  } catch (err) {
    setError(err.message || '保存失败');
  }
};

const chartSeries = computed(() => {
  const items = timeseries.value || [];
  const values = items.map((item) => {
    if (metric.value === 'requests') return item.request_count || 0;
    if (metric.value === 'latency') return item.avg_latency_ms || 0;
    if (metric.value === 'cost') return item.total_cost_usd || 0;
    return item.total_tokens || 0;
  });
  const maxValue = Math.max(1, ...values);
  return items.map((item, idx) => {
    const raw = values[idx] || 0;
    return {
      date: item.date,
      value: raw,
      height: Math.round((raw / maxValue) * 100),
    };
  });
});

const formatNumber = (value) => Number(value || 0).toLocaleString();
const formatCost = (value) => Number(value || 0).toFixed(2);
const formatMs = (value) => `${Math.round(value || 0)} ms`;
const formatDateLabel = (date) => (date || '').slice(5);

onMounted(() => {
  reloadAll();
});
</script>

<style scoped>
.usage-page {
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

.usage-page::before {
  content: none;
  display: none;
}

.usage-page > * {
  position: relative;
  z-index: 1;
}

.header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
}

.header h1 {
  margin: 0;
  font-size: 26px;
}

.header p {
  margin: 6px 0 0;
  color: var(--text-muted);
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

label {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
}

input {
  padding: 10px 12px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface-soft);
  font-size: 13px;
}

button {
  border: none;
  padding: 10px 16px;
  border-radius: var(--radius-sm);
  background: var(--accent-gradient);
  color: #fff;
  font-weight: 600;
  cursor: pointer;
  box-shadow: var(--shadow-sm);
}

button.ghost {
  background: rgba(255, 255, 255, 0.7);
  color: var(--accent-strong);
  border: 1px solid rgba(59, 130, 246, 0.25);
  box-shadow: none;
}

.notice,
.error {
  margin-top: 8px;
  border-radius: 12px;
  padding: 10px 14px;
  font-size: 13px;
}

.notice {
  background: var(--notice-bg);
  color: var(--notice-text);
}

.error {
  background: var(--error-bg);
  color: var(--error-text);
}

.summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.summary-card {
  background: var(--surface-strong);
  border-radius: 18px;
  padding: 16px;
  box-shadow: var(--shadow-md);
  border: 1px solid var(--border);
  animation: fade-up 0.35s ease both;
}

.summary-card.highlight {
  background: rgba(59, 130, 246, 0.08);
}

.summary-value {
  font-size: 24px;
  font-weight: 700;
  margin-top: 6px;
}

.summary-sub {
  font-size: 12px;
  color: #6b7390;
  margin-top: 4px;
}

.card {
  background: var(--surface-strong);
  border-radius: var(--radius-lg);
  padding: 18px;
  box-shadow: var(--shadow-md);
  border: 1px solid var(--border);
}

.card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.card-head .hint {
  font-size: 12px;
  color: var(--text-soft);
}

.budget-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 14px;
}

.budget-item {
  background: var(--surface-soft);
  border-radius: 16px;
  padding: 12px;
  border: 1px solid var(--border);
}

.budget-title {
  font-size: 13px;
  color: var(--text-muted);
}

.budget-value {
  margin-top: 6px;
  font-size: 16px;
}

.progress {
  margin-top: 10px;
  height: 8px;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.2);
  overflow: hidden;
}

.progress-fill {
  height: 100%;
  background: var(--accent-gradient);
}

.warn {
  margin-top: 8px;
  font-size: 12px;
  color: #b91c1c;
}

.chart-section {
  min-height: 200px;
}

.chip-group {
  display: flex;
  gap: 8px;
}

.chip-group button {
  padding: 6px 12px;
  border-radius: 12px;
  border: 1px solid rgba(59, 130, 246, 0.25);
  background: rgba(255, 255, 255, 0.7);
  color: var(--accent-strong);
  font-size: 12px;
  box-shadow: none;
}

.chip-group button.active {
  background: var(--accent-gradient);
  color: #fff;
  border: none;
}

.chart {
  margin-top: 12px;
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(20px, 1fr));
  gap: 6px;
  align-items: end;
  height: 140px;
}

.chart-bar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
  font-size: 10px;
  color: var(--text-soft);
}

.chart-bar .bar {
  width: 100%;
  max-width: 28px;
  border-radius: 8px;
  background: var(--accent-gradient);
}

.empty {
  font-size: 12px;
  color: var(--text-soft);
}

.grid-two {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 14px;
}

.table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.table thead {
  text-align: left;
  color: var(--text-muted);
}

.table td,
.table th {
  padding: 8px 4px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.3);
}

.settings-card .form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
  margin-bottom: 12px;
}

.settings-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-soft);
}

@media (max-width: 1080px) {
  .usage-page {
    width: 100%;
    height: auto;
    max-height: none;
    margin: 16px auto;
  }

  .header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
