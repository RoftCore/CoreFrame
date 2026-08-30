(function () {
  'use strict';

  var s = window.__wc;
  var _knownExtensions = null;

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
        s.exitEditMode();
        // Close result panel
        if (typeof closeResultPanel === 'function') closeResultPanel();
        // Close any pkg-overlay dialogs
        var overlay = document.querySelector('.pkg-overlay');
        if (overlay) overlay.remove();
      }
    });

    // Restore from localStorage FIRST (synchronous) so state is available immediately
    try {
      var cached = localStorage.getItem('cf_widget_state');
      if (cached) {
        var parsed = JSON.parse(cached);
        if (parsed && parsed.scenes && Object.keys(parsed.scenes).length) {
          s._scenes = parsed.scenes;
          s._activeScene = parsed.activeScene || Object.keys(parsed.scenes)[0] || null;
          s._sceneOrder = parsed.sceneOrder || Object.keys(parsed.scenes);
        }
      }
    } catch (_) {}
    if (!s._stateLoaded) s._stateLoaded = true;
    tryAutoApply();

    // Then refresh from API (async) — will overwrite localStorage cache
    var apiInitialized = false;
    var autoAddAfterApi = true;
    s.loadState().then(function () {
      apiInitialized = true;
      tryAutoApply(true);  // force re-apply with fresh API data
      // After API loads, apply autoAddExtensions with proper hidden state
      if (autoAddAfterApi) {
        autoAddAfterApi = false;
        autoAddExtensions();
      }
    });
  }

  var _firstAutoAddDone = false;

  function autoAddExtensions() {
    var sw = s.sceneWidgets();
    var col = 1, row = 1;
    var maxCols = s.sceneCols();
    var firstRun = !_firstAutoAddDone && Object.keys(sw).length === 0;
    if (s.currentScene()) _firstAutoAddDone = true;
    for (var extId in (window.extensionsData || {})) {
      if (sw[extId]) continue;
      if (!firstRun && _knownExtensions && _knownExtensions[extId]) continue;
      // Check saved hidden state from the ACTIVE scene, not hardcoded 'default'
      var activeWidgets = s.currentScene() && s.currentScene().widgets || {};
      var saved = activeWidgets[extId];
      var hidden = false;
      if (saved && saved.hidden !== undefined) {
        hidden = saved.hidden;
      } else {
        // New widget: hidden by default (user must click Show)
        hidden = true;
      }
      var gs = s.getExtGrid(extId);
      var w = gs.w || 2;
      var h = gs.h || 2;
      if (col + w > maxCols + 1) { col = 1; row += h; }
      sw[extId] = { col: col, row: row, w: w, h: h, hidden: hidden };
      col += w;
    }
    // NOTA: no persistir aquí — si la escena está vacía (API corruption),
    // esto SOBREESCRIBIRÍA el fichero con datos incompletos.
    // persistScenes solo debe llamarse cuando el usuario modifica el estado.
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  var _applyPending = false;

  function tryAutoApply(force) {
    if (!force && _applyPending) return;
    if (!s._stateLoaded) return;
    if (!window.extensionsData || !Object.keys(window.extensionsData).length) return;
    if (!document.querySelector('.widget')) return;
    _applyPending = true;
    // Snapshot which extensions exist at page load — autoAddExtensions
    // will skip these (unless first run), preventing all widgets from
    // appearing when only a subset was saved in the scene.
    if (_knownExtensions === null) {
      _knownExtensions = {};
      for (var extId in window.extensionsData) {
        _knownExtensions[extId] = true;
      }
    }
    autoAddExtensions();
    s.applyHiddenState();
    s.applySavedLayouts();
    s.applyWidgetStyles();
    var mainContent = document.getElementById('main-content');
    if (mainContent) mainContent.style.visibility = '';
  }

  function ensureApplied() {
    tryAutoApply();
    if (_applyPending) return;
    var check = setInterval(function () {
      if (_applyPending) { clearInterval(check); return; }
      if (s._stateLoaded && window.extensionsData && Object.keys(window.extensionsData).length && document.querySelector('.widget')) {
        clearInterval(check);
        tryAutoApply();
      }
    }, 50);
  }

  function applyWidgetState() {
    _applyPending = false;  // Allow re-application (extension installs, etc.)
    ensureApplied();
  }

  window.__widgetControl = {
    enterEditMode: s.enterEditMode,
    exitEditMode: s.exitEditMode,
    enterMoveMode: s.enterEditMode,
    exitMoveMode: s.exitEditMode,
    enterResizeMode: s.enterEditMode,
    exitResizeMode: s.exitEditMode,
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
