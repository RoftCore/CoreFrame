(function () {
  'use strict';

  // ----- server-side state -----
  var _widgetState = { layout: {}, hidden: {} };
  var _stateLoaded = false;
  var _savePending = false;

  function loadState() {
    return apiFetch('/api/widget-state').then(function (data) {
      if (data && !data.error) {
        _widgetState = {
          layout: data.layout || {},
          hidden: data.hidden || {}
        };
        _stateLoaded = true;
      }
    });
  }

  function persistState() {
    if (_savePending) return;
    _savePending = true;
    setTimeout(function () {
      _savePending = false;
      apiFetch('/api/widget-state', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(_widgetState)
      });
    }, 200);
  }

  function getHidden() { return _widgetState.hidden; }

  function getLayout() { return _widgetState.layout; }

  function saveWidgetLayout(extId, col, row, wSpan, hSpan) {
    if (!extId) return;
    _widgetState.layout[extId] = { col: Math.max(1, col), row: Math.max(1, row), w: Math.max(1, wSpan), h: Math.max(1, hSpan) };
    persistState();
  }

  function saveAllLayouts() {
    var layout = {};
    document.querySelectorAll('.widget-extension').forEach(function (w) {
      if (w.style.display === 'none') return;
      var gc = (w.style.gridColumn || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
      var gr = (w.style.gridRow || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
      if (gc && gr && w.dataset.extId) {
        layout[w.dataset.extId] = {
          col: parseInt(gc[1],10), row: parseInt(gr[1],10),
          w: parseInt(gc[2],10), h: parseInt(gr[2],10)
        };
      }
    });
    _widgetState.layout = layout;
    persistState();
  }

  function applySavedLayouts() {
    var layout = getLayout();
    for (var extId in layout) {
      if (!layout.hasOwnProperty(extId)) continue;
      var pos = layout[extId];
      var w = document.querySelector('.widget-extension.ext-' + extId);
      if (w) {
        w.style.minHeight = '';
        w.style.gridColumn = pos.col + ' / span ' + (pos.w || 2);
        w.style.gridRow = pos.row + ' / span ' + (pos.h || 2);
      }
    }
  }

  function applyHiddenState() {
    var hidden = getHidden();
    for (var extId in hidden) {
      if (!hidden.hasOwnProperty(extId)) continue;
      var w = document.querySelector('.widget-extension.ext-' + extId);
      if (w) w.style.display = 'none';
    }
  }

  // ----- context menu -----
  let moveMode = false;
  let resizeMode = false;
  let resizeTarget = null;

  function getOrCreateCtxMenu() {
    let m = document.getElementById('ctx-menu');
    if (m) return m;
    m = document.createElement('div');
    m.id = 'ctx-menu';
    m.className = 'ctx-menu';
    m.innerHTML =
      '<div class="ctx-menu-item" data-action="hide">\u{1F5D1}  Hide widget</div>' +
      '<div class="ctx-menu-item" data-action="move">\u{2194}  Move widget</div>' +
      '<div class="ctx-menu-item" data-action="resize">\u{2197}  Resize widget</div>' +
      '<div class="ctx-menu-separator"></div>' +
      '<div class="ctx-menu-item" data-action="show" id="ctx-show-btn" style="display:none">\u{1F441}  Show hidden widgets...</div>';
    document.body.appendChild(m);

    m.addEventListener('click', function (e) {
      const item = e.target.closest('.ctx-menu-item');
      if (!item) return;
      const action = item.dataset.action;
      const target = document.querySelector('.ctx-target');
      if (action === 'show') {
        showHiddenPanel();
      } else if (target) {
        if (action === 'hide') hideWidget(target);
        else if (action === 'move') enterMoveMode();
        else if (action === 'resize') enterResizeMode(target);
      }
      closeCtxMenu();
    });

    return m;
  }

  function openCtxMenu(e, widget) {
    closeCtxMenu();
    document.querySelectorAll('.ctx-target').forEach(function (el) { return el.classList.remove('ctx-target'); });
    widget.classList.add('ctx-target');

    const menu = getOrCreateCtxMenu();
    menu.querySelectorAll('[data-action="hide"],[data-action="move"],[data-action="resize"]').forEach(function (el) { return el.style.display = 'flex'; });
    menu.querySelector('.ctx-menu-separator').style.display = 'block';
    const hidden = getHidden();
    document.getElementById('ctx-show-btn').style.display = Object.keys(hidden).length > 0 ? 'flex' : 'none';

    menu.style.left = Math.min(e.clientX, window.innerWidth - 200) + 'px';
    menu.style.top = Math.min(e.clientY, window.innerHeight - 160) + 'px';
    menu.classList.add('visible');
  }

  function openEmptyCtxMenu(e) {
    const hidden = getHidden();
    if (Object.keys(hidden).length === 0) return;
    closeCtxMenu();
    document.querySelectorAll('.ctx-target').forEach(function (el) { return el.classList.remove('ctx-target'); });
    const menu = getOrCreateCtxMenu();
    menu.querySelectorAll('[data-action="hide"],[data-action="move"],[data-action="resize"]').forEach(function (el) { return el.style.display = 'none'; });
    menu.querySelector('.ctx-menu-separator').style.display = 'none';
    document.getElementById('ctx-show-btn').style.display = 'flex';
    menu.style.left = Math.min(e.clientX, window.innerWidth - 200) + 'px';
    menu.style.top = Math.min(e.clientY, window.innerHeight - 100) + 'px';
    menu.classList.add('visible');
  }

  function closeCtxMenu() {
    const m = document.getElementById('ctx-menu');
    if (m) m.classList.remove('visible');
    document.querySelectorAll('.ctx-target').forEach(function (el) { return el.classList.remove('ctx-target'); });
  }

  // ----- hide / show -----
  function hideWidget(widget) {
    const extId = widget.dataset.extId;
    if (!extId) return;
    _widgetState.hidden[extId] = true;
    persistState();
    widget.style.display = 'none';
  }

  function showHiddenPanel() {
    const panel = document.getElementById('result-panel');
    const overlay = document.getElementById('overlay');
    const title = document.getElementById('result-panel-title');
    const body = document.getElementById('result-panel-body');
    title.textContent = 'Hidden Widgets';

    const hidden = getHidden();
    const keys = Object.keys(hidden);
    if (keys.length === 0) {
      body.innerHTML = '<div style="padding:20px;color:var(--text-muted);font-family:var(--font-mono);font-size:12px;">No hidden widgets</div>';
    } else {
      let html = '<div style="font-family:var(--font-mono);">';
      keys.forEach(function (extId) {
        const name = (window.extensionsData && extensionsData[extId] && extensionsData[extId].name) || extId;
        html += '<div class="ctx-hidden-item" data-ext-id="' + extId + '">' +
          '<span>' + escapeHtml(name) + '</span>' +
          '<span class="ctx-show-action">Show</span>' +
        '</div>';
      });
      html += '</div>';
      body.innerHTML = html;
      body.querySelectorAll('.ctx-hidden-item').forEach(function (el) {
        el.addEventListener('click', function () {
          unhideWidget(el.dataset.extId);
          el.remove();
          if (body.querySelectorAll('.ctx-hidden-item').length === 0) {
            body.innerHTML = '<div style="padding:20px;color:var(--text-muted);font-family:var(--font-mono);font-size:12px;">No hidden widgets</div>';
          }
          if (Object.keys(getHidden()).length === 0) {
            closeCtxMenu();
          }
        });
      });
    }

    panel.classList.add('open');
    overlay.classList.add('open');
  }

  function unhideWidget(extId) {
    delete _widgetState.hidden[extId];
    persistState();
    const w = document.querySelector('.widget-extension.ext-' + extId);
    if (w) w.style.display = '';
  }

  // ----- collision helpers -----
  function getOccupiedCells(col, row, w, h) {
    const cells = [];
    for (let c = col; c < col + w; c++)
      for (let r = row; r < row + h; r++)
        cells.push(c + ',' + r);
    return cells;
  }

  function hasCollisionWithNonOverlayable(extId, col, row, w, h) {
    const target = getOccupiedCells(col, row, w, h);
    const widgets = document.querySelectorAll('.widget-extension');
    for (const w of widgets) {
      if (w.dataset.extId === extId || w.dataset.overlayable === 'true' || w.style.display === 'none') continue;
      const gc = (w.style.gridColumn || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
      const gr = (w.style.gridRow || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
      if (!gc || !gr) continue;
      const other = getOccupiedCells(parseInt(gc[1],10), parseInt(gr[1],10), parseInt(gc[2],10), parseInt(gr[2],10));
      for (const cell of target)
        if (other.indexOf(cell) !== -1) return true;
    }
    return false;
  }

  // ----- move mode -----
  function enterMoveMode() {
    if (resizeMode) exitResizeMode();
    if (moveMode) return;
    moveMode = true;
    document.body.classList.add('move-mode');
    freezeAllPositions();

    const bar = document.createElement('div');
    bar.id = 'mode-indicator-bar';
    bar.className = 'mode-indicator';
    bar.innerHTML =
      '<span>MOVE \u2014 Drag any widget</span>' +
      '<button class="mode-exit-btn" id="mode-toggle-btn">Resize \u2194</button>' +
      '<button class="mode-exit-btn" id="mode-exit-btn">Exit \u2715</button>';
    document.body.prepend(bar);
    document.getElementById('mode-exit-btn').addEventListener('click', exitMoveMode);
    document.getElementById('mode-toggle-btn').addEventListener('click', function () {
      exitMoveMode();
      enterResizeMode(resizeTarget);
    });

    let dragEl = null, startCol = 1, startRow = 1, wSpan = 2, hSpan = 2, gridRect = null, colWidth = 0, rowHeight = 0;
    let overlayable = false;
    let _wasDragged = false;
    let offsetX = 0, offsetY = 0;

    function onDown(e) {
      if (!moveMode || e.button !== 0) return;
      const widget = e.target.closest('.widget');
      if (!widget || widget.closest('#mode-indicator-bar')) return;
      e.preventDefault();
      _wasDragged = false;
      dragEl = widget;
      overlayable = dragEl.dataset.overlayable === 'true';
      dragEl.classList.add('widget-moving');

      const grid = widget.closest('.widget-grid');
      if (!grid) { dragEl = null; return; }
      gridRect = grid.getBoundingClientRect();
      colWidth = gridRect.width / 12;
      rowHeight = 93;

      const cs = getComputedStyle(widget);
      const gc = cs.gridColumn || widget.style.gridColumn || 'auto / span 2';
      const gr = cs.gridRow || widget.style.gridRow || 'auto / span 2';
      wSpan = parseInt((gc.match(/span\s+(\d+)/) || [,'2'])[1], 10);
      hSpan = parseInt((gr.match(/span\s+(\d+)/) || [,'2'])[1], 10);

      const wr = widget.getBoundingClientRect();
      startCol = Math.max(1, Math.round((wr.left - gridRect.left) / colWidth) + 1);
      startRow = Math.max(1, Math.round((wr.top - gridRect.top) / rowHeight) + 1);

      offsetX = (e.clientX - wr.left) / colWidth;
      offsetY = (e.clientY - wr.top) / rowHeight;

      widget.style.gridColumn = startCol + ' / span ' + wSpan;
      widget.style.gridRow = startRow + ' / span ' + hSpan;

      document.addEventListener('mousemove', onMove, true);
      document.addEventListener('mouseup', onUp, true);
    }

    function onMove(e) {
      if (!dragEl || !gridRect) return;
      _wasDragged = true;
      let col = Math.round((e.clientX - gridRect.left) / colWidth - offsetX) + 1;
      let row = Math.round((e.clientY - gridRect.top) / rowHeight - offsetY) + 1;
      col = Math.max(1, Math.min(13 - wSpan, col));
      row = Math.max(1, Math.min(100, row));

      if (!overlayable && hasCollisionWithNonOverlayable(dragEl.dataset.extId, col, row, wSpan, hSpan)) {
        dragEl.classList.add('widget-collision');
        return;
      }
      dragEl.classList.remove('widget-collision');
      dragEl.style.gridColumn = col + ' / span ' + wSpan;
      dragEl.style.gridRow = row + ' / span ' + hSpan;
    }

    function onUp() {
      document.removeEventListener('mousemove', onMove, true);
      document.removeEventListener('mouseup', onUp, true);
      if (dragEl) {
        dragEl.classList.remove('widget-moving', 'widget-collision');
        const extId = dragEl.dataset.extId;
        if (extId) {
          const match = dragEl.style.gridColumn.match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
          const matchR = dragEl.style.gridRow.match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
          if (match && matchR) {
            var c = parseInt(match[1],10), w = parseInt(match[2],10);
            var r = parseInt(matchR[1],10), h = parseInt(matchR[2],10);
            if (!overlayable && hasCollisionWithNonOverlayable(extId, c, r, w, h)) {
              dragEl.style.gridColumn = startCol + ' / span ' + wSpan;
              dragEl.style.gridRow = startRow + ' / span ' + hSpan;
            } else {
              saveWidgetLayout(extId, c, r, w, h);
            }
          }
        }
        dragEl = null;
      }
    }

    function onClickSuppress(e) {
      if (_wasDragged) { e.stopPropagation(); _wasDragged = false; }
    }

    document.addEventListener('mousedown', onDown);
    document.addEventListener('click', onClickSuppress, true);
    document._moveCleanup = function () {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('mousemove', onMove, true);
      document.removeEventListener('mouseup', onUp, true);
      document.removeEventListener('click', onClickSuppress, true);
    };
  }

  function exitMoveMode() {
    if (!moveMode) return;
    moveMode = false;
    document.body.classList.remove('move-mode');
    if (document._moveCleanup) { document._moveCleanup(); document._moveCleanup = null; }
    const bar = document.getElementById('mode-indicator-bar');
    if (bar) bar.remove();
    document.querySelectorAll('.widget-moving').forEach(function (el) { return el.classList.remove('widget-moving'); });
  }

  // Freeze all widget positions so CSS Grid doesn't reflow others on resize/move
  function freezeAllPositions() {
    document.querySelectorAll('.widget-extension').forEach(function (w) {
      if (w.style.display === 'none') return;
      w.style.minHeight = '';
      var gc = w.style.gridColumn;
      var gr = w.style.gridRow;
      var needsFreeze = /^span\s+\d+$/.test(gc);
      if (needsFreeze) {
        var grid = w.closest('.widget-grid');
        if (!grid) return;
        var gridRect = grid.getBoundingClientRect();
        var colWidth = gridRect.width / 12;
        var rowHeight = 93;
        var wr = w.getBoundingClientRect();
        var col = Math.max(1, Math.round((wr.left - gridRect.left) / colWidth) + 1);
        var row = Math.max(1, Math.round((wr.top - gridRect.top) / rowHeight) + 1);
        var spanW = parseInt((gc.match(/\d+/) || ['2'])[0], 10);
        var spanH = parseInt((gr.match(/\d+/) || ['2'])[0], 10);
        w.style.gridColumn = col + ' / span ' + spanW;
        w.style.gridRow = row + ' / span ' + spanH;
      }
    });
  }

  // ----- resize mode (grid-based, PowerPoint-style) -----
  function getWidgetGridInfo(w) {
    var gc = (w.style.gridColumn || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
    var gr = (w.style.gridRow || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
    if (!gc || !gr) return null;
    return {
      el: w, extId: w.dataset.extId,
      overlayable: w.dataset.overlayable === 'true',
      col: parseInt(gc[1],10), row: parseInt(gr[1],10),
      w: parseInt(gc[2],10), h: parseInt(gr[2],10)
    };
  }

  function getAllWidgetInfos() {
    var result = [];
    document.querySelectorAll('.widget-extension').forEach(function (w) {
      if (w.style.display === 'none') return;
      var info = getWidgetGridInfo(w);
      if (info) result.push(info);
    });
    return result;
  }

  function detectEdges(w, mx, my) {
    var r = w.getBoundingClientRect();
    var t = 12;
    return {
      top: Math.abs(my - r.top) < t,
      bottom: Math.abs(my - r.bottom) < t,
      left: Math.abs(mx - r.left) < t,
      right: Math.abs(mx - r.right) < t
    };
  }

  function cursorForEdges(edges) {
    if (edges.top && edges.left) return 'nw-resize';
    if (edges.top && edges.right) return 'ne-resize';
    if (edges.bottom && edges.left) return 'sw-resize';
    if (edges.bottom && edges.right) return 'se-resize';
    if (edges.top) return 'n-resize';
    if (edges.bottom) return 's-resize';
    if (edges.left) return 'w-resize';
    if (edges.right) return 'e-resize';
    return '';
  }

  function cellsOverlap(a, b) {
    return !(a.col + a.w <= b.col || b.col + b.w <= a.col ||
             a.row + a.h <= b.row || b.row + b.h <= a.row);
  }

  function cascadeResolve(widgets, draggedExtId) {
    var changed = true, maxIter = 30;
    while (changed && maxIter-- > 0) {
      changed = false;
      for (var i = 0; i < widgets.length; i++) {
        for (var j = 0; j < widgets.length; j++) {
          if (i === j || widgets[i].extId === widgets[j].extId) continue;
          var a = widgets[i], b = widgets[j];
          if (b.overlayable || b.extId === draggedExtId || !cellsOverlap(a, b)) continue;

          var pushRight = (a.col + a.w) - b.col;
          var pushDown = (a.row + a.h) - b.row;

          if (pushRight > 0 && (pushRight <= pushDown || pushDown <= 0)) {
            b.col = a.col + a.w;
            if (b.col + b.w > 13) { b.col = 1; b.row = a.row + a.h; }
          } else if (pushDown > 0) {
            b.row = a.row + a.h;
            if (b.row + b.h > 100) { b.row = 1; b.col = a.col + a.w; }
          }
          a = widgets[i]; b = widgets[j];
          b.el.style.gridColumn = b.col + ' / span ' + b.w;
          b.el.style.gridRow = b.row + ' / span ' + b.h;
          changed = true;
        }
      }
    }
  }

  function enterResizeMode(widget) {
    if (moveMode) exitMoveMode();
    if (resizeMode) exitResizeMode();
    if (!widget) widget = document.querySelector('.widget-extension:not([style*="display: none"])');
    if (!widget) return;
    resizeMode = true;
    document.body.classList.add('resize-mode');
    freezeAllPositions();
    widget.classList.add('widget-resizing');

    var bar = document.createElement('div');
    bar.id = 'mode-indicator-bar';
    bar.className = 'mode-indicator';
    bar.innerHTML =
      '<span>RESIZE \u2014 Drag edges or corners</span>' +
      '<button class="mode-exit-btn" id="mode-toggle-btn">Move \u2194</button>' +
      '<button class="mode-exit-btn" id="mode-exit-btn">Exit \u2715</button>';
    document.body.prepend(bar);
    document.getElementById('mode-exit-btn').addEventListener('click', exitResizeMode);
    document.getElementById('mode-toggle-btn').addEventListener('click', function () {
      exitResizeMode();
      enterMoveMode();
    });

    var isDragging = false;
    var dragEdges = {};
    var dragStartCol, dragStartRow, dragStartW, dragStartH;
    var EDGE_GAP = 10;
    var ROW_H = 93;

    function getGridColRow(mx, my, gridRect, colW) {
      return {
        col: Math.max(1, Math.min(12, Math.round((mx - gridRect.left) / colW) + 1)),
        row: Math.max(1, Math.min(100, Math.round((my - gridRect.top) / ROW_H) + 1))
      };
    }

    function onHover(e) {
      if (isDragging) return;
      var target = document.querySelector('.widget-resizing');
      if (!target) return;
      var edges = detectEdges(target, e.clientX, e.clientY);
      var cursor = cursorForEdges(edges);
      document.body.style.cursor = cursor || '';
    }

    function onDown(e) {
      if (e.button !== 0 || isDragging) return;
      var target = document.querySelector('.widget-resizing');
      if (!target) return;

      var clicked = e.target.closest('.widget-extension');
      if (clicked && clicked !== target) {
        exitResizeMode();
        enterResizeMode(clicked);
        return;
      }

      var edges = detectEdges(target, e.clientX, e.clientY);
      if (!edges.top && !edges.bottom && !edges.left && !edges.right) return;

      e.preventDefault();
      isDragging = true;
      dragEdges = edges;
      var info = getWidgetGridInfo(target);
      if (info) {
        dragStartCol = info.col; dragStartRow = info.row;
        dragStartW = info.w; dragStartH = info.h;
      }

      document.addEventListener('mousemove', onDrag, true);
      document.addEventListener('mouseup', onUp, true);
    }

    function onUp() {
      isDragging = false;
      document.removeEventListener('mousemove', onDrag, true);
      document.removeEventListener('mouseup', onUp, true);
      if (resizeTarget) saveAllLayouts();
    }

    document.addEventListener('mousemove', onHover);
    document.addEventListener('mousedown', onDown);
    document._resizeCleanup = function () {
      document.removeEventListener('mousemove', onHover);
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('mousemove', onDrag, true);
      document.removeEventListener('mouseup', onUp, true);
      document.body.style.cursor = '';
    };
  }

  function exitResizeMode() {
    if (!resizeMode) return;
    resizeMode = false;
    document.body.classList.remove('resize-mode');
    if (document._resizeCleanup) { document._resizeCleanup(); document._resizeCleanup = null; }
    var bar = document.getElementById('mode-indicator-bar');
    if (bar) bar.remove();
    document.querySelectorAll('.widget-resizing').forEach(function (el) { return el.classList.remove('widget-resizing'); });
    document.body.style.cursor = '';
    resizeTarget = null;
  }

  // ----- init -----
  function init() {
    getOrCreateCtxMenu();

    document.addEventListener('contextmenu', function (e) {
      if (e.target.closest('#mode-indicator-bar')) { closeCtxMenu(); return; }
      const widget = e.target.closest('.widget');
      e.preventDefault();
      e.stopPropagation();
      if (widget) {
        openCtxMenu(e, widget);
      } else {
        openEmptyCtxMenu(e);
      }
    });

    document.addEventListener('click', function (e) {
      if (!e.target.closest('#ctx-menu')) closeCtxMenu();
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        closeCtxMenu();
        exitMoveMode();
        exitResizeMode();
      }
    });

    // Load persisted state from server
    loadState().then(function () {
      _stateLoaded = true;
      if (document.querySelector('.widget')) {
        applyHiddenState();
        applySavedLayouts();
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  function applyWidgetState() {
    if (_stateLoaded) {
      applyHiddenState();
      applySavedLayouts();
    } else {
      var check = setInterval(function () {
        if (_stateLoaded) {
          clearInterval(check);
          applyHiddenState();
          applySavedLayouts();
        }
      }, 50);
    }
  }

  window.__widgetControl = {
    enterMoveMode: enterMoveMode,
    exitMoveMode: exitMoveMode,
    enterResizeMode: enterResizeMode,
    exitResizeMode: exitResizeMode,
    applyWidgetState: applyWidgetState
  };

})();
