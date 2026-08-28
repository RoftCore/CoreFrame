let extensionsData = {};
let widgetTimers = {};
let extensionLoadState = {};

// ── Extension loading ─────────────────────────────────────────────

async function loadExtensionsAsync() {
  try {
    const data = await apiFetch('/api/extensions');
    if (data && !data.error) {
      extensionsData = data;
      window.extensionsData = data;
      for (const [extId, ext] of Object.entries(data)) {
        extensionLoadState[extId] = {
          status: ext.loadError ? 'error' : 'loaded',
          loadError: ext.loadError,
        };
      }
      buildSidebar(data);
      renderWidgets(data);
      loadExtensionAssets(data);
    }
  } catch (e) {
    console.error('Initial extension load failed:', e);
  }
}

async function pollExtensionUpdates() {
  try {
    const health = await apiFetch('/api/extensions/health');
    if (!health || health.error) return;
    let hasChanges = false;
    for (const [extId, info] of Object.entries(health)) {
      const prevState = extensionLoadState[extId] || { status: 'unknown' };
      extensionLoadState[extId] = {
        status: info.status,
        loadError: info.load_error,
        loaded: info.loaded,
      };
      if (prevState.status !== info.status || prevState.loaded !== info.loaded) {
        hasChanges = true;
        if (info.loaded && !prevState.loaded) {
          const extData = await apiFetch('/api/extensions');
          if (extData && extData[extId]) {
            extensionsData = extData;
            window.extensionsData = extData;
            addExtensionToUI(extId, extData[extId]);
          }
        } else if (info.status === 'error' || info.status === 'dead') {
          updateExtensionStatusInSidebar(extId, info.status, info.last_error);
        } else if (info.status === 'loading') {
          updateExtensionStatusInSidebar(extId, 'loading');
        }
      }
    }
    if (hasChanges && window.__widgetControl) {
      window.__widgetControl.applyWidgetState();
    }
  } catch (e) {}
}

// ── Extension UI ──────────────────────────────────────────────────

function addExtensionToUI(extId, ext) {
  const sidebar = document.getElementById('sidebar-extensions');
  if (sidebar) {
    const existing = sidebar.querySelector(`.sidebar-ext[data-ext-id="${extId}"]`);
    if (!existing) {
      const item = createSidebarExtensionItem(ext, extId);
      sidebar.appendChild(item);
    }
  }
  if (ext.widgets && ext.widgets.length > 0) {
    const grid = document.querySelector('.widget-grid');
    if (grid && !grid.querySelector(`.widget-extension.ext-${extId}`)) {
      const card = createExtensionCard({ ...ext, id: extId });
      grid.appendChild(card);
      loadExtensionAssets({ [extId]: ext });
      if (!ext.realtime) {
        const interval = ext.refresh_interval || 5000;
        if (interval > 0) {
          ext.widgets.forEach(wDef => {
            const key = `${extId}-${wDef.id}`;
            widgetTimers[key] = setInterval(() => refreshWidget(extId, wDef), interval);
          });
        }
      }
      ext.widgets.forEach(wDef => refreshWidget(extId, wDef));
    }
  }
  if (window.__widgetControl) {
    window.__widgetControl.applyWidgetState();
  }
}

function updateExtensionStatusInSidebar(extId, status, error = '') {
  const item = document.querySelector(`.sidebar-ext[data-ext-id="${extId}"]`);
  if (!item) return;
  const statusEl = item.querySelector('.ext-status');
  if (statusEl) {
    statusEl.className = `ext-status ${status}`;
    if (status === 'error' || status === 'dead') {
      statusEl.title = error || 'Failed to load';
    } else if (status === 'loading') {
      statusEl.title = 'Loading...';
    } else {
      statusEl.title = 'Loaded';
    }
  }
}

function createSidebarExtensionItem(ext, extId) {
  const item = document.createElement('div');
  item.className = 'sidebar-ext';
  item.dataset.extId = extId;
  const isError = extensionLoadState[extId]?.status === 'error';
  const isLoading = extensionLoadState[extId]?.status === 'loading';
  item.innerHTML = `
    <span class="ext-icon">${ext.icon || '📦'}</span>
    <span class="ext-name">${escapeHtml(ext.name || extId)}</span>
    <span class="ext-status ${isError ? 'error' : isLoading ? 'loading' : 'loaded'}" 
          title="${isError ? escapeHtml(extensionLoadState[extId].loadError || 'Error') : isLoading ? 'Loading...' : 'Loaded'}">
      ${isError ? '✗' : isLoading ? '⟳' : '✓'}
    </span>
  `;
  item.addEventListener('click', () => {
    const widget = document.querySelector(`.widget-extension.ext-${extId}`);
    if (widget) {
      widget.scrollIntoView({ behavior: 'smooth', block: 'center' });
      widget.style.animation = 'pulse 1s ease';
      setTimeout(() => widget.style.animation = '', 1000);
    }
  });
  return item;
}

// ── Asset loading ─────────────────────────────────────────────────

function loadExtensionAssets(data) {
  var light = [];
  var heavy = [];
  for (var extId in data) {
    var ext = data[extId];
    var jsCount = (ext.js_modules || []).length;
    var cssCount = (ext.css_modules || []).length;
    var isNode = ext.language === 'node' || ext.language === 'javascript';
    var isHeavy = isNode || jsCount > 2 || cssCount > 2;
    if (isHeavy) heavy.push([extId, ext]);
    else light.push([extId, ext]);
  }
  function loadExtAssets(extId, ext) {
    for (var i = 0; i < (ext.js_modules || []).length; i++) {
      (function (mod) {
        var src = '/ext-static/' + extId + '/' + mod;
        if (document.querySelector('script[src="' + src + '"]')) return;
        var script = document.createElement('script');
        script.src = src;
        script.onerror = function () { console.warn('[EXT] Failed to load ' + mod); };
        document.body.appendChild(script);
      })(ext.js_modules[i]);
    }
    for (var j = 0; j < (ext.css_modules || []).length; j++) {
      (function (cssMod) {
        var href = '/ext-static/' + extId + '/' + cssMod;
        if (document.querySelector('link[href="' + href + '"]')) return;
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = href;
        link.onerror = function () { console.warn('[EXT] Failed to load CSS for ' + extId + ': ' + cssMod); };
        document.head.appendChild(link);
      })(ext.css_modules[j]);
    }
  }
  light.forEach(function (pair) { loadExtAssets(pair[0], pair[1]); });
  if (heavy.length) {
    setTimeout(function () {
      heavy.forEach(function (pair) { loadExtAssets(pair[0], pair[1]); });
    }, 500);
  }
}

// ── Widget rendering ──────────────────────────────────────────────

function renderWidgets(data) {
  const container = document.getElementById('main-content');
  if (typeof clearProgressTimers === 'function') clearProgressTimers();
  if (typeof clearDropdownMenus === 'function') clearDropdownMenus();
  container.innerHTML = '';
  const grid = document.createElement('div');
  grid.className = 'widget-grid';
  for (const [extId, ext] of Object.entries(data)) {
    if (!ext.widgets || ext.widgets.length === 0) continue;
    try {
      const card = createExtensionCard({ ...ext, id: extId });
      grid.appendChild(card);
    } catch (e) {
      console.error('[EXT] Failed to render card for ' + extId + ':', e);
    }
  }
  container.style.visibility = 'hidden';
  container.appendChild(grid);
  refreshAllWidgets(data);
  startWidgetIntervals(data);
  if (window.__widgetControl) window.__widgetControl.applyWidgetState();
}

function refreshAllWidgets(data) {
  for (const [extId, ext] of Object.entries(data)) {
    if (ext.js_modules && ext.js_modules.length) continue;
    for (const wDef of (ext.widgets || [])) {
      try { refreshWidget(extId, wDef); } catch (e) {
        console.error('[EXT] Error refreshing ' + extId + ':', e);
      }
    }
  }
}

async function refreshWidget(extId, wDef) {
  const el = document.querySelector(`[data-widget-id="${wDef.id}"][data-ext-id="${extId}"]`);
  if (!el) return;
  if (wDef.action) {
    try {
      const response = await apiFetch(`/api/extension/${extId}/${wDef.action}`);
      updateWidgetValue(el, response);
    } catch (e) {
      try { updateWidgetValue(el, { error: 'Connection error' }); } catch (e2) {}
    }
  }
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
