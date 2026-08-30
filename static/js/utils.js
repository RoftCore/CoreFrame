let _COREFRAME_TOKEN = null;
async function ensureToken() {
  if (!_COREFRAME_TOKEN) {
    try {
      const res = await fetch('/api/token');
      const data = await res.json();
      _COREFRAME_TOKEN = data.token;
    } catch {}
  }
}

async function apiFetch(url, options = {}) {
  await ensureToken();
  try {
    var headers = {};
    if (options.headers && typeof options.headers === 'object') {
      for (var key in options.headers) headers[key] = options.headers[key];
    }
    if (_COREFRAME_TOKEN) headers['X-CoreFrame-Token'] = _COREFRAME_TOKEN;
    if (typeof options.body === 'string' && !headers['Content-Type']) {
      headers['Content-Type'] = 'application/json';
    }
    delete options.headers;
    var timeout = (options && options.timeout) || 90000;
    const controller = new AbortController();
    var timeoutId = setTimeout(function () { controller.abort(); }, timeout);
    var res;
    try {
      res = await fetch(url, { ...options, headers, signal: controller.signal });
    } finally {
      clearTimeout(timeoutId);
    }
    if (!res) return { error: 'Request timed out' };
    if (!res.ok) {
      const errBody = await res.json().catch(function () { return {}; });
      throw new Error(errBody.error || `HTTP ${res.status}`);
    }
    return await res.json();
  } catch (err) {
    var msg = err.name === 'AbortError' ? 'Request timed out' : err.message;
    console.error(`[API] ${url}: ${msg}`);
    return { error: msg };
  }
}

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i];
}

function formatPercent(value) {
  if (value === undefined || value === null) return '--';
  return value.toFixed(1) + '%';
}

function formatTemp(value) {
  if (value === undefined || value === null) return '--';
  return value.toFixed(0) + '°C';
}

function escapeHtml(text) {
  if (text === undefined || text === null) return '';
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

function clockTick() {
  const now = new Date();
  const h = String(now.getHours()).padStart(2, '0');
  const m = String(now.getMinutes()).padStart(2, '0');
  const s = String(now.getSeconds()).padStart(2, '0');
  document.getElementById('header-clock').textContent = `${h}:${m}:${s}`;
}
