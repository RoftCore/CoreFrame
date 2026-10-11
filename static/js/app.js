let extensionsData = {};
let widgetTimers = {};
let extensionLoadState = {};

// ── Extension loading ─────────────────────────────────────────────

async function loadExtensionsAsync(tries) {
  // Called once from core.js. A single attempt was the entire recovery story:
  // if the host was still restarting and that call failed, the dashboard stayed
  // empty for the rest of the session, so a manual page reload was the only way
  // back. A cold start only worked because the timing happened to line up.
  tries = tries || 8;
  for (let attempt = 1; attempt <= tries; attempt++) {
    try {
      const data = await apiFetch('/api/extensions');
      if (data && !data.error && Object.keys(data).length) {
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
        // Disabled extensions are installed and registered, but not running.
        // They are listed with widgets emptied so the host renders no card.
        for (const [extId, ext] of Object.entries(data)) {
          if (ext.disabled) addExtensionToUI(extId, ext);
        }
        return true;
      }
    } catch (e) {
      if (attempt === tries) console.error('Extension load attempt failed:', e);
    }
    if (attempt < tries) await new Promise(r => setTimeout(r, 700 * attempt));
  }
  console.error('Initial extension load failed after ' + tries + ' attempts');
  return false;
}

async function pollExtensionUpdates() {
  try {
    // Self-heal: an empty dashboard means the extension list never landed.
    // This poll runs every second, so it is the natural place to notice
    // and retry, instead of leaving a manual page reload as the only way
    // out.
    if (!Object.keys(extensionsData || {}).length && !pollExtensionUpdates._healing) {
      pollExtensionUpdates._healing = true;
      loadExtensionsAsync(3).finally(() => { pollExtensionUpdates._healing = false; });
    }
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
    if (hasChanges && window.__widgetControl && !window.__coreframeDragging) {
      window.__widgetControl.applyWidgetState();
    }

    // Leftover placeholders: the branch above only fires on a loaded transition, which one that landed between renders never produces.
    const placeholders = document.querySelectorAll('.widget-extension.cf-placeholder');
    if (placeholders.length) {
      let stale = false;
      for (const el of placeholders) {
        const info = health[el.dataset.extId];
        if (info && info.loaded) { stale = true; break; }
      }
      if (stale) {
        const fresh = await apiFetch('/api/extensions');
        if (fresh && !fresh.error) {
          extensionsData = fresh;
          window.extensionsData = fresh;
          for (const el of placeholders) {
            const extId = el.dataset.extId;
            const ext = fresh[extId];
            if (ext && !ext.pending && !ext.disabled && el.dataset.placeholder === '1') {
              addExtensionToUI(extId, ext);
            }
          }
        }
      }
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
      if (typeof feather !== 'undefined') feather.replace();
    }
  }
  // Disabled: listed, but no card, no assets and no polling. Nothing of it is
  // allowed to touch the grid.
  if (ext.disabled) {
    if (window.__wc) { window.__wc.exitEditMode && window.__wc.editMode && window.__wc.exitEditMode(); }
    return;
  }
  if (ext.widgets && ext.widgets.length > 0) {
    const grid = document.querySelector('.widget-grid');
    if (grid) {
      const existing = grid.querySelector(`.widget-extension.ext-${extId}`);
      // A pending extension holds its slot as a skeleton: swapped in place, or the grid grows by one per load.
      if (!existing || existing.dataset.placeholder === '1') {
        // Hold the skeleton for a minimum readable time, once only, or a fast extension makes it flicker.
        if (existing && existing.dataset.placeholder === '1' && !existing.dataset.cfDeferred) {
          const born = parseInt(existing.dataset.cfPhAt || '0', 10) || Date.now();
          const wait = CF_PLACEHOLDER_MIN_MS - (Date.now() - born);
          if (wait > 0) {
            existing.dataset.cfDeferred = '1';
            setTimeout(() => addExtensionToUI(extId, ext), wait);
            return;
          }
        }
        const card = createExtensionCard({ ...ext, id: extId });
        if (existing) {
          grid.replaceChild(card, existing);
        } else {
          grid.appendChild(card);
        }
        cfApplyAppearAnimation(card, ext);
        loadExtensionAssets({ [extId]: ext });
        // The swap above destroyed whatever an extension had painted into the
        // placeholder card. Extensions that registered a repaint handler get
        // called back (cfNotifyCardRerender below); the ones that paint the card
        // without a hook would be lost, so their scripts are re-run once.
        cfRepaintIfNoHook(extId, ext);
        const interval = ext.refresh_interval || 5000;
        // The core keeps the refresh clock for any extension whose widget values
        // it still owns. A repaint handler only redraws on demand; it does not
        // poll. network_monitor relies on this clock for its VPN/ports badge and
        // declares realtime:true with JS, so it must not be skipped here.
        if (interval > 0 && cfCoreOwnsWidgets(ext, extId)) {
          ext.widgets.forEach(wDef => {
            const key = `${extId}-${wDef.id}`;
            widgetTimers[key] = setInterval(() => refreshWidget(extId, wDef), interval);
          });
        }
        // Prime widgets the core owns, including js-driven ones that have no
        // refresh_interval of their own; see cfNeedsWidgetPriming.
        if (cfNeedsWidgetPriming(ext, extId)) {
          ext.widgets.forEach(wDef => refreshWidget(extId, wDef));
        }
        // The card was just created or replaced in place. Any extension that
        // paints the card itself gets told to repaint into the new DOM.
        cfNotifyCardRerender(extId);
      }
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
  const iconHtml = ext.icon
    ? (ext.icon.startsWith('/') ? '<img src="' + ext.icon + '" alt="" style="width:16px;height:16px">' : '<i data-feather="' + ext.icon + '" width="16" height="16"></i>')
    : '<i data-feather="cpu" width="16" height="16"></i>';
  item.innerHTML = `
    <span class="ext-icon">${iconHtml}</span>
    <span class="ext-name">${escapeHtml(ext.name || extId)}</span>
    <span class="ext-status ${isError ? 'error' : isLoading ? 'loading' : 'loaded'}" 
          title="${isError ? escapeHtml(extensionLoadState[extId].loadError || 'Error') : isLoading ? 'Loading...' : 'Loaded'}">
      ${isError ? '✗' : isLoading ? '⟳' : '✓'}
    </span>
  `;
  item.addEventListener('click', () => {
    // A disabled extension has no card, so there is nothing to scroll to. Its
    // Enable button lives in Settings -> Extensions.
    if (ext.disabled) return;
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
  // Cache-buster: one stamp per page load so extension JS/CSS can never
  // go stale in the webview disk cache (a stale bundle looks exactly like
  // "the fix didn't work"). Localhost: zero real cost.
  var assetV = (typeof window.__cfAssetV !== 'undefined' && window.__cfAssetV) ||
    (window.__cfAssetV = Date.now());
  function loadExtAssets(extId, ext) {
    for (var i = 0; i < (ext.js_modules || []).length; i++) {
      (function (mod) {
        var src = '/ext-static/' + extId + '/' + mod + '?v=' + assetV;
        if (document.querySelector('script[src="' + src + '"]')) return;
        var script = document.createElement('script');
        // async=false restores declaration order: dynamic classic scripts default to async=true.
        script.async = false;
        script.src = src;
        script.onerror = function () { console.warn('[EXT] Failed to load ' + mod); };
        document.body.appendChild(script);
      })(ext.js_modules[i]);
    }
    for (var j = 0; j < (ext.css_modules || []).length; j++) {
      (function (cssMod) {
        var href = '/ext-static/' + extId + '/' + cssMod + '?v=' + assetV;
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
    if (ext.disabled) continue;      // no card for a disabled extension
    if (!ext.widgets || ext.widgets.length === 0) continue;
    try {
      // Pending extensions hold their real grid slot, so the layout is final from the first paint.
      const card = ext.pending
        ? createPlaceholderCard({ ...ext, id: extId })
        : createExtensionCard({ ...ext, id: extId });
      grid.appendChild(card);
      if (!ext.pending) cfApplyAppearAnimation(card, ext);
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

// ── Repaint registry ──────────────────────────────────────────────
// The placeholder→real swap (addExtensionToUI) replaces the card DOM an
// extension may have already painted into, and loadExtensionAssets dedupes
// the script tag so it never re-runs. An extension that paints the card
// registers a repaint callback here so the core can tell it "card replaced,
// repaint". Without this the extension's own paint is destroyed by the swap
// and never restored, and the card keeps whatever the core wrote.
const cfRerenderHandlers = {};
function cfHasRerenderHandler(extId) { return !!cfRerenderHandlers[extId]; }
function cfNotifyCardRerender(extId) {
  const fn = cfRerenderHandlers[extId];
  if (!fn) return;
  try { fn(); } catch (e) { console.error('[EXT] repaint failed for ' + extId + ':', e); }
}
window.cfOnCardRerender = function (extId, fn) {
  if (typeof fn !== 'function') return;
  cfRerenderHandlers[extId] = fn;
  // The extension now paints its own body, so the core must stop polling it.
  // At first card build no handler existed yet, so a core clock may have been
  // started for it; clear it here so the two do not fight over the same DOM.
  const meta = (window.extensionsData || {})[extId];
  for (const w of ((meta && meta.widgets) || [])) {
    const k = `${extId}-${w.id}`;
    if (widgetTimers[k]) { clearInterval(widgetTimers[k]); delete widgetTimers[k]; }
  }
};

// Re-run an extension's scripts when its card was rebuilt and it has no repaint
// handler. Extensions like fortune_cookie paint their card body (buttons, text)
// on boot with no cfOnCardRerender hook, so the placeholder->real swap would
// leave them blank. Re-injecting the script with a nonce defeats the load
// dedupe, so the boot block runs again and repaints the new DOM.
//
// The check is DEFERRED on purpose: this runs right after loadExtensionAssets,
// before any extension script has booted, so no handler exists yet. Deciding
// immediately would double-execute every script (two caches, two poll timers
// fighting each other). After the boot window the handler list is authoritative.
var CF_REPAINT_DELAY_MS = 2500;
function cfRepaintIfNoHook(extId, ext) {
  const js = (ext && ext.js_modules) || [];
  if (!js.length) return;
  setTimeout(function () {
    if (cfHasRerenderHandler(extId)) return;   // it repaints on demand; leave it alone
    const nonce = 'repaint=' + Date.now();
    js.forEach(function (mod) {
      const script = document.createElement('script');
      script.async = false;
      script.src = '/ext-static/' + extId + '/' + mod + '?' + nonce;
      script.onerror = function () { console.warn('[EXT] repaint failed for ' + extId + '/' + mod); };
      document.body.appendChild(script);
    });
  }, CF_REPAINT_DELAY_MS);
}

// Does the core still own this extension's widget values?
// The core owns them unless the extension's JS paints the card body itself.
// A registered repaint handler is exactly that signal: it means the extension
// draws the values into the DOM. network_monitor has JS but no handler — it
// relies on the core clock to feed its VPN/ports badge, so it stays core-owned
// even though it declares realtime:true.
function cfCoreOwnsWidgets(ext, extId) {
  if (!ext.js_modules || !ext.js_modules.length) return true;   // no JS: core owns
  return !cfHasRerenderHandler(extId);                          // JS paints => extension owns
}

// Does the core have to prime this extension's widgets?
// Extensions with js_modules own their content. Two exceptions, both safety
// nets so a card is never left blank:
//   - the extension registered a repaint handler: it paints the card itself,
//     so the core stays out of its DOM entirely (no raw text / "[2]" markers);
//   - the extension declares no refresh_interval and is not realtime: with
//     interval 0 there is no polling, so nobody would fill the widget.
function cfNeedsWidgetPriming(ext, extId) {
  if (cfCoreOwnsWidgets(ext, extId)) {
    // Core-owned: prime it. Unless it declares no interval and is not realtime,
    // in which case there is no clock and one priming call fills it for good.
    const interval = ext.refresh_interval || 0;
    return !(ext.realtime === true || interval > 0);
  }
  // Extension paints its own body; the core stays out of it.
  return false;
}

function refreshAllWidgets(data) {
  for (const [extId, ext] of Object.entries(data)) {
    if (ext.disabled) continue;
    if (!cfNeedsWidgetPriming(ext, extId)) continue;
    for (const wDef of (ext.widgets || [])) {
      try { refreshWidget(extId, wDef); } catch (e) {
        console.error('[EXT] Error refreshing ' + extId + ':', e);
      }
    }
  }
}

// Core immunity: hidden widgets cost zero backend calls and zero DOM work.
// A slow/hanging widget that nobody sees can never slow the UI.
const widgetInflight = {};
// How many times a widget has been retried after coming back empty.
const retryCount = {};

function isWidgetActive(extId, widgetId) {
  try {
    if (typeof window.__wc !== 'undefined' && window.__wc && typeof window.__wc.currentScene === 'function') {
      const sc = window.__wc.currentScene();
      // No scene state yet (boot): allow, preserves current behavior.
      if (!sc || !sc.widgets) return true;
      const pos = sc.widgets[extId];
      // Unknown to the scene: allow (autoAdd handles placement).
      if (!pos) return true;
      if (pos.hidden) {
        // State says hidden: still allow if actually on screen (state race).
        const el = document.querySelector(`[data-widget-id="${widgetId}"][data-ext-id="${extId}"]`);
        if (!el) return false;
        const hidden = typeof cfHidden === 'function' ? cfHidden(el) : el.style.display === 'none';
        if (hidden) return false;
        return true;
      }
      return true;
    }
  } catch (e) {}
  return true;
}

async function refreshWidget(extId, wDef) {
  const key = `${extId}-${wDef.id}`;
  // Host immunity: no backend calls and no DOM writes mid-drag. The
  // interval fires again after drop and catches up by itself.
  if (window.__coreframeDragging) return;
  // Anti pile-up: a previous call still running (e.g. 3s backend on a 3s
  // interval) skips instead of stacking overlapping requests.
  if (widgetInflight[key]) return;
  if (!isWidgetActive(extId, wDef.id)) return;
  const el = document.querySelector(`[data-widget-id="${wDef.id}"][data-ext-id="${extId}"]`);
  if (!el) return;
  if (wDef.action) {
    widgetInflight[key] = true;
    try {
      const response = await apiFetch(`/api/extension/${extId}/${wDef.action}`);
      // A js-driven extension paints its own body. Its script mounts
      // asynchronously, so writing the payload immediately left the card
      // showing the serialized response until the extension took over. Give
      // that script a moment to claim the body, and write nothing if it did.
      // Core-owned widgets have no script to wait for, and delaying them only
      // left system_monitor and process_manager sitting on --. Ownership is
      // decided by a repaint handler, not by "has JS": network_monitor has JS
      // but is still core-fed, so it must not wait or bail.
      const ownsBody = !cfCoreOwnsWidgets(window.extensionsData[extId] || {}, extId);
      if (ownsBody) {
        await new Promise(r => setTimeout(r, 900));
        if (!el.querySelector(cfValueSelector(el))) return;
      }
      updateWidgetValue(el, response);
    } catch (e) {
      try { updateWidgetValue(el, { error: 'Connection error' }); } catch (e2) {}
    } finally {
      delete widgetInflight[key];
      // A widget that never received a value used to stay on "--" for the rest
      // of the session: the host asks once at start, and an extension that owns
      // its own DOM polls by itself from then on. get_processes sits right at
      // the 0.8s budget, so on a loaded machine the first attempt misses and
      // nothing ever asked again. The empty-node test is per type: a badge sits
      // on "Loading..." and a list on "", so "--" is only the text/chart marker.
      if (el && el.isConnected && !widgetInflight[key]) {
        const valEl = el.querySelector(cfValueSelector(el));
        const cur = (valEl && (valEl.textContent || '').trim()) || '';
        if (valEl && (cur === '--' || cur === 'Loading...' || cur === '')) {
          const tries = (retryCount[key] = (retryCount[key] || 0) + 1);
          if (tries <= 4) {
            setTimeout(() => { retryCount[key] = 0; refreshWidget(extId, wDef); }, 700 * tries);
          }
        }
      }
    }
  }
}

function startWidgetIntervals(data) {
  for (const timer in widgetTimers) clearInterval(widgetTimers[timer]);
  for (const [extId, ext] of Object.entries(data)) {
    if (ext.disabled) continue;   // no polling for a disabled extension
    // Keep the refresh clock wherever the core still owns the widget values.
    // realtime alone is not a reason to skip: network_monitor is realtime:true
    // with JS and still depends on this clock (see cfCoreOwnsWidgets).
    if (!cfCoreOwnsWidgets(ext, extId)) continue;
    const interval = ext.refresh_interval || 5000;
    if (interval <= 0) continue;
    for (const wDef of (ext.widgets || [])) {
      const key = `${extId}-${wDef.id}`;
      widgetTimers[key] = setInterval(() => refreshWidget(extId, wDef), interval);
    }
  }
}
