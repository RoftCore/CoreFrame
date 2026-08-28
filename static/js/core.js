let extensionsData = {};
let widgetTimers = {};
let extensionLoadState = {}; // Tracks loading state per extension

document.addEventListener('DOMContentLoaded', async () => {
  // Boot lock: no hover/tooltip/click until the saved window mode is applied
  document.body.classList.add('booting');

  clockTick();
  setInterval(clockTick, 1000);

  // Clear any autofocus a control grabbed — prevents stuck floating tooltips
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

  // INSTANT: Show UI immediately, load extensions in background
  const loadingEl = document.getElementById('main-content');
  loadingEl.innerHTML = '<div class="widget-grid"></div>'; // Empty grid ready
  
  // Start async extension loading
  loadExtensionsAsync();
  
  // Poll for extension updates
  setInterval(pollExtensionUpdates, 1000);
  
  applyStartupMode();
});

async function loadExtensionsAsync() {
  try {
    const data = await apiFetch('/api/extensions');
    if (data && !data.error) {
      extensionsData = data;
      window.extensionsData = data;
      
      // Initialize load state for each extension
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
      
      // Update load state
      extensionLoadState[extId] = {
        status: info.status,
        loadError: info.load_error,
        loaded: info.loaded,
      };
      
      // Check for state changes
      if (prevState.status !== info.status || prevState.loaded !== info.loaded) {
        hasChanges = true;
        
        if (info.loaded && !prevState.loaded) {
          // Extension just loaded - add to UI
          const extData = await apiFetch('/api/extensions');
          if (extData && extData[extId]) {
            extensionsData = extData;
            window.extensionsData = extData;
            addExtensionToUI(extId, extData[extId]);
          }
        } else if (info.status === 'error' || info.status === 'dead') {
          // Extension failed - show error in sidebar
          updateExtensionStatusInSidebar(extId, info.status, info.last_error);
        } else if (info.status === 'loading') {
          // Extension loading - show spinner in sidebar
          updateExtensionStatusInSidebar(extId, 'loading');
        }
      }
    }
    
    if (hasChanges && window.__widgetControl) {
      window.__widgetControl.applyWidgetState();
    }
  } catch (e) {
    // Silently ignore polling errors
  }
}

function addExtensionToUI(extId, ext) {
  // Add to sidebar
  const sidebar = document.getElementById('sidebar-extensions');
  if (sidebar) {
    const existing = sidebar.querySelector(`.sidebar-ext[data-ext-id="${extId}"]`);
    if (!existing) {
      const item = createSidebarExtensionItem(ext, extId);
      sidebar.appendChild(item);
    }
  }
  
  // Add widget if it has widgets
  if (ext.widgets && ext.widgets.length > 0) {
    const grid = document.querySelector('.widget-grid');
    if (grid && !grid.querySelector(`.widget-extension.ext-${extId}`)) {
      const card = createExtensionCard({ ...ext, id: extId });
      grid.appendChild(card);
      loadExtensionAssets({ [extId]: ext });
      
      // Start widget intervals
      if (!ext.realtime) {
        const interval = ext.refresh_interval || 5000;
        if (interval > 0) {
          ext.widgets.forEach(wDef => {
            const key = `${extId}-${wDef.id}`;
            widgetTimers[key] = setInterval(() => refreshWidget(extId, wDef), interval);
          });
        }
      }
      
      // Initial widget refresh
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
    // Scroll to extension widget
    const widget = document.querySelector(`.widget-extension.ext-${extId}`);
    if (widget) {
      widget.scrollIntoView({ behavior: 'smooth', block: 'center' });
      widget.style.animation = 'pulse 1s ease';
      setTimeout(() => widget.style.animation = '', 1000);
    }
  });
  
  return item;
}

function loadExtensionAssets(data) {
  var light = [];
  var heavy = [];
  for (var extId in data) {
    var ext = data[extId];
    var jsCount = (ext.js_modules || []).length;
    var cssCount = (ext.css_modules || []).length;
    var isNode = ext.language === 'node' || ext.language === 'javascript';
    var isHeavy = isNode || jsCount > 2 || cssCount > 2;
    if (isHeavy) {
      heavy.push([extId, ext]);
    } else {
      light.push([extId, ext]);
    }
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
      try {
        refreshWidget(extId, wDef);
      } catch (e) {
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

//  WebSocket
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
  // refresh cada 3s por si los eventos no disparan
  setInterval(updateDot, 3000);

  socket.on('realtime_update', (data) => {
    if (!data.ext || !data.values) return;
    if (!window.extensionsData) return;
    const ext = window.extensionsData[data.ext];
    Object.keys(data.values).forEach(id => {
      const el = document.querySelector(`[data-widget-id="${id}"][data-ext-id="${data.ext}"]`);
      if (el) {
        updateWidgetValue(el, { value: data.values[id] });
      }
    });
  });

  socket.on('focus_window', () => {
    // Bring window to front and restore if minimized
    if (window.pywebview) {
      pywebview.api.focus_window().catch(() => {});
    }
    // Fallback: focus the window
    window.focus();
    document.body.focus();
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

function showInstallOverlay(msg) {
  var el = document.getElementById('install-overlay');
  if (!el) {
    el = document.createElement('div');
    el.id = 'install-overlay';
    el.style.cssText = 'position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.7);display:flex;flex-direction:column;align-items:center;justify-content:center;color:#e0e0e0;font-family:monospace;font-size:14px';
    el.innerHTML = '<div class="spinner" style="width:32px;height:32px;border:3px solid rgba(0,212,255,0.2);border-top-color:#00d4ff;border-radius:50%;animation:spin 0.8s linear infinite;margin-bottom:16px"></div><div id="install-overlay-msg"></div>';
    document.body.appendChild(el);
  }
  document.getElementById('install-overlay-msg').textContent = msg || 'Installing...';
  el.style.display = 'flex';
}

function hideInstallOverlay() {
  var el = document.getElementById('install-overlay');
  if (el) el.style.display = 'none';
}

function updateInstallOverlay(msg) {
  var el = document.getElementById('install-overlay-msg');
  if (el) el.textContent = msg || 'Installing...';
}

document.getElementById('btn-install').addEventListener('click', function () {
  showInstallChoice();
});

function showInstallChoice() {
  if (document.querySelector('.pkg-overlay')) return;
  var overlay = document.createElement('div');
  overlay.className = 'pkg-overlay';
  var dialog = document.createElement('div');
  dialog.className = 'pkg-dialog';
  dialog.innerHTML =
    '<div class="pkg-header">Install Extension</div>' +
    '<div class="pkg-body" style="text-align:center;padding:24px 14px">' +
      '<button class="mkt-btn mkt-btn-file" id="mkt-file-btn"> From file</button>' +
      '<div style="margin:12px 0;color:var(--text-muted);font-size:10px">or</div>' +
      '<button class="mkt-btn mkt-btn-market" id="mkt-market-btn"> Marketplace</button>' +
      '<div style="margin:12px 0;color:var(--text-muted);font-size:10px">or</div>' +
      '<button class="mkt-btn mkt-btn-provider" id="mkt-provider-btn"> External Providers</button>' +
    '</div>' +
    '<div class="pkg-footer"><button class="pkg-btn" id="mkt-close">Cancel</button></div>';
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);

  document.getElementById('mkt-close').addEventListener('click', function () { overlay.remove(); });
  overlay.addEventListener('click', function (e) { if (e.target === overlay) overlay.remove(); });

  document.getElementById('mkt-file-btn').addEventListener('click', function () {
    overlay.remove();
    triggerFileInstall();
  });

  document.getElementById('mkt-market-btn').addEventListener('click', function () {
    showMarketplaceList(overlay);
  });

  document.getElementById('mkt-provider-btn').addEventListener('click', function () {
    overlay.remove();
    showExternalProviders();
  });
}

function refreshAfterInstall(extName, extId) {
  hideInstallToast();
  showInstallOverlay('Installed! Loading...');
  // Wait until extension is actually loaded and responding before showing confirm
  var attempts = 0;
  var maxAttempts = 30;
  function checkReady() {
    attempts++;
    apiFetch('/api/extensions').then(function (data) {
      if (data && data[extId] && !data[extId].loadError) {
        // Extension is loaded, try to get a widget value to confirm it responds
        var ext = data[extId];
        var testAction = ext.widgets && ext.widgets[0] && ext.widgets[0].action;
        if (testAction) {
          apiFetch('/api/extension/' + extId + '/' + testAction).then(function (resp) {
            hideInstallOverlay();
            showInstallConfirm(extName, extId);
          }).catch(function () {
            if (attempts < maxAttempts) setTimeout(checkReady, 500);
            else { hideInstallOverlay(); showInstallConfirm(extName, extId); }
          });
        } else {
          hideInstallOverlay();
          showInstallConfirm(extName, extId);
        }
      } else if (attempts < maxAttempts) {
        setTimeout(checkReady, 500);
      } else {
        hideInstallOverlay();
        showInstallConfirm(extName, extId);
      }
    }).catch(function () {
      if (attempts < maxAttempts) setTimeout(checkReady, 500);
      else { hideInstallOverlay(); showInstallConfirm(extName, extId); }
    });
  }
  setTimeout(checkReady, 500);
}

function showInstallConfirm(extName, extId) {
  var overlay = document.createElement('div');
  overlay.className = 'pkg-overlay';
  overlay.innerHTML =
    '<div class="pkg-dialog" style="text-align:center;padding:20px">' +
    '<div style="font-size:28px;margin-bottom:8px">&#10003;</div>' +
    '<div style="font-size:14px;color:var(--text-primary);margin-bottom:16px">' + escapeHtml(extName) + ' installed</div>' +
    '<div style="display:flex;gap:8px;justify-content:center">' +
    '<button id="install-show-btn" class="pkg-btn pkg-btn-primary" style="background:var(--accent-cyan);color:#fff">Show</button>' +
    '<button id="install-close-btn" class="pkg-btn">Close</button>' +
    '</div></div>';
  document.body.appendChild(overlay);

  document.getElementById('install-show-btn').onclick = function () {
    overlay.remove();
    var ext = window.extensionsData ? window.extensionsData[extId] : null;
    if (ext) {
      var grid = document.querySelector('.widget-grid');
      if (grid && !document.querySelector('.widget-extension.ext-' + extId)) {
        var card = createExtensionCard({ ...ext, id: extId });
        grid.appendChild(card);
        if (ext.widgets) {
          ext.widgets.forEach(function (wDef) { refreshWidget(extId, wDef); });
        }
        if (ext.js_modules && ext.js_modules.length) {
          document.querySelectorAll('script[src*="/ext-static/' + extId + '/"]').forEach(function (s) { s.remove(); });
          ext.js_modules.forEach(function (mod) {
            var script = document.createElement('script');
            script.src = '/ext-static/' + extId + '/' + mod;
            document.body.appendChild(script);
          });
        }
      }
    }
    if (window.__widgetControl && window.__widgetControl.unhideWidget) {
      window.__widgetControl.unhideWidget(extId);
    }
  };
  document.getElementById('install-close-btn').onclick = function () {
    overlay.remove();
  };
  overlay.addEventListener('click', function (e) {
    if (e.target === overlay) overlay.remove();
  });
}

function triggerFileInstall() {
  var input = document.createElement('input');
  input.type = 'file';
  input.accept = '.zip';
  input.style.display = 'none';
  input.addEventListener('change', function () {
    if (!input.files || !input.files[0]) { input.remove(); return; }
    var file = input.files[0];
    input.remove();
    var formData = new FormData();
    formData.append('extension', file);

    var installId = null;
    var installName = null;

    showInstallToast('Installing extension...');

    var sock = window.__socket;
    var progressHandler = function (ev) {
      if (ev.id !== installId) return;
      if (ev.step === 'syncing') {
        showInstallToast('Syncing ' + installName + '...');
      } else if (ev.step === 'deps') {
        showInstallToast('Installing deps for ' + installName + '...');
      } else if (ev.step === 'loading') {
        showInstallToast('Loading ' + installName + '...');
      } else if (ev.step === 'done') {
        hideInstallToast();
        refreshAfterInstall(installName || installId, installId);
        if (sock) sock.off('extension_install_progress', progressHandler);
      } else if (ev.step === 'error') {
        hideInstallToast();
        showToast('Install error: ' + (ev.error || 'Unknown error'));
        if (sock) sock.off('extension_install_progress', progressHandler);
      }
    };
    if (sock) sock.on('extension_install_progress', progressHandler);

    apiFetch('/api/install_extension', {
      method: 'POST',
      body: formData
    }).then(function (data) {
      if (data && data.exists) {
        hideInstallToast();
        if (sock) sock.off('extension_install_progress', progressHandler);
        showToast(data.message || 'This extension has already been imported.');
        return;
      }
      if (data && data.error) {
        hideInstallToast();
        if (sock) sock.off('extension_install_progress', progressHandler);
        showToast('Error: ' + data.error);
        return;
      }
      if (data && data.status === 'installing') {
        installId = data.id;
        installName = data.name;
        showInstallToast('Installing deps for ' + data.name + '...');
      } else {
        hideInstallToast();
        if (sock) sock.off('extension_install_progress', progressHandler);
        var val = data.value || data;
        refreshAfterInstall(val.name || val.id, val.id);
      }
    });
  });
  document.body.appendChild(input);
  input.click();
}

function showMarketplaceList(choiceOverlay) {
  if (!choiceOverlay && document.querySelector('.pkg-overlay')) return;
  var overlay = choiceOverlay || document.createElement('div');
  if (!choiceOverlay) {
    overlay.className = 'pkg-overlay';
    document.body.appendChild(overlay);
  }
  var dialog = overlay.querySelector('.pkg-dialog');
  if (!dialog) {
    dialog = document.createElement('div');
    dialog.className = 'pkg-dialog mkt-dialog';
    overlay.appendChild(dialog);
  }
  dialog.innerHTML =
    '<div class="pkg-header">Marketplace</div>' +
    '<div class="pkg-search"><input type="text" id="mkt-search" placeholder="Search marketplace..."></div>' +
    '<div class="pkg-body" id="mkt-body">Loading...</div>' +
    '<div class="pkg-footer"><button class="pkg-btn" id="mkt-close2">Close</button></div>';

  document.getElementById('mkt-close2').addEventListener('click', function () { overlay.remove(); });
  overlay.addEventListener('click', function (e) { if (e.target === overlay) overlay.remove(); });

  var _mktExts = [];
  var _mktShowHidden = false;
  var _mktFilter = '';

  function renderMarketplace() {
    var body = document.getElementById('mkt-body');
    if (!body) return;
    body.innerHTML = '';
    var filtered = _mktShowHidden ? _mktExts : _mktExts.filter(function(e) { return !e.hidden; });
    if (_mktFilter) {
      var f = _mktFilter.toLowerCase();
      filtered = filtered.filter(function (e) {
        return (e.name || '').toLowerCase().indexOf(f) >= 0 || (e.id || '').toLowerCase().indexOf(f) >= 0 || (e.description || '').toLowerCase().indexOf(f) >= 0;
      });
    }
    if (!filtered.length) {
      body.innerHTML = '<div class="pkg-empty">No extensions available.</div>';
      return;
    }
    var grid = document.createElement('div');
    grid.className = 'mkt-grid';
    filtered.forEach(function (ext) {
      var installed = !!(window.extensionsData && window.extensionsData[ext.id]);
      var card = document.createElement('div');
      card.className = 'mkt-card' + (ext.hidden ? ' mkt-hidden' : '') + (installed ? ' mkt-installed' : '');
      var iconHtml = window.renderExtIconHtml ? window.renderExtIconHtml(ext.icon || '', ext.id) : '';
      if (iconHtml) {
        var iconWrap = document.createElement('div');
        iconWrap.className = 'ext-card-icon';
        iconWrap.style.cssText = 'width:36px;height:36px;margin:0 auto 2px;font-size:16px;';
        iconWrap.innerHTML = iconHtml;
        card.appendChild(iconWrap);
      }
      var nameEl = document.createElement('div');
      nameEl.className = 'mkt-card-name';
      nameEl.innerHTML = '<strong>' + (ext.name || ext.id) + '</strong> <span class="text-muted">v' + (ext.version || '?') + '</span>';
      var descEl = document.createElement('div');
      descEl.className = 'mkt-card-desc';
      descEl.textContent = ext.description || '';
      var btn = document.createElement('button');
      if (installed) {
        btn.className = 'pkg-btn mkt-installed-btn';
        btn.textContent = 'Installed';
        btn.addEventListener('mouseenter', function () { btn.textContent = 'Uninstall'; btn.style.color = 'var(--accent-red)'; btn.style.borderColor = 'var(--accent-red)'; });
        btn.addEventListener('mouseleave', function () { btn.textContent = 'Installed'; btn.style.color = ''; btn.style.borderColor = ''; });
        btn.addEventListener('click', function (e) {
          e.stopPropagation();
          var wc = window.__wc;
          if (wc && wc.showDeleteExtensionConfirm) {
            wc.showDeleteExtensionConfirm(ext.id, function () { renderMarketplace(); });
          }
        });
      } else {
        btn.className = 'pkg-btn pkg-btn-primary';
        btn.textContent = 'Install';
        btn.addEventListener('click', function () {
          btn.textContent = '...';
          btn.disabled = true;
          var attempts = 0;
          var maxAttempts = 3;
          var to = [3000, 15000, 30000];
          var installId = null;
          var sock = window.__socket;
          var progressHandler = null;
          function tryInstall() {
            var label = attempts === 0 ? 'Downloading ' + ext.name + '...' : 'Retrying (' + attempts + '/' + maxAttempts + ')...';
            showInstallOverlay(label);
            apiFetch('/api/marketplace/install/' + encodeURIComponent(ext.id), { method: 'POST', timeout: to[attempts] || 30000 }).then(function (res) {
              if (res && res.exists) {
                hideInstallOverlay();
                showToast(res.message || 'This extension has already been imported.');
                btn.textContent = 'Install';
                btn.disabled = false;
                return;
              }
              if (res && res.error) {
                attempts++;
                if (attempts < maxAttempts) {
                  tryInstall();
                  return;
                }
                hideInstallOverlay();
                showToast('Error: ' + res.error);
                btn.textContent = 'Install';
                btn.disabled = false;
                return;
              }
              if (res && res.status === 'installing') {
                installId = res.id;
                hideInstallOverlay();
                showInstallToast('Installing deps for ' + ext.name + '...');
                progressHandler = function (ev) {
                  if (ev.id !== installId) return;
                  if (ev.step === 'syncing') {
                    showInstallToast('Syncing ' + ext.name + '...');
                  } else if (ev.step === 'deps') {
                    showInstallToast('Installing deps for ' + ext.name + '...');
                  } else if (ev.step === 'loading') {
                    showInstallToast('Loading ' + ext.name + '...');
      } else if (ev.step === 'done') {
        hideInstallToast();
        if (sock) sock.off('extension_install_progress', progressHandler);
        apiFetch('/api/extensions').then(function (data) {
          if (data && !data.error) {
            window.extensionsData = data;
            buildSidebar(data);
          }
          renderMarketplace();
          refreshAfterInstall(ext.name, ext.id);
        });
      } else if (ev.step === 'error') {
        hideInstallToast();
        if (sock) sock.off('extension_install_progress', progressHandler);
        showToast('Install error: ' + (ev.error || 'Unknown error'));
        btn.textContent = 'Install';
        btn.disabled = false;
        renderMarketplace();
      }
                };
                if (sock) sock.on('extension_install_progress', progressHandler);
                return;
              }
              hideInstallOverlay();
              apiFetch('/api/extensions').then(function (data) {
                if (data && !data.error) {
                  window.extensionsData = data;
                  buildSidebar(data);
                }
                renderMarketplace();
                refreshAfterInstall(ext.name, ext.id);
              });
            });
          }
          tryInstall();
        });
      }
      card.appendChild(nameEl);
      card.appendChild(descEl);
      card.appendChild(btn);
      grid.appendChild(card);
    });
    body.appendChild(grid);
    if (window.feather) window.feather.replace();
    var toggleRow = document.createElement('div');
    toggleRow.style.cssText = 'padding:8px 0;border-top:1px solid var(--border-color);margin-top:4px';
    var label = document.createElement('label');
    label.style.cssText = 'font-size:10px;color:var(--text-muted);cursor:pointer;display:flex;align-items:center;gap:6px';
    var cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.checked = _mktShowHidden;
    cb.style.cssText = 'accent-color:#ff9800';
    cb.addEventListener('change', function () {
      _mktShowHidden = cb.checked;
      renderMarketplace();
    });
    label.appendChild(cb);
    label.appendChild(document.createTextNode('Show hidden extensions'));
    toggleRow.appendChild(label);
    body.appendChild(toggleRow);
  }

  function doLoadMarketplace(attempt) {
    apiFetch('/api/marketplace/list', { timeout: 10000 }).then(function (registry) {
      var body = document.getElementById('mkt-body');
      if (!registry || registry.error) {
        if (attempt < 2) {
          setTimeout(function () { doLoadMarketplace(attempt + 1); }, 2000);
          body.innerHTML = '<div class="pkg-empty">Retrying...</div>';
          return;
        }
        var cached = localStorage.getItem('mkt-cache');
        if (cached) {
          try { var cachedData = JSON.parse(cached); if (cachedData && cachedData.extensions) { _mktExts = cachedData.extensions; renderMarketplace(); return; } } catch(e) {}
        }
        body.innerHTML = '<div class="pkg-empty">Failed to load marketplace: ' + (registry ? registry.error : 'unknown') + '</div>';
        return;
      }
      localStorage.setItem('mkt-cache', JSON.stringify(registry));
      _mktExts = registry.extensions || [];
      if (!_mktExts.length) {
        body.innerHTML = '<div class="pkg-empty">No extensions available.</div>';
        return;
      }
      renderMarketplace();
    });
  }
  doLoadMarketplace(0);

  var mktSearch = document.getElementById('mkt-search');
  if (mktSearch) {
    mktSearch.addEventListener('input', function () {
      _mktFilter = this.value;
      renderMarketplace();
    });
  }
}

function showExternalProviders() {
  if (document.querySelector('.pkg-overlay')) return;
  var overlay = document.createElement('div');
  overlay.className = 'pkg-overlay';
  var dialog = document.createElement('div');
  dialog.className = 'pkg-dialog';
  dialog.style.maxWidth = '560px';
  dialog.innerHTML =
    '<div class="pkg-header">External Providers</div>' +
    '<div class="pkg-body" id="ep-body">Loading...</div>' +
    '<div class="pkg-footer"><button class="pkg-btn" id="ep-close">Close</button></div>';
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);

  document.getElementById('ep-close').addEventListener('click', function () { overlay.remove(); });
  overlay.addEventListener('click', function (e) { if (e.target === overlay) overlay.remove(); });

  function renderProviders(providers) {
    var body = document.getElementById('ep-body');
    if (!body) return;
    var html = '';
    html += '<div class="provider-warning">' +
      '<span class="provider-warning-icon">\u26A0</span>' +
      '<span>External providers are not supervised or verified by CoreFrame. ' +
      'Extensions from these sources may be unsafe. Install only from providers you trust.</span>' +
      '</div>';
    html += '<div class="provider-input-row">' +
      '<input type="text" id="ep-url-input" placeholder="https://example.com/registry.json">' +
      '<button id="ep-add-btn">Add</button>' +
      '</div>';
    if (providers && providers.length) {
      html += '<div style="display:flex;flex-direction:column;gap:6px;" id="ep-list">';
      providers.forEach(function (p, i) {
        html += '<div class="provider-card" data-idx="' + i + '">' +
          '<div class="provider-card-icon">\uD83C\uDF10</div>' +
          '<div class="provider-card-info">' +
            '<div class="provider-card-name">' + escapeHtml(p.name || p.url) + '</div>' +
            '<div class="provider-card-url">' + escapeHtml(p.url) + '</div>' +
          '</div>' +
          '<button class="ext-card-btn ext-card-btn-danger ep-remove" data-idx="' + i + '">Remove</button>' +
        '</div>';
      });
      html += '</div>';
    } else {
      html += '<div style="text-align:center;padding:16px;color:var(--text-muted);font-size:11px;">No external providers configured.</div>';
    }
    body.innerHTML = html;

    document.getElementById('ep-add-btn').addEventListener('click', function () {
      var input = document.getElementById('ep-url-input');
      var url = (input.value || '').trim();
      if (!url) return;
      if (!url.startsWith('http://') && !url.startsWith('https://')) {
        url = 'https://' + url;
      }
      apiFetch('/api/providers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: url })
      }).then(function (res) {
        if (res && res.error) { showToast('Error: ' + res.error); return; }
        if (res && res.providers) renderProviders(res.providers);
      });
    });

    body.querySelectorAll('.ep-remove').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var idx = parseInt(btn.dataset.idx, 10);
        apiFetch('/api/providers/' + idx, { method: 'DELETE' }).then(function (res) {
          if (res && res.providers) renderProviders(res.providers);
        });
      });
    });

    body.querySelectorAll('.provider-card').forEach(function (card) {
      card.addEventListener('click', function (e) {
        if (e.target.closest('.ep-remove')) return;
        var idx = parseInt(card.dataset.idx, 10);
        var provider = providers[idx];
        if (provider) {
          overlay.remove();
          showProviderMarketplace(provider);
        }
      });
    });
  }

  apiFetch('/api/providers').then(function (res) {
    renderProviders((res && res.providers) || []);
  });
}

function showProviderMarketplace(provider) {
  // Close any existing provider marketplace first
  var existing = document.querySelector('.pkg-overlay');
  if (existing) existing.remove();
  var overlay = document.createElement('div');
  overlay.className = 'pkg-overlay';
  var dialog = document.createElement('div');
  dialog.className = 'pkg-dialog mkt-dialog';
  dialog.innerHTML =
    '<div class="pkg-header">' + escapeHtml(provider.name || provider.url) + '</div>' +
    '<div class="pkg-search"><input type="text" id="pvm-search" placeholder="Search..."></div>' +
    '<div class="pkg-body" id="pvm-body">Loading...</div>' +
    '<div class="pkg-footer"><button class="pkg-btn" id="pvm-close">Close</button></div>';
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);

  document.getElementById('pvm-close').addEventListener('click', function () { overlay.remove(); });
  overlay.addEventListener('click', function (e) { if (e.target === overlay) overlay.remove(); });

  var _pvmExts = [];
  var _pvmFilter = '';

  function renderProviderMkt() {
    var body = document.getElementById('pvm-body');
    if (!body) return;
    var exts = _pvmExts;
    if (_pvmFilter) {
      var f = _pvmFilter.toLowerCase();
      exts = exts.filter(function (e) {
        return (e.name || '').toLowerCase().indexOf(f) >= 0 || (e.id || '').toLowerCase().indexOf(f) >= 0 || (e.description || '').toLowerCase().indexOf(f) >= 0;
      });
    }
    if (!exts.length) {
      body.innerHTML = '<div class="pkg-empty">' + (_pvmFilter ? 'No matches' : 'No extensions found in this provider.') + '</div>';
      return;
    }
    var grid = document.createElement('div');
    grid.className = 'mkt-grid';
    exts.forEach(function (ext) {
      var installed = !!(window.extensionsData && window.extensionsData[ext.id]);
      var card = document.createElement('div');
      card.className = 'mkt-card' + (installed ? ' mkt-installed' : '');
      var iconHtml = window.renderExtIconHtml ? window.renderExtIconHtml(ext.icon || '', ext.id) : '';
      if (iconHtml) {
        var iconWrap = document.createElement('div');
        iconWrap.className = 'ext-card-icon';
        iconWrap.style.cssText = 'width:36px;height:36px;margin:0 auto 2px;font-size:16px;';
        iconWrap.innerHTML = iconHtml;
        card.appendChild(iconWrap);
      }
      var nameEl = document.createElement('div');
      nameEl.className = 'mkt-card-name';
      nameEl.innerHTML = '<strong>' + (ext.name || ext.id) + '</strong> <span class="text-muted">v' + (ext.version || '?') + '</span>';
      var descEl = document.createElement('div');
      descEl.className = 'mkt-card-desc';
      descEl.textContent = ext.description || '';
      var btn = document.createElement('button');
      if (installed) {
        btn.className = 'pkg-btn mkt-installed-btn';
        btn.textContent = 'Installed';
        btn.addEventListener('mouseenter', function () { btn.textContent = 'Uninstall'; btn.style.color = 'var(--accent-red)'; btn.style.borderColor = 'var(--accent-red)'; });
        btn.addEventListener('mouseleave', function () { btn.textContent = 'Installed'; btn.style.color = ''; btn.style.borderColor = ''; });
        btn.addEventListener('click', function (e) {
          e.stopPropagation();
          var wc = window.__wc;
          if (wc && wc.showDeleteExtensionConfirm) {
            wc.showDeleteExtensionConfirm(ext.id, function () { renderProviderMkt(); });
          }
        });
      } else {
        btn.className = 'pkg-btn pkg-btn-primary';
        btn.textContent = 'Install';
        btn.addEventListener('click', function () {
          btn.textContent = '...';
          btn.disabled = true;
          apiFetch('/api/providers/install', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ provider_url: provider.url, ext_id: ext.id })
          }).then(function (res) {
            if (res && res.error) {
              showToast('Error: ' + res.error);
              btn.textContent = 'Install';
              btn.disabled = false;
              return;
            }
            refreshAfterInstall(ext.name || ext.id, ext.id);
            renderProviderMkt();
          });
        });
      }
      card.appendChild(nameEl);
      card.appendChild(descEl);
      card.appendChild(btn);
      grid.appendChild(card);
    });
    body.innerHTML = '';
    body.appendChild(grid);
    if (window.feather) window.feather.replace();
  }

  apiFetch('/api/providers/extensions?url=' + encodeURIComponent(provider.url)).then(function (res) {
    var body = document.getElementById('pvm-body');
    if (!res || res.error) {
      body.innerHTML = '<div class="pkg-empty">Failed to load: ' + (res ? res.error : 'unknown') + '</div>';
      return;
    }
    _pvmExts = res.extensions || [];
    renderProviderMkt();
  });

  var pvmSearch = document.getElementById('pvm-search');
  if (pvmSearch) {
    pvmSearch.addEventListener('input', function () {
      _pvmFilter = this.value;
      renderProviderMkt();
    });
  }
}

document.getElementById('btn-package').addEventListener('click', function () {
  var overlay = document.createElement('div');
  overlay.className = 'pkg-overlay';
  var dialog = document.createElement('div');
  dialog.className = 'pkg-dialog';
  dialog.innerHTML =
    '<div class="pkg-header">Package extension</div>' +
    '<div class="pkg-body" id="pkg-body">Loading...</div>' +
    '<div class="pkg-footer"><button class="pkg-btn" id="pkg-close">Close</button></div>';
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);

  document.getElementById('pkg-close').addEventListener('click', function () { overlay.remove(); });
  overlay.addEventListener('click', function (e) { if (e.target === overlay) overlay.remove(); });

  apiFetch('/api/extensions').then(function (data) {
    if (!data || data.error) { document.getElementById('pkg-body').textContent = 'Failed to load extensions.'; return; }
    var body = document.getElementById('pkg-body');
    body.innerHTML = '';
    var ids = Object.keys(data).sort();
    if (!ids.length) { body.innerHTML = '<div class="pkg-empty">No extensions installed.</div>'; return; }
    ids.forEach(function (id) {
      var ext = data[id];
      var row = document.createElement('div');
      row.className = 'pkg-row';
      var info = document.createElement('div');
      info.className = 'pkg-info';
      var authorLine = ext.author ? '<br><span class="text-muted" style="font-size:11px">author: ' + escapeHtml(ext.author) + '</span>' : '';
      info.innerHTML = '<strong>' + escapeHtml(ext.name || id) + '</strong> <span class="text-muted">' + escapeHtml(id) + '</span>' + authorLine;
      var btn = document.createElement('button');
      btn.className = 'pkg-btn pkg-btn-primary';
      btn.textContent = 'Package';

      var authorRow = document.createElement('div');
      authorRow.className = 'pkg-author-row';
      authorRow.style.display = 'none';
      var authorInput = document.createElement('input');
      authorInput.type = 'text';
      authorInput.placeholder = 'Author name...';
      authorInput.className = 'pkg-author-input';
      authorInput.value = ext.author || '';
      var authorConfirm = document.createElement('button');
      authorConfirm.className = 'pkg-btn pkg-btn-primary';
      authorConfirm.textContent = 'OK';
      authorConfirm.style.marginLeft = '6px';
      authorRow.appendChild(authorInput);
      authorRow.appendChild(authorConfirm);

      function doPackage(author) {
        btn.textContent = '...';
        btn.disabled = true;
        authorRow.style.display = 'none';
        var a = document.createElement('a');
        a.href = '/api/package_extension/' + encodeURIComponent(id) + '?author=' + encodeURIComponent(author);
        a.download = id + '.zip';
        a.style.display = 'none';
        document.body.appendChild(a);
        a.click();
        setTimeout(function () { a.remove(); btn.textContent = 'Package'; btn.disabled = false; }, 3000);
      }

      btn.addEventListener('click', function () {
        if (ext.author) {
          doPackage(ext.author);
        } else {
          authorRow.style.display = 'flex';
          authorInput.focus();
        }
      });

      authorConfirm.addEventListener('click', function () {
        var val = authorInput.value.trim();
        if (!val) { authorInput.focus(); return; }
        doPackage(val);
      });

      authorInput.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          var val = authorInput.value.trim();
          if (!val) return;
          doPackage(val);
        }
      });

      row.appendChild(info);
      row.appendChild(btn);
      row.appendChild(authorRow);
      body.appendChild(row);
    });
  });
});

document.getElementById('btn-reload').addEventListener('click', async () => {
  const btn = document.getElementById('btn-reload');
  btn.textContent = '↻';
  btn.style.animation = 'spin 0.6s linear infinite';
  try {
    await apiFetch('/api/restart', { method: 'POST' });
  } catch (e) {}
  // Instant reload - server responds immediately, just wait a tiny bit and refresh
  setTimeout(() => location.reload(), 500);
});

//  Window mode state & F11 

let currentWindowMode = new URLSearchParams(window.location.search).get('mode') || 'windowed';

var _installToastEl = null;
function showInstallToast(msg) {
  if (_installToastEl) { _installToastEl.textContent = msg; return; }
      _installToastEl = document.createElement('div');
      _installToastEl.style.cssText = 'position:fixed;bottom:20px;right:20px;background:#1a1a2e;color:#e0e0e0;padding:8px 14px;border-radius:6px;border:1px solid rgba(0,212,255,0.3);font-size:12px;z-index:9999;max-width:360px';
      _installToastEl.textContent = msg;
      document.body.appendChild(_installToastEl);
      // Request widget control to suppress autoAdd during refresh
      if (window.__widgetControl) {
        window.__widgetControl._suppressAutoAdd = true;
      }
}
function hideInstallToast() {
  if (_installToastEl) { _installToastEl.remove(); _installToastEl = null; }
}

function showToast(msg) {
  var t = document.createElement('div');
  t.style.cssText = 'position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#1a1a2e;color:#e0e0e0;padding:8px 16px;border-radius:6px;border:1px solid rgba(0,212,255,0.3);font-size:12px;z-index:9999;transition:opacity 0.3s';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(function(){ t.style.opacity = '0'; setTimeout(function(){ t.remove(); }, 400); }, 2500);
}

function applyStartupMode() {
  var done = function () {
    try { var ae = document.activeElement; if (ae && typeof ae.blur === 'function') ae.blur(); } catch (e) {}
    document.body.classList.remove('booting');
  };
  // Python natively enforces the saved mode right after reveal — the JS side
  // must NOT call the API again here (duplicate WinForms work caused freezes).
  // Just unlock interaction shortly after first paint.
  setTimeout(done, 250);
}

function applyWindowModeFallback(mode) {
  if (mode === 'fullscreen') {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(function(){});
    } else {
      document.documentElement.requestFullscreen().catch(function(){});
    }
  } else {
    if (document.fullscreenElement) {
      document.exitFullscreen().catch(function(){});
    }
  }
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'F11') {
    e.preventDefault();
    if (window.pywebview) {
      const next = currentWindowMode === 'fullscreen' ? 'windowed' : 'fullscreen';
      pywebview.api.set_window_mode(next).then(function(applied) {
        currentWindowMode = next;
        updateUrlMode(next);
        if (!applied && next !== 'fullscreen') {
          showToast('Reinicia CoreFrame para aplicar');
        }
      }).catch(function(err) {
        console.warn('set_window_mode pywebview failed:', err);
        applyWindowModeFallback(next);
        currentWindowMode = next;
        updateUrlMode(next);
      });
    } else {
      const next = currentWindowMode === 'fullscreen' ? 'windowed' : 'fullscreen';
      applyWindowModeFallback(next);
      currentWindowMode = next;
      updateUrlMode(next);
    }
  }
});

function updateUrlMode(mode) {
  const url = new URL(window.location);
  url.searchParams.set('mode', mode);
  window.history.replaceState({}, '', url);
}

//  Minimize window
document.getElementById('btn-minimize').addEventListener('click', function () {
  if (window.pywebview) {
    pywebview.api.minimize_window().catch(function(err) {
      console.warn('minimize_window failed:', err);
    });
  }
});

//  Settings dropdown (accessible via right-click on gear)
const settingsBtn = document.getElementById('btn-settings');
