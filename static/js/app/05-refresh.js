// ── Repaint registry ──────────────────────────────────────────────
// Extensions that paint their own card register here so the core can ask them
// to repaint after the card is rebuilt.
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
  // Registration precedes the paint, so the shimmer stays until cfWatchForFirstPaint.
  // Drop any core clock: the extension owns the DOM from now on.
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
