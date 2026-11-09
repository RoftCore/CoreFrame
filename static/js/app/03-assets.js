// ── Asset loading ─────────────────────────────────────────────────
// An extension whose card is not near the viewport does not need its CSS or its
// JS yet. Loading every stylesheet at boot is the most expensive thing the page
// does at scale: measured 400 ms for 1.000 sheets and 8 s for 3.000, and the
// curve is superlinear. The card keeps its skeleton until its assets land, which
// is exactly what a slow extension already looks like today.
//
// The old light/heavy split and its 500 ms delay are gone: with demand loading
// only the cards around the viewport load, which is the same budget the light
// ones already used.

const CF_ASSET_MARGIN = '150% 0px 150% 0px';   // a screen and a half ahead
let cfAssetIO = null;
const cfAssetPending = {};                     // extId -> ext, waiting for its card

function cfAssetCard(extId) {
  if (typeof cfPollCard === 'function') return cfPollCard(extId);
  return document.querySelector('.widget-extension.ext-' + extId);
}

function cfAssetObserver() {
  if (cfAssetIO || typeof IntersectionObserver === 'undefined') return cfAssetIO;
  cfAssetIO = new IntersectionObserver(function (entries) {
    for (let i = 0; i < entries.length; i++) {
      if (!entries[i].isIntersecting) continue;
      const card = entries[i].target;
      const extId = card.dataset.extId;
      const ext = extId && cfAssetPending[extId];
      if (!ext) continue;
      delete cfAssetPending[extId];
      try { cfAssetIO.unobserve(card); } catch (e) {}
      cfLoadExtAssetsNow(extId, ext);
    }
  }, { rootMargin: CF_ASSET_MARGIN, threshold: 0 });
  return cfAssetIO;
}

function cfLoadExtAssetsNow(extId, ext) {
  // A card can have lost its shimmer to the 8 s failsafe while its assets were
  // still deferred. Show it again instead of an empty body while they load.
  var card = cfAssetCard(extId);
  if (card && (ext.js_modules || []).length && typeof cfCardBodyClaimed === 'function' &&
      !cfCardBodyClaimed(card) && typeof cfMarkLoadingState === 'function') {
    cfMarkLoadingState(card, (ext.widgets || []).length);
    if (typeof cfWatchForFirstPaint === 'function') cfWatchForFirstPaint(card, extId);
  }
  // Cache-buster per page load: a stale bundle looks exactly like a failed fix (pitfall 4).
  var assetV = (typeof window.__cfAssetV !== 'undefined' && window.__cfAssetV) ||
    (window.__cfAssetV = Date.now());
  for (var i = 0; i < (ext.js_modules || []).length; i++) {
    (function (mod) {
      var src = '/ext-static/' + extId + '/' + mod + '?v=' + assetV;
      if (document.querySelector('script[src="' + src + '"]')) return;
      var script = document.createElement('script');
      // async=false restores declaration order: dynamic classic scripts default to async=true.
      script.async = false;
      script.src = src;
      // Ask for a repaint once the code has actually run: a notification sent at
      // append time races the script, and the handler is registered while it loads.
      script.onload = function () {
        if (typeof cfNotifyCardRerender === 'function') cfNotifyCardRerender(extId);
      };
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

function loadExtensionAssets(data) {
  var io = cfAssetObserver();
  for (var extId in data) {
    var ext = data[extId];
    // Disabled: listed, but no card, no assets and no polling.
    if (!ext || ext.disabled) continue;
    var card = cfAssetCard(extId);
    if (!io || !card) { cfLoadExtAssetsNow(extId, ext); continue; }
    cfAssetPending[extId] = ext;
    try { io.observe(card); } catch (e) { cfLoadExtAssetsNow(extId, ext); }
  }
}

// Scene switch: the cards are about to be visible, so do not wait for the
// observer to fire on the next frame. Also used by any caller that knows a
// widget is about to be shown.
function cfPrefetchAssets(extIds) {
  for (var i = 0; i < (extIds || []).length; i++) {
    var extId = extIds[i];
    var ext = cfAssetPending[extId];
    if (!ext) continue;
    delete cfAssetPending[extId];
    var card = cfAssetCard(extId);
    if (cfAssetIO && card) { try { cfAssetIO.unobserve(card); } catch (e) {} }
    cfLoadExtAssetsNow(extId, ext);
  }
}
