let extensionsData = {};
let widgetTimers = {};

document.addEventListener('DOMContentLoaded', async () => {
  clockTick();
  setInterval(clockTick, 1000);

  initResultPanel();
  initWebSocket();

  const data = await apiFetch('/api/extensions');
  if (data.error) {
    document.getElementById('main-content').innerHTML = `<div class="loading"><div class="spinner"></div>Failed to connect: ${escapeHtml(data.error)}</div>`;
    return;
  }
  extensionsData = data;
  window.extensionsData = data;
  buildSidebar(data);
  renderWidgets(data);
  loadExtensionAssets(data);
});

function loadExtensionAssets(data) {
  for (const [extId, ext] of Object.entries(data)) {
    for (const mod of (ext.js_modules || [])) {
      const script = document.createElement('script');
      script.src = `/ext-static/${extId}/${mod}`;
      script.onload = () => console.log(`[EXT] Loaded ${mod} for ${extId}`);
      script.onerror = () => console.error(`[EXT] Failed to load ${mod}: ${script.src}`);
      document.body.appendChild(script);
    }
    for (const mod of (ext.css_modules || [])) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = `/ext-static/${extId}/${mod}`;
      document.head.appendChild(link);
    }
  }
}

function renderWidgets(data) {
  const container = document.getElementById('main-content');
  container.innerHTML = '';

  const grid = document.createElement('div');
  grid.className = 'widget-grid';

  for (const [extId, ext] of Object.entries(data)) {
    if (!ext.widgets || ext.widgets.length === 0) continue;
    const card = createExtensionCard({ ...ext, id: extId });
    grid.appendChild(card);
  }

  container.appendChild(grid);

  refreshAllWidgets(data);
  startWidgetIntervals(data);
  if (window.__widgetControl) window.__widgetControl.applyWidgetState();
}

function refreshAllWidgets(data) {
  for (const [extId, ext] of Object.entries(data)) {
    if (ext.js_modules && ext.js_modules.length) continue;
    for (const wDef of (ext.widgets || [])) {
      refreshWidget(extId, wDef);
    }
  }
}

async function refreshWidget(extId, wDef) {
  const el = document.querySelector(`[data-widget-id="${wDef.id}"][data-ext-id="${extId}"]`);
  if (!el) return;
  const response = await apiFetch(`/api/extension/${extId}/${wDef.action}`);
  updateWidgetValue(el, response);
}

function startWidgetIntervals(data) {
  for (const timer in widgetTimers) clearInterval(widgetTimers[timer]);

  for (const [extId, ext] of Object.entries(data)) {
    if (ext.realtime) continue;
    const interval = ext.refresh_interval || 5000;
    if (interval <= 0) continue;
    for (const wDef of (ext.widgets || [])) {
      const key = `${extId}-${wDef.id}`;
      widgetTimers[key] = setInterval(() => refreshWidget(extId, wDef), interval);
    }
  }
}

// --- WebSocket (generic realtime bus) ---
function initWebSocket() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${location.host}`;
  const socket = io(wsUrl, { transports: ['websocket'] });

  socket.on('connect', () => {
    document.getElementById('connection-dot').className = 'hud-dot ok';
  });

  socket.on('disconnect', () => {
    document.getElementById('connection-dot').className = 'hud-dot error';
  });

  socket.on('realtime_update', (data) => {
    if (!data.ext || !data.values) return;
    const ext = extensionsData[data.ext];
    if (ext && ext.js_modules && ext.js_modules.length) return;
    Object.keys(data.values).forEach(id => {
      const el = document.querySelector(`[data-widget-id="${id}"][data-ext-id="${data.ext}"]`);
      if (el) {
        updateWidgetValue(el, { value: data.values[id] });
      }
    });
  });
}

function initResultPanel() {
  document.getElementById('result-panel-close').addEventListener('click', closeResultPanel);
  document.getElementById('overlay').addEventListener('click', closeResultPanel);
}

function closeResultPanel() {
  document.getElementById('result-panel').classList.remove('open');
  document.getElementById('overlay').classList.remove('open');
}

document.getElementById('btn-reload').addEventListener('click', async () => {
  const btn = document.getElementById('btn-reload');
  btn.textContent = '↻';
  btn.style.animation = 'spin 0.6s linear infinite';
  try {
    await apiFetch('/api/restart', { method: 'POST' });
  } catch (e) {}
  let attempts = 0;
  const poll = () => {
    fetch('/api/token').then(r => { if (r.ok) location.reload(); else if (++attempts < 30) setTimeout(poll, 1000); else location.reload(); }).catch(() => { if (++attempts < 30) setTimeout(poll, 1000); else location.reload(); });
  };
  setTimeout(poll, 1500);
});
