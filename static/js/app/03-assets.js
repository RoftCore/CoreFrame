// Asset loading: an extension's CSS/JS only loads when its card nears the viewport (pitfall 54).

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
  // The 8 s failsafe may have cleared the shimmer while assets were still deferred.
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
      // A "module" script instead gets its own top-level scope, so two extensions can
      // declare the same function without one overwriting the other.
      if (ext.script_scope === 'module') script.type = 'module';
      else script.async = false;
      script.src = src;
      // Ask for a repaint once the code has actually run: a notification sent at append time races the script, and the handler is registered while it loads.
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

// Scene switch: the cards are about to be visible, so skip waiting for the observer.
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
