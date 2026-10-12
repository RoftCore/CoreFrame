/* Undo/redo for layout changes: Ctrl+Z and Ctrl+Shift+Z.
 *
 * Snapshot based, per (scene, widget). Each entry keeps the widget's
 * {col,row,w,h,hidden} before and after the change, so undo restores exactly
 * what was there and never replays side effects.
 *
 * Recorded: showing/hiding a widget, moving one, resizing one.
 * NOT recorded: installing an extension, deleting a widget, creating or deleting
 * a scene. Those either are not layout changes or destroy state an entry would
 * have to resurrect, so pretending to undo them would be a lie.
 *
 * The capture point matters: saveWidgetLayout is called up to 15 times during a
 * single drop (the resolver's fallbacks), so recording there would fill the
 * history with one entry per fallback. The "before" is therefore taken when the
 * gesture starts and the "after" when it ends, giving one entry per real action.
 *
 * Ten steps deep, oldest dropped. A new action clears the redo stack, as usual. */

(function () {
  'use strict';

  var MAX = 10;
  var past = [];
  var future = [];
  var s = window.__wc || {};

  function snap(sceneId, extId) {
    var sc = s._scenes && s._scenes[sceneId];
    if (!sc || !sc.widgets || !sc.widgets[extId]) return null;
    var w = sc.widgets[extId];
    return { col: w.col, row: w.row, w: w.w, h: w.h, hidden: !!w.hidden };
  }

  function same(a, b) {
    if (!a || !b) return false;
    return a.col === b.col && a.row === b.row && a.w === b.w &&
           a.h === b.h && a.hidden === b.hidden;
  }

  function restore(entry, which) {
    var state = entry[which];
    var sc = s._scenes && s._scenes[entry.scene];
    if (!state || !sc) return false;
    sc.widgets = sc.widgets || {};
    sc.widgets[entry.extId] = {
      col: state.col, row: state.row, w: state.w, h: state.h, hidden: !!state.hidden
    };
    if (entry.scene === s._activeScene) {
      var el = document.querySelector('.widget-extension.ext-' + entry.extId);
      if (el) {
        if (state.hidden) cfHide(el); else cfShow(el);
        el.style.gridColumn = state.col + ' / span ' + state.w;
        el.style.gridRow = state.row + ' / span ' + state.h;
        if (typeof s.applyStyleToWidget === 'function') {
          try { s.applyStyleToWidget(entry.extId); } catch (e) {}
        }
      }
// A drop leaves a spacer and projection behind that would keep the old cell occupied.
      document.querySelectorAll('.widget-drag-placeholder, .widget-drag-spacer')
        .forEach(function (n) { n.remove(); });
      if (typeof s.applyHiddenState === 'function') {
        try { s.applyHiddenState(); } catch (e) {}
      }
    }
    s.persistScenes();
    return true;
  }

  var api = {
    MAX: MAX,

    snapshot: function (extId, sceneId) {
      return snap(sceneId || s._activeScene, extId);
    },

    /* before/after come from snapshot(); the gesture code takes one at the start
     * and one at the end. Entries with no real change are dropped, so a click
     * that did not move anything does not consume a step. */
    record: function (label, extId, scene, before, after) {
      if (!extId || !before || !after) return false;
      if (same(before, after)) return false;
      past.push({ label: label, scene: scene || s._activeScene, extId: extId,
                  before: before, after: after });
      while (past.length > MAX) past.shift();
      future.length = 0;
      return true;
    },

    undo: function () {
      if (!past.length) return false;
      var entry = past.pop();
      future.push(entry);
      if (!restore(entry, 'before')) {
// Scene is gone: put it back so the stack stays consistent.
        future.pop();
        past.push(entry);
        return false;
      }
      s.showToast('Undo: ' + entry.label);
      return true;
    },

    redo: function () {
      if (!future.length) return false;
      var entry = future.pop();
      past.push(entry);
      if (!restore(entry, 'after')) {
        past.pop();
        future.push(entry);
        return false;
      }
      s.showToast('Redo: ' + entry.label);
      return true;
    },

    canUndo: function () { return past.length > 0; },
    canRedo: function () { return future.length > 0; },
    depth: function () { return { past: past.length, future: future.length }; },
    clear: function () { past.length = 0; future.length = 0; }
  };

  window.cfHistory = api;
  s.history = api;

  /* Ctrl+Z / Ctrl+Shift+Z, and Ctrl+Y as the usual alias for redo.
   * Capture phase so a widget that stops propagation cannot swallow the key,
   * and skipped entirely while typing so undo never eats a character. */
  document.addEventListener('keydown', function (e) {
    if (!(e.ctrlKey || e.metaKey) || e.altKey) return;
    var k = (e.key || '').toLowerCase();
    if (k !== 'z' && k !== 'y') return;
    var t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' ||
              t.tagName === 'SELECT' || t.isContentEditable)) return;
    e.preventDefault();
    if (k === 'y' || e.shiftKey) api.redo(); else api.undo();
  }, true);
})();