// ── CoreFrame Bootstrap ───────────────────────────────────────────
// This file initializes the app. All logic lives in:
//   app.js      — extension loading, polling, sidebar, widget rendering
//   install.js  — marketplace, providers, package, install from file
//   window.js   — window mode, F11, minimize, settings
//   widgets.js  — widget creation, updates, charts
//   menu.js     — sidebar menu actions
//   utils.js    — API helpers, formatting

document.addEventListener('DOMContentLoaded', async () => {
  document.body.classList.add('booting');

  clockTick();
  setInterval(clockTick, 1000);

  setTimeout(() => {
    const ae = document.activeElement;
    if (ae && ae !== document.body && typeof ae.blur === 'function') ae.blur();
  }, 50);

  document.getElementById('btn-reload').style.display = '';
  if (typeof _COREFRAME_DEBUG !== 'undefined' && _COREFRAME_DEBUG) {
    document.getElementById('btn-package').style.display = '';
    document.body.classList.add('mode-debug');
  }

  initResultPanel();
  initWebSocket();

  // Initialize permission handlers after WebSocket is ready
  if (window.__permissions) {
    window.__permissions.initPermissionHandlers();
    // Check for pending consents/migrations on startup
    setTimeout(() => window.__permissions.checkPendingOnStartup(), 1500);
  }

  const loadingEl = document.getElementById('main-content');
  loadingEl.innerHTML = '<div class="widget-grid"></div>';

  loadExtensionsAsync();
  setInterval(pollExtensionUpdates, 1000);
  applyStartupMode();
});

// ── Result panel ──────────────────────────────────────────────────

function initResultPanel() {
  document.getElementById('result-panel-close').addEventListener('click', closeResultPanel);
  document.getElementById('overlay').addEventListener('click', closeResultPanel);
}

function closeResultPanel() {
  document.getElementById('result-panel').classList.remove('open');
  document.getElementById('overlay').classList.remove('open');
}

// ── Button listeners ──────────────────────────────────────────────

document.getElementById('btn-install').addEventListener('click', function () {
  showInstallChoice();
});

document.getElementById('btn-package').addEventListener('click', function () {
  showPackageDialog();
});

document.getElementById('btn-reload').addEventListener('click', async () => {
  const btn = document.getElementById('btn-reload');
  btn.textContent = '↻';
  btn.style.animation = 'spin 0.6s linear infinite';
  try { await apiFetch('/api/restart', { method: 'POST' }); } catch (e) {}
  setTimeout(() => location.reload(), 500);
});

// ── WebSocket ─────────────────────────────────────────────────────

function initWebSocket() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${location.host}`;
  const socket = io(wsUrl, {
    transports: ['polling'],
    reconnection: true,
    reconnectionAttempts: 30,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,
  });
  window.__socket = socket;

  function updateDot() {
    var el = document.getElementById('connection-dot');
    if (!el) return;
    el.className = socket.connected ? 'hud-dot ok' : 'hud-dot error';
  }
  socket.on('connect', updateDot);
  socket.on('disconnect', updateDot);
  updateDot();
  setInterval(updateDot, 3000);

  socket.on('realtime_update', (data) => {
    if (!data.ext || !data.values) return;
    if (!window.extensionsData) return;
    Object.keys(data.values).forEach(id => {
      const el = document.querySelector(`[data-widget-id="${id}"][data-ext-id="${data.ext}"]`);
      if (el) updateWidgetValue(el, { value: data.values[id] });
    });
  });

  socket.on('focus_window', () => {
    if (window.pywebview) pywebview.api.focus_window().catch(() => {});
    window.focus();
    document.body.focus();
  });
}
