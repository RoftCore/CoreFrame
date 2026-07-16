(function () {
  'use strict';

  var s = window.__wc;

  //  hide / show 

  s.getHidden = function () {
    var sw = s.sceneWidgets();
    var h = {};
    for (var id in sw) {
      if (sw[id] && sw[id].hidden && window.extensionsData && window.extensionsData[id]) h[id] = true;
    }
    document.querySelectorAll('.widget-extension').forEach(function (w) {
      var extId = w.dataset.extId;
      if (extId && !sw[extId] && window.extensionsData && window.extensionsData[extId]) h[extId] = true;
    });
    return h;
  };

  s.hideWidget = function (widget) {
    const extId = widget.dataset.extId;
    if (!extId || !s.currentScene()) return;
    var sw = s.currentScene().widgets;
    var gs = s.getExtGrid(extId);
    sw[extId] = sw[extId] || { col: 1, row: 1, w: gs.w || 2, h: gs.h || 2 };
    sw[extId].hidden = true;
    s.persistScenes();
    widget.style.display = 'none';
  };

  s.showHiddenPanel = function () {
    const panel = document.getElementById('result-panel');
    const overlay = document.getElementById('overlay');
    const title = document.getElementById('result-panel-title');
    const body = document.getElementById('result-panel-body');
    title.textContent = 'Hidden Widgets';

    const hidden = s.getHidden();
    const keys = Object.keys(hidden);
    if (keys.length === 0) {
      body.innerHTML = '<div style="padding:20px;color:var(--text-muted);font-family:var(--font-mono);font-size:12px;">No hidden widgets</div>';
    } else {
      let html = '<div style="font-family:var(--font-mono);">';
      keys.forEach(function (extId) {
        const name = (window.extensionsData && window.extensionsData[extId] && window.extensionsData[extId].name) || extId;
        html += '<div class="ctx-hidden-item" data-ext-id="' + extId + '">' +
          '<span>' + escapeHtml(name) + '</span>' +
          '<span class="ctx-show-action">Show</span>' +
        '</div>';
      });
      html += '</div>';
      body.innerHTML = html;
      body.querySelectorAll('.ctx-hidden-item').forEach(function (el) {
        el.addEventListener('click', function () {
          if (!s.unhideWidget(el.dataset.extId)) return;
          el.remove();
          if (body.querySelectorAll('.ctx-hidden-item').length === 0) {
            body.innerHTML = '<div style="padding:20px;color:var(--text-muted);font-family:var(--font-mono);font-size:12px;">No hidden widgets</div>';
          }
          if (Object.keys(s.getHidden()).length === 0) {
            s.closeCtxMenu();
          }
        });
      });
    }

    panel.classList.add('open');
    overlay.classList.add('open');
  };

  s.unhideWidget = function (extId) {
    if (!s.currentScene()) return false;
    var sw = s.currentScene().widgets;
    var gs = s.getExtGrid(extId);
    var w = gs.w || 2, h = gs.h || 2;
    if (sw[extId]) {
      w = sw[extId].w || w;
      h = sw[extId].h || h;
    }
    var spot = s.findFreeSpot(w, h);
    if (!spot) {
      s.showToast('No space for this widget');
      return false;
    }
    sw[extId] = { col: spot.col, row: spot.row, w: spot.w, h: spot.h, hidden: false };
    s.persistScenes();
    var wEl = document.querySelector('.widget-extension.ext-' + extId);
    if (wEl) {
      wEl.style.display = '';
      wEl.style.gridColumn = spot.col + ' / span ' + spot.w;
      wEl.style.gridRow = spot.row + ' / span ' + spot.h;
      s.applyStyleToWidget(extId);
    }
    if (spot.w !== w || spot.h !== h) {
      s.showToast('Resized to fit: ' + spot.w + 'x' + spot.h);
    }
    return true;
  };

  s.applyHiddenState = function () {
    var sw = s.sceneWidgets();
    document.querySelectorAll('.widget-extension').forEach(function (w) {
      var extId = w.dataset.extId;
      if (sw[extId]) {
        w.style.display = sw[extId].hidden ? 'none' : '';
      } else {
        w.style.display = 'none';
      }
    });
  };

  //  layout

  s.getLayout = function () {
    var sw = s.sceneWidgets();
    var l = {};
    for (var id in sw) {
      if (sw[id]) l[id] = { col: sw[id].col, row: sw[id].row, w: sw[id].w, h: sw[id].h };
    }
    return l;
  };

  s.saveWidgetLayout = function (extId, col, row, wSpan, hSpan) {
    if (!extId || !s.currentScene()) return;
    s.currentScene().widgets[extId] = s.currentScene().widgets[extId] || {};
    s.currentScene().widgets[extId].col = Math.max(1, col);
    s.currentScene().widgets[extId].row = Math.max(1, row);
    s.currentScene().widgets[extId].w = Math.max(1, wSpan);
    s.currentScene().widgets[extId].h = Math.max(1, hSpan);
    s.currentScene().widgets[extId].hidden = s.currentScene().widgets[extId].hidden || false;
    s.persistScenes();
  };

  s.saveAllLayouts = function () {
    if (!s.currentScene()) return;
    var sw = {};
    var maxCols = s.sceneCols();
    var sc = s.currentScene();
    var maxRows = (sc && sc.rows) || 6;
    document.querySelectorAll('.widget-extension').forEach(function (w) {
      if (w.style.display === 'none') return;
      var gc = (w.style.gridColumn || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
      var gr = (w.style.gridRow || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
      if (gc && gr && w.dataset.extId) {
        var col = Math.max(1, parseInt(gc[1],10));
        var row = Math.max(1, parseInt(gr[1],10));
        var wSpan = Math.max(1, Math.min(parseInt(gc[2],10), maxCols - col + 1));
        var hSpan = Math.max(1, Math.min(parseInt(gr[2],10), maxRows - row + 1));
        sw[w.dataset.extId] = {
          col: col, row: row,
          w: wSpan, h: hSpan,
          hidden: false
        };
      }
    });
    var old = s.currentScene().widgets;
    for (var id in sw) {
      if (old[id] && old[id].hidden) sw[id].hidden = true;
    }
    s.currentScene().widgets = sw;
    s.persistScenes();
  };

  s.applySavedLayouts = function () {
    var cols = s.sceneCols();
    var sc = s.currentScene();
    var grid = document.querySelector('.widget-grid');
    if (grid) {
      grid.style.gridTemplateColumns = 'repeat(' + cols + ', 1fr)';
      grid.style.gridTemplateRows = 'repeat(' + (sc.rows || 6) + ', 1fr)';
    }
    var sw = s.sceneWidgets();
    for (var extId in sw) {
      if (!sw.hasOwnProperty(extId)) continue;
      var pos = sw[extId];
      var clampedCol = Math.max(1, Math.min(pos.col || 1, cols));
      var clampedW = Math.min(pos.w || 2, cols - clampedCol + 1);
      var w = document.querySelector('.widget-extension.ext-' + extId);
      if (w) {
        w.style.minHeight = '';
        w.style.maxHeight = '';
        w.style.gridColumn = clampedCol + ' / span ' + clampedW;
        var clampedRow = Math.max(1, Math.min(pos.row || 1, (sc.rows || 6)));
        var clampedH = Math.min(pos.h || 2, (sc.rows || 6) - clampedRow + 1);
        w.style.gridRow = clampedRow + ' / span ' + clampedH;
      }
    }
  };

  //  collision helpers 

  function parseGridPos(val) {
    if (!val) return null;
    var m = val.match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
    if (m) return { col: parseInt(m[1], 10), span: parseInt(m[2], 10) };
    m = val.match(/^(\d+)\s*\/\s+(\d+)$/);
    if (m) return { col: parseInt(m[1], 10), span: parseInt(m[2], 10) - parseInt(m[1], 10) };
    return null;
  }

  s.findFreeSpot = function (w, h) {
    var cells = {};
    var widgets = document.querySelectorAll('.widget-extension');
    for (const el of widgets) {
      if (el.style.display === 'none' || el.dataset.overlayable === 'true') continue;
      var cs = getComputedStyle(el);
      var gc = parseGridPos(cs.gridColumn || '');
      var gr = parseGridPos(cs.gridRow || '');
      if (!gc || !gr) continue;
      for (var cc = gc.col; cc < gc.col + gc.span; cc++)
        for (var rr = gr.col; rr < gr.col + gr.span; rr++)
          cells[cc + ',' + rr] = true;
    }
    var grid = document.querySelector('.widget-grid');
    var visibleRows = 10;
    var sc = s.currentScene();
    if (sc && sc.rows) {
      visibleRows = sc.rows;
    } else if (grid) {
      var mainEl = document.getElementById('main');
      var pitch = getGridRowPitch(grid);
      var availH = mainEl ? mainEl.clientHeight - 16 : 600;
      var gap = 8;
      visibleRows = Math.ceil((availH + gap) / pitch) || 4;
    }
    for (var w2 = w; w2 >= 1; w2--) {
      for (var h2 = h; h2 >= 1; h2--) {
        for (var row = 1; row <= visibleRows - h2 + 1; row++) {
          for (var col = 1; col <= s.sceneCols() - w2 + 1; col++) {
            var free = true;
            for (var cc = col; cc < col + w2 && free; cc++)
              for (var rr = row; rr < row + h2 && free; rr++)
                if (cells[cc + ',' + rr]) free = false;
            if (free) return { col: col, row: row, w: w2, h: h2 };
          }
        }
      }
    }
    return null;
  };

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
    for (const el of widgets) {
      if (el.dataset.extId === extId || el.dataset.overlayable === 'true' || el.style.display === 'none') continue;
      const gc = (el.style.gridColumn || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
      const gr = (el.style.gridRow || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
      if (!gc || !gr) continue;
      const other = getOccupiedCells(parseInt(gc[1],10), parseInt(gr[1],10), parseInt(gc[2],10), parseInt(gr[2],10));
      for (const cell of target)
        if (other.indexOf(cell) !== -1) return true;
    }
    return false;
  }

  function getGridRowPitch(grid) {
    var cs = window.getComputedStyle(grid);
    var gap = parseFloat(cs.rowGap || cs.gap) || 8;
    var tracks = (cs.gridTemplateRows || '').split(' ').filter(Boolean);
    if (tracks.length > 0) return parseFloat(tracks[0]) + gap;
    return parseFloat(cs.gridAutoRows) + gap || 93;
  }

  function pixelToRow(grid, y) {
    var cs = window.getComputedStyle(grid);
    var gap = parseFloat(cs.rowGap || cs.gap) || 8;
    var tracks = (cs.gridTemplateRows || '').split(' ').filter(Boolean);
    if (tracks.length === 0) return Math.max(1, Math.round(y / 100));
    var pos = 0;
    for (var r = 0; r < tracks.length; r++) {
      var h = parseFloat(tracks[r]);
      if (y < pos + h) return r + 1;
      pos += h + gap;
    }
    return tracks.length + 1;
  }

  function gridPosFromPixel(el, grid, maxCols, maxRows) {
    var gridRect = grid.getBoundingClientRect();
    var elRect = el.getBoundingClientRect();
    var colW = gridRect.width / maxCols;
    var rowH = gridRect.height / maxRows;
    return {
      col: Math.max(1, Math.round((elRect.left - gridRect.left) / colW) + 1),
      row: Math.max(1, Math.round((elRect.top - gridRect.top) / rowH) + 1)
    };
  }

  function drawGridOverlay(grid) {
    var existing = grid.querySelector('.grid-overlay');
    if (existing) existing.remove();
    var overlay = document.createElement('div');
    overlay.className = 'grid-overlay';
    var cs = window.getComputedStyle(grid);
    var gap = parseFloat(cs.rowGap || cs.gap) || 8;
    var html = '';
    var rows = (cs.gridTemplateRows || '').split(' ').filter(Boolean);
    var rowPos = 0;
    for (var i = 0; i < rows.length - 1; i++) {
      rowPos += parseFloat(rows[i]) + gap / 2;
      html += '<div style="position:absolute;left:0;right:0;top:' + rowPos + 'px;height:1px;background:rgba(0,212,255,0.15);"></div>';
      rowPos += gap / 2;
    }
    var cols = (cs.gridTemplateColumns || '').split(' ').filter(Boolean);
    var colPos = 0;
    for (var j = 0; j < cols.length - 1; j++) {
      colPos += parseFloat(cols[j]) + gap / 2;
      html += '<div style="position:absolute;top:0;bottom:0;left:' + colPos + 'px;width:1px;background:rgba(0,212,255,0.15);"></div>';
      colPos += gap / 2;
    }
    overlay.innerHTML = html;
    grid.appendChild(overlay);
  }

  function removeGridOverlay(grid) {
    var el = grid.querySelector('.grid-overlay');
    if (el) el.remove();
  }

  function redrawOverlay() {
    if (!s.moveMode && !s.resizeMode) return;
    var grid = document.querySelector('.widget-grid');
    if (grid) drawGridOverlay(grid);
  }

  function freezeAllPositions() {
    var grid = document.querySelector('.widget-grid');
    if (!grid) return;
    var maxCols = s.sceneCols();
    var sc = s.currentScene();
    var maxRows = (sc && sc.rows) || 6;

    var entries = [];
    document.querySelectorAll('.widget-extension').forEach(function (w) {
      if (w.style.display === 'none') return;
      var cs = window.getComputedStyle(w);
      var gc = w.style.gridColumn;
      var gr = w.style.gridRow;
      var needsFreeze = /^span\s+\d+$/.test(gc);

      var col, row;
      var colRaw = parseInt(cs.gridColumnStart, 10);
      var rowRaw = parseInt(cs.gridRowStart, 10);
      if (isNaN(colRaw) || colRaw < 1 || isNaN(rowRaw) || rowRaw < 1) {
        var px = gridPosFromPixel(w, grid, maxCols, maxRows);
        col = px.col;
        row = px.row;
      } else {
        col = colRaw;
        row = rowRaw;
      }

      var spanW = parseInt((gc.match(/span\s+(\d+)/) || ['', '2'])[1], 10);
      var spanH = parseInt((gr.match(/span\s+(\d+)/) || ['', '2'])[1], 10);
      entries.push({ el: w, needsFreeze: needsFreeze, col: col, row: row, w: spanW, h: spanH });
    });

    entries.forEach(function (e) {
      e.el.style.minHeight = '';
      e.el.style.maxHeight = '';
      if (!e.needsFreeze) return;
      var clampedCol = Math.min(e.col, maxCols);
      var clampedW = Math.min(e.w, maxCols - clampedCol + 1);
      var clampedRow = Math.min(e.row, maxRows);
      var clampedH = Math.min(e.h, maxRows - clampedRow + 1);
      if (clampedCol < 1) clampedCol = 1;
      if (clampedRow < 1) clampedRow = 1;
      e.el.style.gridColumn = clampedCol + ' / span ' + clampedW;
      e.el.style.gridRow = clampedRow + ' / span ' + clampedH;
    });
  }

  //  move mode 

  s.enterMoveMode = function () {
    if (s.resizeMode) s.exitResizeMode();
    if (s.moveMode) return;
    s.moveMode = true;
    freezeAllPositions();
    document.body.classList.add('move-mode');
    var grid = document.querySelector('.widget-grid');
    if (grid) drawGridOverlay(grid);
    window.addEventListener('resize', redrawOverlay);

    const bar = document.createElement('div');
    bar.id = 'mode-indicator-bar';
    bar.className = 'mode-indicator';
    bar.innerHTML =
      '<span>MOVE \u2014 Drag any widget</span>' +
      '<button class="mode-exit-btn" id="mode-toggle-btn">Resize \u2194</button>' +
      '<button class="mode-exit-btn" id="mode-exit-btn">Exit \u2715</button>';
    document.body.prepend(bar);
    document.getElementById('mode-exit-btn').addEventListener('click', s.exitMoveMode);
    document.getElementById('mode-toggle-btn').addEventListener('click', function () {
      var target = dragEl || document.querySelector('.ctx-target') || s.resizeTarget;
      s.exitMoveMode();
      s.enterResizeMode(target);
    });

    let dragEl = null, startCol = 1, startRow = 1, wSpan = 2, hSpan = 2, gridRect = null, colWidth = 0;
    let overlayable = false;
    let _wasDragged = false;
    let offsetX = 0, offsetY = 0;

    function onDown(e) {
      if (!s.moveMode || e.button !== 0) return;
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
      colWidth = gridRect.width / s.sceneCols();

      const cs = getComputedStyle(widget);
      const gc = cs.gridColumn || widget.style.gridColumn || 'auto / span 2';
      const gr = cs.gridRow || widget.style.gridRow || 'auto / span 2';
      wSpan = parseInt((gc.match(/span\s+(\d+)/) || [,'2'])[1], 10);
      hSpan = parseInt((gr.match(/span\s+(\d+)/) || [,'2'])[1], 10);

      const wr = widget.getBoundingClientRect();
      startCol = Math.max(1, Math.round((wr.left - gridRect.left) / colWidth) + 1);

      var sc = s.currentScene();
      var maxRow = (sc && sc.rows) || 6;
      startRow = Math.max(1, Math.min(maxRow - hSpan + 1, pixelToRow(grid, wr.top - gridRect.top)));

      offsetX = (e.clientX - wr.left) / colWidth;
      offsetY = e.clientY - wr.top;

      widget.style.gridColumn = startCol + ' / span ' + wSpan;
      widget.style.gridRow = startRow + ' / span ' + hSpan;

      document.addEventListener('mousemove', onMove, true);
      document.addEventListener('mouseup', onUp, true);
    }

    function onMove(e) {
      if (!dragEl || !gridRect) return;
      _wasDragged = true;
      var mainEl = document.getElementById('main');
      var grid = document.querySelector('.widget-grid');
      if (!grid) return;
      gridRect = grid.getBoundingClientRect();
      colWidth = gridRect.width / s.sceneCols();
      var sc = s.currentScene();
      var maxCol = (sc && sc.cols) || 12;
      let col = Math.round((e.clientX - gridRect.left) / colWidth - offsetX) + 1;
      let row = pixelToRow(grid, e.clientY - gridRect.top - offsetY);
      var maxRow = (sc && sc.rows) || 6;
      col = Math.max(1, Math.min(maxCol - wSpan + 1, col));
      row = Math.max(1, Math.min(maxRow - hSpan + 1, row));

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
              s.saveWidgetLayout(extId, c, r, w, h);
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
  };

  s.exitMoveMode = function () {
    if (!s.moveMode) return;
    s.moveMode = false;
    var grid = document.querySelector('.widget-grid');
    if (grid) { grid.style.minHeight = ''; grid.style.position = ''; removeGridOverlay(grid); }
    window.removeEventListener('resize', redrawOverlay);
    document.body.classList.remove('move-mode');
    if (document._moveCleanup) { document._moveCleanup(); document._moveCleanup = null; }
    const bar = document.getElementById('mode-indicator-bar');
    if (bar) bar.remove();
    document.querySelectorAll('.widget-moving').forEach(function (el) { return el.classList.remove('widget-moving'); });
  };

  //  resize mode 

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

  s.enterResizeMode = function (widget) {
    if (s.moveMode) s.exitMoveMode();
    if (s.resizeMode) s.exitResizeMode();
    if (!widget) widget = document.querySelector('.widget-extension:not([style*="display: none"])');
    if (!widget) return;
    s.resizeMode = true;
    freezeAllPositions();
    document.body.classList.add('resize-mode');
    var grid = document.querySelector('.widget-grid');
    if (grid) drawGridOverlay(grid);
    window.addEventListener('resize', redrawOverlay);
    s.resizeTarget = widget;
    widget.classList.add('widget-resizing');

    var bar = document.createElement('div');
    bar.id = 'mode-indicator-bar';
    bar.className = 'mode-indicator';
    bar.innerHTML =
      '<span>RESIZE \u2014 Drag edges or corners</span>' +
      '<button class="mode-exit-btn" id="mode-toggle-btn">Move \u2194</button>' +
      '<button class="mode-exit-btn" id="mode-exit-btn">Exit \u2715</button>';
    document.body.prepend(bar);
    document.getElementById('mode-exit-btn').addEventListener('click', function () { s.resizeTarget = null; s.exitResizeMode(); });
    document.getElementById('mode-toggle-btn').addEventListener('click', function () {
      s.exitResizeMode();
      s.enterMoveMode();
    });

    var isDragging = false;
    var dragEdges = {};
    var dragStartCol, dragStartRow, dragStartW, dragStartH;

    function getGridColRow(mx, my, g, colW) {
      var gridRect = g.getBoundingClientRect();
      return {
        col: Math.max(1, Math.round((mx - gridRect.left) / colW) + 1),
        row: Math.max(1, pixelToRow(g, my - gridRect.top))
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
        s.exitResizeMode();
        s.enterResizeMode(clicked);
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

    function onDrag(e) {
      if (!isDragging) return;
      var target = document.querySelector('.widget-resizing');
      if (!target) return;
      var grid = target.closest('.widget-grid');
      if (!grid) return;
      var colW = grid.getBoundingClientRect().width / s.sceneCols();
      var pos = getGridColRow(e.clientX, e.clientY, grid, colW);
      var sc = s.currentScene();
      var maxRow = (sc && sc.rows) || 6;
      var mainEl = document.getElementById('main');
      var mainRect = mainEl.getBoundingClientRect();
      if (e.clientY > mainRect.bottom - 24 && pos.row > maxRow) {
        mainEl.scrollTop += 12;
        var grid2 = target.closest('.widget-grid');
        if (grid2) {
          colW = grid2.getBoundingClientRect().width / s.sceneCols();
          pos = getGridColRow(e.clientX, e.clientY, grid2, colW);
        }
      } else if (e.clientY < mainRect.top + 24 && pos.row < 1) {
        mainEl.scrollTop -= 12;
        var grid3 = target.closest('.widget-grid');
        if (grid3) {
          colW = grid3.getBoundingClientRect().width / s.sceneCols();
          pos = getGridColRow(e.clientX, e.clientY, grid3, colW);
        }
      }
      var newCol = dragStartCol, newRow = dragStartRow;
      var newW = dragStartW, newH = dragStartH;

      if (dragEdges.right) {
        newW = Math.max(1, Math.min(s.sceneCols() - newCol + 1, pos.col - newCol));
      }
      if (dragEdges.left) {
        var maxCol = dragStartCol + dragStartW - 1;
        var delta = dragStartCol - pos.col;
        newCol = Math.max(1, Math.min(maxCol, dragStartCol - delta));
        newW = Math.max(1, Math.min(s.sceneCols() - newCol + 1, dragStartW + delta));
      }
      if (dragEdges.bottom) {
        newH = Math.max(1, Math.min(maxRow - newRow + 1, pos.row - newRow));
      }
      if (dragEdges.top) {
        var maxRowPos = dragStartRow + dragStartH - 1;
        var delta = dragStartRow - pos.row;
        newRow = Math.max(1, Math.min(maxRowPos, dragStartRow - delta));
        newH = Math.max(1, Math.min(maxRow - newRow + 1, dragStartH + delta));
      }

      var overlayable = target.dataset.overlayable === 'true';
      if (!overlayable && hasCollisionWithNonOverlayable(target.dataset.extId, newCol, newRow, newW, newH)) {
        target.classList.add('widget-collision');
        return;
      }
      target.classList.remove('widget-collision');
      target.style.gridColumn = newCol + ' / span ' + newW;
      target.style.gridRow = newRow + ' / span ' + newH;
    }

    function onUp() {
      isDragging = false;
      document.removeEventListener('mousemove', onDrag, true);
      document.removeEventListener('mouseup', onUp, true);
      if (s.resizeTarget) {
        s.resizeTarget.classList.remove('widget-collision');
        s.saveAllLayouts();
      }
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
  };

  s.exitResizeMode = function () {
    if (!s.resizeMode) return;
    s.resizeMode = false;
    document.body.classList.remove('resize-mode');
    removeGridOverlay(document.querySelector('.widget-grid'));
    window.removeEventListener('resize', redrawOverlay);
    if (document._resizeCleanup) { document._resizeCleanup(); document._resizeCleanup = null; }
    var bar = document.getElementById('mode-indicator-bar');
    if (bar) bar.remove();
    document.querySelectorAll('.widget-resizing').forEach(function (el) { return el.classList.remove('widget-resizing'); });
    document.body.style.cursor = '';
  };
})();
