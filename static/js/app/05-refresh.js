// Extensions that paint their own card register here so the core can ask for a repaint.
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
  cfRerenderHandlers[extId] = fn;
  // Registration precedes the paint, so the shimmer stays; the extension now owns the DOM.
  const meta = (window.extensionsData || {})[extId];
  for (const w of ((meta && meta.widgets) || [])) {
    const k = `${extId}-${w.id}`;
    if (widgetTimers[k]) { clearInterval(widgetTimers[k]); delete widgetTimers[k]; }
  }
};

// A declared 0 means "do not poll me" and must not fall through to the default.
function cfRefreshInterval(ext) {
  const ri = ext && ext.refresh_interval;
  if (ri === undefined || ri === null) return 5000;
  return ri;
}

// "Live" means the script has run; before that the core leaves the card alone.
const cfExtensionLive = {};
function cfIsExtensionLive(extId) { return !!cfExtensionLive[extId]; }
function cfMarkExtensionLive(extId) { cfExtensionLive[extId] = true; }
// Grace before the first prime, so js extensions can claim their cards first.
var CF_PRIME_DEFER_MS = 1200;

// The core owns the values unless a repaint handler means the JS draws them itself.
function cfCoreOwnsWidgets(ext, extId) {
  if (!ext.js_modules || !ext.js_modules.length) return true;   // no JS: core owns
  return !cfHasRerenderHandler(extId);                          // JS paints => extension owns
}

// JS extensions own their content, except when nothing would ever fill the card.
function cfNeedsWidgetPriming(ext, extId) {
  if (cfCoreOwnsWidgets(ext, extId)) {
// Core-owned: prime it, unless it has no clock at all (one call then fills it for good).
    const interval = ext.refresh_interval || 0;
    return !(ext.realtime === true || interval > 0);
  }
  // Extension paints its own body; the core stays out of it.
  return false;
}

function refreshAllWidgets(data) {
  // Prime core-owned widgets, but let js extensions boot and claim their cards first.
  const primeOne = function (extId, ext) {
    if (ext.disabled) return;
    if (!cfNeedsWidgetPriming(ext, extId)) return;
    // A late hook still means the extension owns this card; writing here is the bug.
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

// Hidden widgets cost zero backend calls and zero DOM work.
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
  // No backend calls and no DOM writes mid-drag; the next tick catches up.
  if (window.__coreframeDragging) return;
  // Anti pile-up: a still-running call skips instead of stacking requests.
  if (widgetInflight[key]) return;
  if (!isWidgetActive(extId, wDef.id)) return;
  const el = document.querySelector(`[data-widget-id="${wDef.id}"][data-ext-id="${extId}"]`);
  if (!el) return;
  if (wDef.action) {
    widgetInflight[key] = true;
    try {
      const response = await apiFetch(`/api/extension/${extId}/${wDef.action}`);
      // Give a JS-painted body a moment to mount, and write nothing if it claimed it.
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
      // A widget still on its empty marker is retried: the host asks once, and a slow
      // first attempt left it on "--" for the rest of the session.
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
    // Keep the clock wherever the core still owns the values, realtime or not.
    if (!cfCoreOwnsWidgets(ext, extId)) continue;
    const interval = cfRefreshInterval(ext);
    if (interval <= 0) continue;
    for (const wDef of (ext.widgets || [])) {
      const key = `${extId}-${wDef.id}`;
      widgetTimers[key] = setInterval(() => refreshWidget(extId, wDef), interval);
    }
  }
}
