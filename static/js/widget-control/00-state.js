(function () {
  'use strict';

  window.__wc = window.__wc || {};
  var s = window.__wc;

  s._scenes = {};
  s._sceneOrder = [];
  s._activeScene = null;
  s._stateLoaded = false;
  s._savePending = false;
  s.moveMode = false;
  s.resizeMode = false;
  s.resizeTarget = null;

  s.currentScene = function () { return s._scenes[s._activeScene] || null; };

  s.sceneWidgets = function () {
    var c = s.currentScene();
    return c ? c.widgets : {};
  };

  s.sceneCols = function () {
    return (s._scenes[s._activeScene] && s._scenes[s._activeScene].cols) || 12;
  };

  s.persistScenes = function () {
    try {
      localStorage.setItem('cf_widget_state', JSON.stringify({
        scenes: s._scenes, activeScene: s._activeScene, sceneOrder: s._sceneOrder
      }));
    } catch (_) {}
    return apiFetch('/api/widget-state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenes: s._scenes, activeScene: s._activeScene, sceneOrder: s._sceneOrder })
    });
  };

  s.getExtGrid = function (extId) {
    var ext = (window.extensionsData || {})[extId] || {};
    return ext.grid_size || {};
  };

  s.showToast = function (msg) {
    if (typeof showToast !== 'undefined') showToast(msg);
  };

  // Visibility contract: ask cfHidden(), never read style.display (pitfall 29).
  function keepAlive(extId) {
    var ext = (window.extensionsData || {})[extId] || {};
    return ext.keep_alive !== false;
  }

  // Off-scene cards keep their decoded images on purpose: display:none throws the
  // decode away and a photo-heavy scene costs ~1 s to come back (pitfall 29). Keeping
  // it forever costs memory instead - one renderer reached 506 MB - so the decode is
  // kept for a while and released per card, without touching the grid.
  var CF_OFFSCENE_RELEASE_MS = (typeof window.__cfOffsceneReleaseMs === 'number')
    ? window.__cfOffsceneReleaseMs : 120000;

  function releaseDecode(el) {
    if (!el || !el.isConnected) return;
    if (!el.classList.contains('cf-offscene')) return;  // it came back meanwhile
    el.dataset.cfDecodeReleased = '1';
    el.style.display = 'none';
  }

  s.cfHidden = function (el) {
    if (!el) return true;
    return el.style.display === 'none' || el.classList.contains('cf-offscene');
  };

  s.cfHide = function (el) {
    if (!el) return;
    if (keepAlive(el.dataset.extId)) {
      el.classList.add('cf-offscene');
      // A released card stays released: restoring display would decode it again.
      if (!el.dataset.cfDecodeReleased) el.style.display = '';
      if (!el._cfReleaseTimer) {
        el._cfReleaseTimer = setTimeout(function () {
          el._cfReleaseTimer = null;
          releaseDecode(el);
        }, CF_OFFSCENE_RELEASE_MS);
      }
    } else {
      el.classList.remove('cf-offscene');
      el.style.display = 'none';
    }
  };

  s.cfShow = function (el) {
    if (!el) return;
    if (el._cfReleaseTimer) {
      clearTimeout(el._cfReleaseTimer);
      el._cfReleaseTimer = null;
    }
    el.classList.remove('cf-offscene');
    el.style.display = '';
    if (el.dataset.cfDecodeReleased) delete el.dataset.cfDecodeReleased;
  };

  // Short globals: app.js and the layout module ask constantly.
  window.cfHidden = s.cfHidden;
  window.cfHide = s.cfHide;
  window.cfShow = s.cfShow;
})();
