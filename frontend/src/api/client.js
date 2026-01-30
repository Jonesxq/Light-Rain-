const API_BASE_KEY = 'apiBase';
const TOKEN_KEY = 'accessToken';
const REFRESH_KEY = 'refreshToken';

// export function getApiBase() {
//   return localStorage.getItem(API_BASE_KEY) || 'http://127.0.0.1:8000/api/v1';
// }
export function getApiBase() {
  // 允许你手动覆盖（比如未来你有真实线上 API）
  const saved = localStorage.getItem(API_BASE_KEY);
  if (saved) return saved;

  // 默认走同域名相对路径（关键）
  // 本地开发：Vite proxy 会把 /api/v1 转发到 http://127.0.0.1:8000
  // 朋友/手机：访问 trycloudflare 域名，也会请求同域名的 /api/v1
  return '/api/v1';
}


export function setApiBase(value) {
  localStorage.setItem(API_BASE_KEY, value);
}

export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || '';
}

export function setTokens(accessToken, refreshToken) {
  localStorage.setItem(TOKEN_KEY, accessToken || '');
  if (refreshToken) {
    localStorage.setItem(REFRESH_KEY, refreshToken);
  }
}

export function clearTokens() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
}

export async function apiFetch(
  path,
  { method = 'GET', body = null, headers = {}, skipAuth = false, timeoutMs = 30000 } = {},
) {
  const finalHeaders = { ...headers };
  const token = getToken();
  if (!skipAuth && token) {
    finalHeaders.Authorization = `Bearer ${token}`;
  }

  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  let payload = body;
  if (body && !(body instanceof FormData)) {
    finalHeaders['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(`${getApiBase()}${path}`, {
      method,
      headers: finalHeaders,
      body: payload,
      signal: controller.signal,
    });
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('请求超时，请检查网络或稍后重试');
    }
    throw error;
  } finally {
    clearTimeout(timeoutId);
  }

  if (response.status === 204) {
    return null;
  }

  let data = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    if (response.status === 401 && !skipAuth) {
      clearTokens();
    }
    const message = data?.detail || data?.error || response.statusText;
    throw new Error(message);
  }

  return data;
}
