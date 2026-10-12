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
