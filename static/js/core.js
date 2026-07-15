let extensionsData = {};
let widgetTimers = {};

document.addEventListener('DOMContentLoaded', async () => {
  clockTick();
  setInterval(clockTick, 1000);

  document.getElementById('btn-reload').style.display = '';
  if (typeof _COREFRAME_DEBUG !== 'undefined' && _COREFRAME_DEBUG) {
    document.getElementById('btn-package').style.display = '';
    document.body.classList.add('mode-debug');
  }

  initResultPanel();
  initWebSocket();

  const loadingEl = document.getElementById('main-content');
  let attempts = 0;
  const maxAttempts = 30;

  const tryLoad = async () => {
    const data = await apiFetch('/api/extensions');
    if (!data.error) {
      extensionsData = data;
      window.extensionsData = data;
      buildSidebar(data);
      renderWidgets(data);
      loadExtensionAssets(data);
      return;
    }
    attempts++;
    if (attempts < maxAttempts) {
      loadingEl.innerHTML = `<div class="loading"><div class="spinner"></div>Connecting to server (${attempts}/${maxAttempts})...</div>`;
      setTimeout(tryLoad, 1000);
    } else {
      loadingEl.innerHTML = `<div class="loading"><div class="spinner"></div>Failed to connect after ${maxAttempts}s. <button onclick="location.reload()" style="background:#00d4ff;border:none;padding:8px 16px;border-radius:4px;cursor:pointer;margin-top:8px">Retry</button></div>`;
    }
  };

  tryLoad();
});

function loadExtensionAssets(data) {
  for (const [extId, ext] of Object.entries(data)) {
    var loaded = 0, total = 0;
    for (const mod of (ext.js_modules || [])) {
      total++;
      const script = document.createElement('script');
      script.src = `/ext-static/${extId}/${mod}`;
      script.onload = function () { loaded++; if (loaded === total) console.log(`[EXT] All assets loaded for ${extId}`); };
      script.onerror = function () { console.warn(`[EXT] Failed to load ${mod}: ${script.src}`); };
      document.body.appendChild(script);
    }
    for (const mod of (ext.css_modules || [])) {
      const link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = `/ext-static/${extId}/${mod}`;
      link.onerror = function () { console.warn(`[EXT] Failed to load CSS for ${extId}: ${link.href}`); };
      document.head.appendChild(link);
    }
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
    const card = createExtensionCard({ ...ext, id: extId });
    grid.appendChild(card);
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
      refreshWidget(extId, wDef);
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
      updateWidgetValue(el, { error: 'Connection error' });
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
  var overlay = document.createElement('div');
  overlay.className = 'pkg-overlay';
  var dialog = document.createElement('div');
  dialog.className = 'pkg-dialog';
  dialog.innerHTML =
    '<div class="pkg-header">Install Extension</div>' +
    '<div class="pkg-body" style="text-align:center;padding:24px 14px">' +
      '<button class="mkt-btn mkt-btn-file" id="mkt-file-btn">📁 From file</button>' +
      '<div style="margin:12px 0;color:var(--text-muted);font-size:10px">or</div>' +
      '<button class="mkt-btn mkt-btn-market" id="mkt-market-btn">📦 Marketplace</button>' +
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
}

function refreshAfterInstall(extName, extId) {
  showInstallOverlay('Installed! Refreshing...');
  apiFetch('/api/extensions').then(function (data) {
    hideInstallOverlay();
    if (data && !data.error) {
      extensionsData = data;
      window.extensionsData = data;
      buildSidebar(data);
      var ext = data[extId];
      if (ext && ext.widgets && ext.widgets.length) {
        var grid = document.querySelector('.widget-grid');
        if (grid) {
          var card = createExtensionCard({ ...ext, id: extId });
          grid.appendChild(card);
        }
      }
      if (ext) loadExtensionAssets({ [extId]: ext });
      if (ext && ext.widgets) {
        if (!ext.js_modules || !ext.js_modules.length) {
          ext.widgets.forEach(function (wDef) { refreshWidget(extId, wDef); });
        }
        if (!ext.realtime) {
          var interval = ext.refresh_interval || 5000;
          if (interval > 0) {
            ext.widgets.forEach(function (wDef) {
              var key = extId + '-' + wDef.id;
              widgetTimers[key] = setInterval(function () { refreshWidget(extId, wDef); }, interval);
            });
          }
        }
      }
      if (window.__widgetControl) window.__widgetControl.applyWidgetState();
    }
    showInstallConfirm(extName, extId);
  }).catch(function () {
    hideInstallOverlay();
    showInstallConfirm(extName, extId);
  });
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
    if (!input.files || !input.files[0]) return;
    var file = input.files[0];
    var formData = new FormData();
    formData.append('extension', file);

    var installId = null;
    var installName = null;
    var toastEl = null;

    function showInstallToast(msg) {
      if (toastEl) { toastEl.textContent = msg; return; }
      toastEl = document.createElement('div');
      toastEl.style.cssText = 'position:fixed;bottom:20px;right:20px;background:#1a1a2e;color:#e0e0e0;padding:8px 14px;border-radius:6px;border:1px solid rgba(0,212,255,0.3);font-size:12px;z-index:9999;max-width:360px';
      toastEl.textContent = msg;
      document.body.appendChild(toastEl);
    }
    function hideInstallToast() {
      if (toastEl) { toastEl.remove(); toastEl = null; }
    }

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
  setTimeout(function () { input.remove(); }, 2000);
}

function showMarketplaceList(choiceOverlay) {
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
    '<div class="pkg-body" id="mkt-body">Loading...</div>' +
    '<div class="pkg-footer"><button class="pkg-btn" id="mkt-close2">Close</button></div>';

  document.getElementById('mkt-close2').addEventListener('click', function () { overlay.remove(); });
  overlay.addEventListener('click', function (e) { if (e.target === overlay) overlay.remove(); });

  var _mktExts = [];
  var _mktShowHidden = false;

  function renderMarketplace() {
    var body = document.getElementById('mkt-body');
    if (!body) return;
    body.innerHTML = '';
    var filtered = _mktShowHidden ? _mktExts : _mktExts.filter(function(e) { return !e.hidden; });
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
  let attempts = 0;
  const poll = () => {
    fetch('/api/token').then(r => { if (r.ok) location.reload(); else if (++attempts < 30) setTimeout(poll, 1000); else location.reload(); }).catch(() => { if (++attempts < 30) setTimeout(poll, 1000); else location.reload(); });
  };
  setTimeout(poll, 1500);
});

//  Window mode state & F11 

let currentWindowMode = new URLSearchParams(window.location.search).get('mode') || 'windowed';

function showToast(msg) {
  var t = document.createElement('div');
  t.style.cssText = 'position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:#1a1a2e;color:#e0e0e0;padding:8px 16px;border-radius:6px;border:1px solid rgba(0,212,255,0.3);font-size:12px;z-index:9999;transition:opacity 0.3s';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(function(){ t.style.opacity = '0'; setTimeout(function(){ t.remove(); }, 400); }, 2500);
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
        if (!applied && next !== 'fullscreen') {
          showToast('Reinicia CoreFrame para aplicar');
        }
      }).catch(function(err) {
        console.warn('set_window_mode pywebview failed:', err);
        applyWindowModeFallback(next);
        currentWindowMode = next;
      });
    } else {
      const next = currentWindowMode === 'fullscreen' ? 'windowed' : 'fullscreen';
      applyWindowModeFallback(next);
      currentWindowMode = next;
    }
  }
});

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
