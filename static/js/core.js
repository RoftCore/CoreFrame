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

  // ── Freeze attribution: any main-thread block (>200ms) is reported
  // with the culprit script URL to the backend log. Proves whether a
  // freeze comes from core files or an extension script.
  try {
    if (typeof PerformanceObserver !== 'undefined') {
      var _ltBuf = [];
      var _ltTimer = null;
      var _ltFlush = function () {
        if (!_ltBuf.length) return;
        var batch = _ltBuf.splice(0, _ltBuf.length);
        try {
          if (typeof apiFetch !== 'undefined') {
            apiFetch('/api/debug/longtask', { method: 'POST',
              body: JSON.stringify({ tasks: batch }) }).catch(function(){});
          }
        } catch (e) {}
      };
      new PerformanceObserver(function (list) {
        var es = list.getEntries();
        for (var i = 0; i < es.length; i++) {
          var e = es[i];
          if (e.duration < 200) continue;
          var src = '';
          try {
            var at = e.attribution && e.attribution[0];
            src = (at && (at.containerSrc || at.containerName)) || e.name || '';
          } catch (_) {}
          _ltBuf.push({ d: Math.round(e.duration), src: String(src).slice(-120) });
        }
        if (_ltBuf.length) {
          try { clearTimeout(_ltTimer); } catch (_) {}
          _ltTimer = setTimeout(_ltFlush, 2000);
        }
      }).observe({ entryTypes: ['longtask'] });
    }
  } catch (e) {}
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
    transports: ['websocket'],
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
    // Host immunity: no DOM writes mid-drag. Queue latest values only;
    // they flush on 'coreframe-dragend'. A heavy widget updating at 2s
    // can never jank a drag this way.
    if (window.__coreframeDragging) {
      window.__pendingWidgetUpdates = window.__pendingWidgetUpdates || {};
      Object.keys(data.values).forEach(id => {
        window.__pendingWidgetUpdates[data.ext + '|' + id] = { ext: data.ext, id: id, value: data.values[id] };
      });
      return;
    }
    Object.keys(data.values).forEach(id => {
      const el = document.querySelector(`[data-widget-id="${id}"][data-ext-id="${data.ext}"]`);
      if (!el) return;
      // Skip hidden widgets: no backend-independent work for unseen content.
      if (el.style.display === 'none') return;
      updateWidgetValue(el, { value: data.values[id] });
    });
  });

  // Flush queued realtime values once the gesture ends, time-sliced
  // (8ms budget per frame): applying every heavy redraw in a single
  // frame would be its own drop jolt.
  window.addEventListener('coreframe-dragend', () => {
    const pending = window.__pendingWidgetUpdates;
    window.__pendingWidgetUpdates = {};
    if (!pending) return;
    const entries = Object.keys(pending).map(k => pending[k]);
    if (!entries.length) return;
    let i = 0;
    const applyOne = (p) => {
      try {
        const el = document.querySelector(`[data-widget-id="${p.id}"][data-ext-id="${p.ext}"]`);
        if (!el) return;
        if (el.style.display === 'none') return;
        updateWidgetValue(el, { value: p.value });
      } catch (e) {}
    };
    const step = () => {
      const t0 = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
      while (i < entries.length) {
        applyOne(entries[i++]);
        const now = (typeof performance !== 'undefined' && performance.now) ? performance.now() : Date.now();
        if (now - t0 > 8 && i < entries.length) break;
      }
      if (i < entries.length) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  });

  socket.on('focus_window', () => {
    if (window.pywebview) pywebview.api.focus_window().catch(() => {});
    window.focus();
    document.body.focus();
  });
}
