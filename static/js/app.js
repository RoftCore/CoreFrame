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

// Did an extension already paint into this card?
// The skeleton only has .cf-placeholder-bar stripes. Anything else in the body
// means a script painted here, and replacing the card would throw that away.
// Re-injecting the script to repaint is not an option: classic scripts share
// the global scope, so a second run re-declares their top-level let/const and
// dies on a SyntaxError.
// Did an extension already paint into this placeholder card?
// A skeleton is built with .cf-placeholder-bar stripes inside .widget-body, so
// either extra content in the body, or a body the extension replaced wholesale,
// means a script painted there. Some extensions (fortune_cookie) assign
// widget.innerHTML to the WHOLE card, which removes .widget-body entirely;
// those were read as "not painted" and had their DOM thrown away by the swap.
// A real card is always rebuilt; a painted body is carried over separately.
function cfCardIsPainted(card) {
  if (!card || card.dataset.placeholder !== '1') return false;
  const body = card.querySelector('.widget-body');
  // The skeleton always ships a .widget-body. Its absence means an extension
  // assigned innerHTML to the whole card and removed it (fortune_cookie).
  if (!body) return true;
  // Body present: painted only if something beyond the placeholder bars is in.
  return !!body.querySelector('*:not(.cf-placeholder-bar)');
}

// Did the extension claim this (real) card's body?
// The host builds .widget-body as a flat list of .widget-sub scaffolds. If the
// extension painted into the card, that scaffold is gone or wrapped, so the
// body's direct children are no longer the bare sub-widgets. Used to keep the
// core from writing a payload over a card the extension owns, whether or not
// its repaint hook has arrived yet (a heavy extension's hook is late).
function cfCardBodyClaimed(card) {
  if (!card) return false;
  const body = card.querySelector('.widget-body');
  if (!body) return card.children.length > 1;      // extension replaced the card
  for (const child of body.children) {
    if (!child.classList.contains('widget-sub')) return true;  // non-scaffold child
  }
  return false;
}

// Clear a card's loading shimmer as soon as its extension script paints into
// it. Extensions reach the card in two ways: through cfOnCardRerender (handled
// there), or by mutating the DOM directly — fortune_cookie assigns
// widget.innerHTML, most others append their own nodes. Neither goes through
// updateWidgetValue, so watch the body: the first real mutation is the paint.
// Only reacts while the card is still flagged cf-loading, so it stops once the
// card is showing content.
function cfWatchForFirstPaint(card, extId) {
  if (!card || typeof MutationObserver === 'undefined') return;
  if (!card.classList.contains('cf-loading')) return;
  const body = card.querySelector('.widget-body');
  if (!body) return;
  const mo = new MutationObserver(function () {
    if (!card.isConnected || !card.classList.contains('cf-loading')) { mo.disconnect(); return; }
    // A mutation inside the body means the extension is painting.
    cfClearLoadingState(card);
    mo.disconnect();
  });
  mo.observe(body, { childList: true, subtree: true });
  // Safety net: whatever happens, the card must never stay hidden forever. If
  // nothing painted within 8s (or the observer saw nothing), reveal it so a
  // partly-working extension is still readable.
  setTimeout(function () {
    mo.disconnect();
    if (card.isConnected) cfClearLoadingState(card);
  }, 8000);
}

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
          // The placeholder->real swap happens once per load cycle, by design
          // (the host holds loading until the frontend asks so it can reserve
          // the grid). An extension that already painted the card would lose
          // that DOM, and its script cannot be re-run to repaint (classic
          // scripts share global scope; a second run re-declares top-level
          // let/const and dies on a SyntaxError).
          //
          // Two shapes of ownership:
          //  - painted the .widget-body: carry those nodes into the new card.
          //  - replaced the whole card (widget.innerHTML, so there is no
          //    .widget-body left): there is nothing to carry, so keep the card
          //    as it is and just clear the skeleton flag. Replacing it here is
          //    what made fortune_cookie drop its buttons and fortune.
          if (cfCardIsPainted(existing)) {
            const oldBody = existing.querySelector('.widget-body');
            if (!oldBody) {
              delete existing.dataset.placeholder;
              cfMarkExtensionLive(extId);
              cfClearLoadingState(existing);
              return;
            }
            const newBody = card.querySelector('.widget-body');
            if (newBody) newBody.replaceChildren(...oldBody.childNodes);
          }
          grid.replaceChild(card, existing);
          cfMarkExtensionLive(extId);
        } else {
          grid.appendChild(card);
        }
        cfApplyAppearAnimation(card, ext);
        cfWatchForFirstPaint(card, extId);
        loadExtensionAssets({ [extId]: ext });
        const interval = cfRefreshInterval(ext);
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
        // refresh_interval of their own; see cfNeedsWidgetPriming. A js
        // extension is deferred so its script can claim the fresh card first,
        // otherwise the core writes the raw payload and the card flashes "[6]"
        // style text until the extension paints over it.
        const _isJsExt = (ext.js_modules || []).length > 0;
        if (cfNeedsWidgetPriming(ext, extId)) {
          if (_isJsExt) {
            setTimeout(function () {
              if (cfNeedsWidgetPriming(ext, extId)) {
                ext.widgets.forEach(wDef => refreshWidget(extId, wDef));
              }
            }, CF_PRIME_DEFER_MS);
          } else {
            ext.widgets.forEach(wDef => refreshWidget(extId, wDef));
          }
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
  cfMarkExtensionLive(extId);
  // The extension is about to paint, so the card is no longer "loading".
  const card = document.querySelector(`.widget-extension.ext-${extId}`);
  if (card) cfClearLoadingState(card);
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

// The declared refresh interval in ms. A declared 0 means "do not poll me", so
// it must not fall through to the default the way `refresh_interval || 5000`
// did: that handed fortune_cookie (interval:0) a 5s clock, so the core re-primed
// it every 5s, the card reloaded itself and the fortune changed phrase on its
// own. Only a missing value takes the 5000 default.
function cfRefreshInterval(ext) {
  const ri = ext && ext.refresh_interval;
  if (ri === undefined || ri === null) return 5000;
  return ri;
}

// An extension is "live" once its script has run. Until then the core must not
// write a value into its card: the raw payload shows as a flash of unformatted
// text before the extension paints over it.
const cfExtensionLive = {};
function cfIsExtensionLive(extId) { return !!cfExtensionLive[extId]; }
function cfMarkExtensionLive(extId) { cfExtensionLive[extId] = true; }
// How long the first mass-prime waits for js extensions to boot and claim their
// cards before the core writes into them. Heavy assets load 500ms after light
// ones, so this sits past both. After the wait the repaint-hook list is
// authoritative: extensions that painted registered a hook (or kept their DOM),
// so cfNeedsWidgetPriming no longer mistakes them for core-owned.
var CF_PRIME_DEFER_MS = 1200;

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
  // Prime core-owned widgets immediately, but give js extensions a beat to boot
  // and claim their cards first. At this point in the page (renderWidgets runs
  // before loadExtensionAssets) no extension script has executed yet, so every
  // js extension would look "core-owned" and the core would write the raw
  // payload onto cards the extension is about to paint — the "[6]" / raw-text
  // flash on entry. Waiting lets the scripts register their repaint hooks (or,
  // for hookless painters, whose DOM is preserved by cfCardIsPainted) so the ownership
  // check below is accurate.
  const primeOne = function (extId, ext) {
    if (ext.disabled) return;
    if (!cfNeedsWidgetPriming(ext, extId)) return;
    // If the extension already painted its card (hook registered, or the DOM is
    // no longer the host's), the core must not write a payload over it. This is
    // the check that survives a slow boot: a late hook still means "the
    // extension owns this card", and writing here is what showed "[6]" on
    // metadata_stripper when its heavy assets arrived after the prime.
    for (const wDef of (ext.widgets || [])) {
      const card = document.querySelector(`.widget-extension.ext-${extId}`);
      if (card && cfCardBodyClaimed(card)) continue;
      try { refreshWidget(extId, wDef); } catch (e) {
        console.error('[EXT] Error refreshing ' + extId + ':', e);
      }
    }
  };

  for (const [extId, ext] of Object.entries(data)) {
    const isJs = (ext.js_modules || []).length > 0;
    if (!isJs) { primeOne(extId, ext); continue; }  // no script: core owns it now
    // js extension: defer so it can claim its card before the core writes.
    setTimeout(function () { primeOne(extId, ext); }, CF_PRIME_DEFER_MS);
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
    const interval = cfRefreshInterval(ext);
    if (interval <= 0) continue;
    for (const wDef of (ext.widgets || [])) {
      const key = `${extId}-${wDef.id}`;
      widgetTimers[key] = setInterval(() => refreshWidget(extId, wDef), interval);
    }
  }
}
