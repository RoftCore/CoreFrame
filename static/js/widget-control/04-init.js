(function () {
  'use strict';

  var s = window.__wc;

  function init() {
    document.getElementById('btn-settings').addEventListener('click', function (e) {
      s.openSettingsDropdown(e);
    });

    document.addEventListener('contextmenu', function (e) {
      if (e.target.closest('#mode-indicator-bar')) { s.closeCtxMenu(); return; }
      if (e.target.closest('#scene-bar')) return;
      var widget = e.target.closest('.widget');
      e.preventDefault();
      e.stopPropagation();
      if (widget) {
        s.openCtxMenu(e, widget);
      } else {
        s.openEmptyCtxMenu(e);
      }
    });

    document.addEventListener('click', function (e) {
      if (!e.target.closest('#ctx-menu')) s.closeCtxMenu();
      if (!e.target.closest('#scene-ctx-menu')) s.closeSceneCtxMenu();
      if (!e.target.closest('#settings-ctx-menu') && !e.target.closest('#btn-settings')) s.closeSettingsDropdown();
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        s.closeCtxMenu();
        s.closeSceneCtxMenu();
        s.closeSettingsDropdown();
        s.exitMoveMode();
        s.resizeTarget = null;
        s.exitResizeMode();
      }
    });

    s.loadState().then(function () {
      s._stateLoaded = true;
      autoAddExtensions();
      if (document.querySelector('.widget')) {
        s.applyHiddenState();
        s.applySavedLayouts();
        s.applyWidgetStyles();
      }
    });
  }

  function autoAddExtensions() {
    var sw = s.sceneWidgets();
    var changed = false;
    var col = 1, row = 1;
    var maxCols = s.sceneCols();
    for (var extId in (window.extensionsData || {})) {
      if (sw[extId]) continue;
      var gs = s.getExtGrid(extId);
      var w = gs.w || 2;
      var h = gs.h || 2;
      if (col + w > maxCols + 1) { col = 1; row += h; }
      sw[extId] = { col: col, row: row, w: w, h: h, hidden: false };
      col += w;
      changed = true;
    }
    if (changed) s.persistScenes();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  function applyWidgetState() {
    function done() {
      if (s._stateLoaded) autoAddExtensions();
      s.applyHiddenState();
      s.applySavedLayouts();
      s.applyWidgetStyles();
      var mc = document.getElementById('main-content');
      if (mc) mc.style.visibility = '';
    }
    if (s._stateLoaded) {
      done();
    } else {
      var check = setInterval(function () {
        if (s._stateLoaded) {
          clearInterval(check);
          done();
        }
      }, 50);
    }
  }

  window.__widgetControl = {
    enterMoveMode: s.enterMoveMode,
    exitMoveMode: s.exitMoveMode,
    enterResizeMode: s.enterResizeMode,
    exitResizeMode: s.exitResizeMode,
    applyWidgetState: applyWidgetState,
    autoAddExtensions: autoAddExtensions,
    persistScenes: s.persistScenes,
    switchScene: s.switchScene,
    createScene: s.createScene,
    deleteScene: s.deleteScene,
    openSceneSettings: s.openSceneSettings,
    _activeScene: function () { return s._activeScene; },
    _scenes: function () { return s._scenes; },
    currentScene: s.currentScene,
    unhideWidget: s.unhideWidget,
    getHidden: s.getHidden,
    openEmptyCtxMenu: s.openEmptyCtxMenu,
    openCtxMenu: s.openCtxMenu
  };
})();
