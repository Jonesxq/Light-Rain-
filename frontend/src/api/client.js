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

function parseSseEventLines(lines) {
  const dataLines = [];
  for (const rawLine of lines) {
    const line = rawLine.replace(/\r$/, '');
    if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (!dataLines.length) return null;
  return dataLines.join('\n');
}

export async function apiStream(
  path,
  {
    method = 'POST',
    body = null,
    headers = {},
    skipAuth = false,
    onMessage = null,
    signal = null,
    timeoutMs = null,
  } = {},
) {
  const finalHeaders = { Accept: 'text/event-stream', ...headers };
  const token = getToken();
  if (!skipAuth && token) {
    finalHeaders.Authorization = `Bearer ${token}`;
  }

  let payload = body;
  if (body && !(body instanceof FormData)) {
    finalHeaders['Content-Type'] = 'application/json';
    payload = JSON.stringify(body);
  }

  const controller = !signal && timeoutMs ? new AbortController() : null;
  const requestSignal = signal || controller?.signal;
  let timeoutId = null;
  if (controller && timeoutMs) {
    timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  }

  let response;
  try {
    response = await fetch(`${getApiBase()}${path}`, {
      method,
      headers: finalHeaders,
      body: payload,
      signal: requestSignal,
    });
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('请求已取消');
    }
    throw error;
  } finally {
    if (timeoutId) {
      clearTimeout(timeoutId);
    }
  }

  if (!response.ok) {
    let data = null;
    try {
      data = await response.json();
    } catch {
      data = null;
    }
    if (response.status === 401 && !skipAuth) {
      clearTokens();
    }
    const message = data?.detail || data?.error || response.statusText;
    throw new Error(message);
  }

  if (!response.body) {
    throw new Error('当前环境不支持流式响应');
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder('utf-8');
  let buffer = '';

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split(/\r?\n\r?\n/);
    buffer = parts.pop() || '';
    for (const part of parts) {
      const dataText = parseSseEventLines(part.split(/\n/));
      if (!dataText) continue;
      let payloadData = dataText;
      try {
        payloadData = JSON.parse(dataText);
      } catch {
        payloadData = dataText;
      }
      if (onMessage) {
        onMessage(payloadData);
      }
    }
  }

  const remaining = buffer.trim();
  if (remaining) {
    const dataText = parseSseEventLines(remaining.split(/\n/));
    if (dataText && onMessage) {
      let payloadData = dataText;
      try {
        payloadData = JSON.parse(dataText);
      } catch {
        payloadData = dataText;
      }
      onMessage(payloadData);
    }
  }
}
