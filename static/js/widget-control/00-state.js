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

  s.cfHidden = function (el) {
    if (!el) return true;
    return el.style.display === 'none' || el.classList.contains('cf-offscene');
  };

  s.cfHide = function (el) {
    if (!el) return;
    if (keepAlive(el.dataset.extId)) {
      el.classList.add('cf-offscene');
      el.style.display = '';
    } else {
      el.classList.remove('cf-offscene');
      el.style.display = 'none';
    }
  };

  s.cfShow = function (el) {
    if (!el) return;
    el.classList.remove('cf-offscene');
    el.style.display = '';
  };

  // Short globals: app.js and the layout module ask constantly.
  window.cfHidden = s.cfHidden;
  window.cfHide = s.cfHide;
  window.cfShow = s.cfShow;
})();
