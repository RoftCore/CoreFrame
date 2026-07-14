(function () {
  'use strict';

  // ----- scene state -----
  var _scenes = {};
  var _activeScene = null;
  var _stateLoaded = false;
  var _savePending = false;

  function currentScene() {
    return _scenes[_activeScene] || null;
  }

  function sceneWidgets() {
    var s = currentScene();
    return s ? s.widgets : {};
  }

  function loadState() {
    return apiFetch('/api/scenes').then(function (data) {
      if (data && !data.error) {
        _scenes = data.scenes || {};
        _activeScene = data.active || Object.keys(_scenes)[0] || null;
        _stateLoaded = true;
        renderSceneBar();
      }
    });
  }

  function persistScenes() {
    return apiFetch('/api/widget-state', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scenes: _scenes, activeScene: _activeScene })
    });
  }

  function getHidden() {
    var sw = sceneWidgets();
    var h = {};
    for (var id in sw) {
      if (sw[id] && sw[id].hidden) h[id] = true;
    }
    document.querySelectorAll('.widget-extension').forEach(function (w) {
      var extId = w.dataset.extId;
      if (extId && !sw[extId]) h[extId] = true;
    });
    return h;
  }

  function getLayout() {
    var sw = sceneWidgets();
    var l = {};
    for (var id in sw) {
      if (sw[id]) l[id] = { col: sw[id].col, row: sw[id].row, w: sw[id].w, h: sw[id].h };
    }
    return l;
  }

  function saveWidgetLayout(extId, col, row, wSpan, hSpan) {
    if (!extId || !currentScene()) return;
    currentScene().widgets[extId] = currentScene().widgets[extId] || {};
    currentScene().widgets[extId].col = Math.max(1, col);
    currentScene().widgets[extId].row = Math.max(1, row);
    currentScene().widgets[extId].w = Math.max(1, wSpan);
    currentScene().widgets[extId].h = Math.max(1, hSpan);
    currentScene().widgets[extId].hidden = currentScene().widgets[extId].hidden || false;
    persistScenes();
  }

  function saveAllLayouts() {
    if (!currentScene()) return;
    var sw = {};
    var maxCols = sceneCols();
    var s = currentScene();
    var maxRows = (s && s.rows) || 6;
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
    // preserve hidden state
    var old = currentScene().widgets;
    for (var id in sw) {
      if (old[id] && old[id].hidden) sw[id].hidden = true;
    }
    currentScene().widgets = sw;
    persistScenes();
  }

  function sceneCols() {
    return (_scenes[_activeScene] && _scenes[_activeScene].cols) || 12;
  }

  function applySavedLayouts() {
    var cols = sceneCols();
    var s = currentScene();
    var grid = document.querySelector('.widget-grid');
    if (grid) {
      grid.style.gridTemplateColumns = 'repeat(' + cols + ', 1fr)';
      grid.style.gridTemplateRows = 'repeat(' + (s.rows || 6) + ', 1fr)';
    }
    var sw = sceneWidgets();
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
        var clampedRow = Math.max(1, Math.min(pos.row || 1, (s.rows || 6)));
        var clampedH = Math.min(pos.h || 2, (s.rows || 6) - clampedRow + 1);
        w.style.gridRow = clampedRow + ' / span ' + clampedH;
      }
    }
  }

  function applyHiddenState() {
    var sw = sceneWidgets();
    document.querySelectorAll('.widget-extension').forEach(function (w) {
      var extId = w.dataset.extId;
      if (sw[extId]) {
        w.style.display = sw[extId].hidden ? 'none' : '';
      } else {
        w.style.display = 'none';
      }
    });
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
      '<div class="ctx-menu-item" data-action="style" id="ctx-style-btn" style="display:none">\u{265B} Change Style</div>' +
      '<div class="ctx-menu-separator"></div>' +
      '<div class="ctx-menu-item" data-action="show" id="ctx-show-btn" style="display:none">\u{1F441}  Show hidden widgets...</div>' +
      '<div class="ctx-menu-item" data-action="install" id="ctx-install-btn" style="display:none">\u{2795}  Install extension...</div>';
    document.body.appendChild(m);

    m.addEventListener('click', function (e) {
      const item = e.target.closest('.ctx-menu-item');
      if (!item) return;
      const action = item.dataset.action;
      const target = document.querySelector('.ctx-target');
      if (action === 'show') {
        showHiddenPanel();
      } else if (action === 'install') {
        var btn = document.getElementById('btn-install');
        if (btn) btn.click();
      } else if (action === 'style') {
        showStylePicker(target);
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
    document.getElementById('ctx-install-btn').style.display = 'none';

    var extData = window.extensionsData && window.extensionsData[widget.dataset.extId];
    var hasStyles = false;
    if (extData && extData.widgets) {
      for (var wi = 0; wi < extData.widgets.length; wi++) {
        var st = extData.widgets[wi].styles;
        if (st && typeof st === 'object' && !Array.isArray(st) && Object.keys(st).length > 0) {
          hasStyles = true;
          break;
        }
      }
    }
    document.getElementById('ctx-style-btn').style.display = hasStyles ? 'flex' : 'none';

    menu.style.left = Math.min(e.clientX, window.innerWidth - 200) + 'px';
    menu.style.top = Math.min(e.clientY, window.innerHeight - 160) + 'px';
    menu.classList.add('visible');
  }

  function openEmptyCtxMenu(e) {
    const hidden = getHidden();
    const hasHidden = Object.keys(hidden).length > 0;
    closeCtxMenu();
    document.querySelectorAll('.ctx-target').forEach(function (el) { return el.classList.remove('ctx-target'); });
    const menu = getOrCreateCtxMenu();
    menu.querySelectorAll('[data-action="hide"],[data-action="move"],[data-action="resize"],[data-action="style"]').forEach(function (el) { return el.style.display = 'none'; });
    menu.querySelector('.ctx-menu-separator').style.display = 'none';
    document.getElementById('ctx-show-btn').style.display = hasHidden ? 'flex' : 'none';
    document.getElementById('ctx-install-btn').style.display = hasHidden ? 'none' : 'flex';
    menu.style.left = Math.min(e.clientX, window.innerWidth - 200) + 'px';
    menu.style.top = Math.min(e.clientY, window.innerHeight - 100) + 'px';
    menu.classList.add('visible');
  }

  function closeCtxMenu() {
    const m = document.getElementById('ctx-menu');
    if (m) m.classList.remove('visible');
    document.querySelectorAll('.ctx-target').forEach(function (el) { return el.classList.remove('ctx-target'); });
  }

  // ----- style picker -----
  function showStylePicker(widget) {
    var extId = widget.dataset.extId;
    var extData = window.extensionsData && window.extensionsData[extId];
    if (!extData) return;

    var styleDefs = {};
    for (var wi = 0; wi < (extData.widgets || []).length; wi++) {
      var st = extData.widgets[wi].styles;
      if (st && typeof st === 'object' && !Array.isArray(st)) {
        for (var name in st) {
          if (!styleDefs[name]) styleDefs[name] = st[name] || {};
        }
      }
    }
    var styleNames = Object.keys(styleDefs);
    if (styleNames.length === 0) return;

    var sw = sceneWidgets();
    var currentStyle = (sw[extId] && sw[extId].style) || 'default';

    var panel = document.getElementById('result-panel');
    var overlay = document.getElementById('overlay');
    var title = document.getElementById('result-panel-title');
    var body = document.getElementById('result-panel-body');
    title.textContent = 'Change Style - ' + (extData.name || extId);

    var html = '<div style="font-family:var(--font-mono);padding:4px 0;">';
    var defActive = currentStyle === 'default' ? ';border-color:var(--accent-cyan);background:rgba(0,212,255,0.15)' : '';
    html += '<div class="style-option" data-style="default" style="display:flex;align-items:center;gap:10px;padding:10px 12px;cursor:pointer;border:1px solid transparent;border-radius:var(--radius-sm);margin-bottom:4px' + defActive + '">' +
      '<div style="width:18px;height:18px;border-radius:50%;border:2px solid var(--border-light);background:var(--bg-widget);flex-shrink:0;"></div>' +
      '<div><div style="font-size:12px;color:var(--text-primary);">Default</div><div style="font-size:9px;color:var(--text-muted);">Default style</div></div>' +
      (currentStyle === 'default' ? '<span class="style-active-label" style="margin-left:auto;color:var(--accent-cyan);font-size:10px;">Active</span>' : '') +
      '</div>';
    styleNames.forEach(function(s) {
      var sd = styleDefs[s] || {};
      var label = sd.label || s.charAt(0).toUpperCase() + s.slice(1);
      var active = currentStyle === s ? ';border-color:var(--accent-cyan);background:rgba(0,212,255,0.15)' : '';
      html += '<div class="style-option" data-style="' + s + '" style="display:flex;align-items:center;gap:10px;padding:10px 12px;cursor:pointer;border:1px solid transparent;border-radius:var(--radius-sm);margin-bottom:4px' + active + '">' +
        '<div style="width:18px;height:18px;border-radius:50%;border:2px solid var(--border-light);flex-shrink:0;background:var(--bg-widget);"></div>' +
        '<div><div style="font-size:12px;color:var(--text-primary);">' + escapeHtml(label) + '</div><div style="font-size:9px;color:var(--text-muted);">' + escapeHtml(s) + '</div></div>' +
        (currentStyle === s ? '<span class="style-active-label" style="margin-left:auto;color:var(--accent-cyan);font-size:10px;">Active</span>' : '') +
        '</div>';
    });
    html += '</div>';
    body.innerHTML = html;

    body.querySelectorAll('.style-option').forEach(function(el) {
      el.addEventListener('click', function() {
        var styleName = el.dataset.style;
        changeWidgetStyle(extId, styleName);
        body.querySelectorAll('.style-option').forEach(function(opt) {
          opt.style.borderColor = 'transparent';
          opt.style.background = '';
          var oldLabel = opt.querySelector('.style-active-label');
          if (oldLabel) oldLabel.remove();
        });
        el.style.borderColor = 'var(--accent-cyan)';
        el.style.background = 'rgba(0,212,255,0.15)';
        var tag = document.createElement('span');
        tag.className = 'style-active-label';
        tag.style.cssText = 'margin-left:auto;color:var(--accent-cyan);font-size:10px;';
        tag.textContent = 'Active';
        el.appendChild(tag);
        if (typeof showToast !== 'undefined') showToast('Style changed to ' + label);
      });
    });

    panel.classList.add('open');
    overlay.classList.add('open');
  }

  function changeWidgetStyle(extId, styleName) {
    if (!extId || !currentScene()) return;
    currentScene().widgets[extId] = currentScene().widgets[extId] || {};
    currentScene().widgets[extId].style = styleName;
    persistScenes();
    applyStyleToWidget(extId);
  }

  function applyStyleToWidget(extId) {
    var sw = sceneWidgets();
    var w = document.querySelector('.widget-extension.ext-' + extId);
    if (!w || !sw[extId]) return;
    w.className = w.className.replace(/\bwidget-style-\S+/g, '').trim();
    var style = sw[extId].style;
    if (style && style !== 'default') {
      w.classList.add('widget-style-' + style);
    }
  }

  function applyWidgetStyles() {
    var sw = sceneWidgets();
    for (var extId in sw) {
      if (sw.hasOwnProperty(extId) && sw[extId].style) {
        applyStyleToWidget(extId);
      }
    }
  }

  // ----- hide / show -----
  function hideWidget(widget) {
    const extId = widget.dataset.extId;
    if (!extId || !currentScene()) return;
    var sw = currentScene().widgets;
    sw[extId] = sw[extId] || { col: 1, row: 1, w: 2, h: 2 };
    sw[extId].hidden = true;
    persistScenes();
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
          if (!unhideWidget(el.dataset.extId)) return;
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
    if (!currentScene()) return false;
    var sw = currentScene().widgets;
    var w = 2, h = 2;
    if (sw[extId]) {
      w = sw[extId].w || 2;
      h = sw[extId].h || 2;
    }
    var spot = findFreeSpot(w, h);
    if (!spot) {
      showToast('No space for this widget');
      return false;
    }
    sw[extId] = { col: spot.col, row: spot.row, w: spot.w, h: spot.h, hidden: false };
    persistScenes();
    var wEl = document.querySelector('.widget-extension.ext-' + extId);
    if (wEl) {
      wEl.style.display = '';
      wEl.style.gridColumn = spot.col + ' / span ' + spot.w;
      wEl.style.gridRow = spot.row + ' / span ' + spot.h;
      applyStyleToWidget(extId);
    }
    if (spot.w !== w || spot.h !== h) {
      showToast('Resized to fit: ' + spot.w + 'x' + spot.h);
    }
    return true;
  }

  function parseGridPos(val) {
    if (!val) return null;
    var m = val.match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
    if (m) return { col: parseInt(m[1], 10), span: parseInt(m[2], 10) };
    m = val.match(/^(\d+)\s*\/\s+(\d+)$/);
    if (m) return { col: parseInt(m[1], 10), span: parseInt(m[2], 10) - parseInt(m[1], 10) };
    return null;
  }

  function findFreeSpot(w, h) {
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
    var s = currentScene();
    if (s && s.rows) {
      visibleRows = s.rows;
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
          for (var col = 1; col <= sceneCols() - w2 + 1; col++) {
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
    document.getElementById('mode-exit-btn').addEventListener('click', exitMoveMode);
    document.getElementById('mode-toggle-btn').addEventListener('click', function () {
      var target = dragEl || document.querySelector('.ctx-target') || resizeTarget;
      exitMoveMode();
      enterResizeMode(target);
    });

    let dragEl = null, startCol = 1, startRow = 1, wSpan = 2, hSpan = 2, gridRect = null, colWidth = 0;
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
      colWidth = gridRect.width / sceneCols();

      const cs = getComputedStyle(widget);
      const gc = cs.gridColumn || widget.style.gridColumn || 'auto / span 2';
      const gr = cs.gridRow || widget.style.gridRow || 'auto / span 2';
      wSpan = parseInt((gc.match(/span\s+(\d+)/) || [,'2'])[1], 10);
      hSpan = parseInt((gr.match(/span\s+(\d+)/) || [,'2'])[1], 10);

      const wr = widget.getBoundingClientRect();
      startCol = Math.max(1, Math.round((wr.left - gridRect.left) / colWidth) + 1);

      var s = currentScene();
      var maxRow = (s && s.rows) || 6;
      startRow = Math.max(1, Math.min(maxRow - hSpan + 1, pixelToRow(grid, wr.top - gridRect.top)));

      offsetX = (e.clientX - wr.left) / colWidth;
      offsetY = e.clientY - wr.top; // pixel offset, decoupled from rowHeight

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
      colWidth = gridRect.width / sceneCols();
      var s = currentScene();
      var maxCol = (s && s.cols) || 12;
      let col = Math.round((e.clientX - gridRect.left) / colWidth - offsetX) + 1;
      let row = pixelToRow(grid, e.clientY - gridRect.top - offsetY);
      var maxRow = (s && s.rows) || 6;
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
    var grid = document.querySelector('.widget-grid');
    if (grid) { grid.style.minHeight = ''; grid.style.position = ''; removeGridOverlay(grid); }
    window.removeEventListener('resize', redrawOverlay);
    document.body.classList.remove('move-mode');
    if (document._moveCleanup) { document._moveCleanup(); document._moveCleanup = null; }
    const bar = document.getElementById('mode-indicator-bar');
    if (bar) bar.remove();
    document.querySelectorAll('.widget-moving').forEach(function (el) { return el.classList.remove('widget-moving'); });
  }

  function redrawOverlay() {
    if (!moveMode && !resizeMode) return;
    var grid = document.querySelector('.widget-grid');
    if (grid) drawGridOverlay(grid);
  }

  function drawGridOverlay(grid) {
    var existing = grid.querySelector('.grid-overlay');
    if (existing) existing.remove();
    var overlay = document.createElement('div');
    overlay.className = 'grid-overlay';
    var cs = window.getComputedStyle(grid);
    var gap = parseFloat(cs.rowGap || cs.gap) || 8;
    var html = '';
    // Horizontal lines (between rows)
    var rows = (cs.gridTemplateRows || '').split(' ').filter(Boolean);
    var rowPos = 0;
    for (var i = 0; i < rows.length - 1; i++) {
      rowPos += parseFloat(rows[i]) + gap / 2;
      html += '<div style="position:absolute;left:0;right:0;top:' + rowPos + 'px;height:1px;background:rgba(0,212,255,0.15);"></div>';
      rowPos += gap / 2;
    }
    // Vertical lines (between columns)
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

  function rowToPixel(grid, row) {
    var cs = window.getComputedStyle(grid);
    var gap = parseFloat(cs.rowGap || cs.gap) || 8;
    var tracks = (cs.gridTemplateRows || '').split(' ').filter(Boolean);
    var pos = 0;
    for (var r = 0; r < Math.min(row - 1, tracks.length); r++)
      pos += parseFloat(tracks[r]) + gap;
    return pos;
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

  // Freeze all widget positions so CSS Grid doesn't reflow others on resize/move
  function freezeAllPositions() {
    var grid = document.querySelector('.widget-grid');
    if (!grid) return;
    var maxCols = sceneCols();
    var s = currentScene();
    var maxRows = (s && s.rows) || 6;

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
    freezeAllPositions();
    document.body.classList.add('resize-mode');
    var grid = document.querySelector('.widget-grid');
    if (grid) drawGridOverlay(grid);
    window.addEventListener('resize', redrawOverlay);
    resizeTarget = widget;
    widget.classList.add('widget-resizing');

    var bar = document.createElement('div');
    bar.id = 'mode-indicator-bar';
    bar.className = 'mode-indicator';
    bar.innerHTML =
      '<span>RESIZE \u2014 Drag edges or corners</span>' +
      '<button class="mode-exit-btn" id="mode-toggle-btn">Move \u2194</button>' +
      '<button class="mode-exit-btn" id="mode-exit-btn">Exit \u2715</button>';
    document.body.prepend(bar);
    document.getElementById('mode-exit-btn').addEventListener('click', function () { resizeTarget = null; exitResizeMode(); });
    document.getElementById('mode-toggle-btn').addEventListener('click', function () {
      exitResizeMode();
      enterMoveMode();
    });

    var isDragging = false;
    var dragEdges = {};
    var dragStartCol, dragStartRow, dragStartW, dragStartH;
    var EDGE_GAP = 10;

    function getGridColRow(mx, my, grid, colW) {
      var gridRect = grid.getBoundingClientRect();
      return {
        col: Math.max(1, Math.round((mx - gridRect.left) / colW) + 1),
        row: Math.max(1, pixelToRow(grid, my - gridRect.top))
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

    function onDrag(e) {
      if (!isDragging) return;
      var target = document.querySelector('.widget-resizing');
      if (!target) return;
      var grid = target.closest('.widget-grid');
      if (!grid) return;
      var colW = grid.getBoundingClientRect().width / sceneCols();
      var pos = getGridColRow(e.clientX, e.clientY, grid, colW);
      var s = currentScene();
      var maxRow = (s && s.rows) || 6;
      // auto-scroll if widget exceeds visible rows
      var mainEl = document.getElementById('main');
      var mainRect = mainEl.getBoundingClientRect();
      if (e.clientY > mainRect.bottom - 24 && pos.row > maxRow) {
        mainEl.scrollTop += 12;
        var grid2 = target.closest('.widget-grid');
        if (grid2) {
          colW = grid2.getBoundingClientRect().width / sceneCols();
          pos = getGridColRow(e.clientX, e.clientY, grid2, colW);
        }
      } else if (e.clientY < mainRect.top + 24 && pos.row < 1) {
        mainEl.scrollTop -= 12;
        var grid3 = target.closest('.widget-grid');
        if (grid3) {
          colW = grid3.getBoundingClientRect().width / sceneCols();
          pos = getGridColRow(e.clientX, e.clientY, grid3, colW);
        }
      }
      var newCol = dragStartCol, newRow = dragStartRow;
      var newW = dragStartW, newH = dragStartH;

      if (dragEdges.right) {
        newW = Math.max(1, Math.min(sceneCols() - newCol + 1, pos.col - newCol));
      }
      if (dragEdges.left) {
        var maxCol = dragStartCol + dragStartW - 1;
        var delta = dragStartCol - pos.col;
        newCol = Math.max(1, Math.min(maxCol, dragStartCol - delta));
        newW = Math.max(1, Math.min(sceneCols() - newCol + 1, dragStartW + delta));
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
      if (resizeTarget) {
        resizeTarget.classList.remove('widget-collision');
        saveAllLayouts();
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
  }

  function exitResizeMode() {
    if (!resizeMode) return;
    resizeMode = false;
    document.body.classList.remove('resize-mode');
    removeGridOverlay(document.querySelector('.widget-grid'));
    window.removeEventListener('resize', redrawOverlay);
    if (document._resizeCleanup) { document._resizeCleanup(); document._resizeCleanup = null; }
    var bar = document.getElementById('mode-indicator-bar');
    if (bar) bar.remove();
    document.querySelectorAll('.widget-resizing').forEach(function (el) { return el.classList.remove('widget-resizing'); });
    document.body.style.cursor = '';
  }

  // ----- scene bar -----

  function openSceneCtxMenu(e, sid) {
    e.preventDefault();
    e.stopPropagation();
    closeCtxMenu();
    var menu = document.getElementById('scene-ctx-menu');
    if (!menu) {
      menu = document.createElement('div');
      menu.id = 'scene-ctx-menu';
      menu.className = 'ctx-menu';
      menu.innerHTML =
        '<div class="ctx-menu-item" data-action="icon">\u{1F4F7}  Change icon</div>' +
        '<div class="ctx-menu-separator"></div>' +
        '<div class="ctx-menu-item" data-action="delete" style="color:var(--accent-red)">\u{1F5D1}  Delete scene</div>';
      document.body.appendChild(menu);
      menu.addEventListener('click', function (e) {
        var item = e.target.closest('.ctx-menu-item');
        if (!item) return;
        var action = item.dataset.action;
        var sceneId = menu.dataset.sceneId;
        if (action === 'delete') {
          showDeleteConfirmation(sceneId);
        } else if (action === 'icon') {
          showIconPicker(sceneId);
        }
        closeSceneCtxMenu();
      });
    }
    menu.dataset.sceneId = sid;
    var delItem = menu.querySelector('[data-action="delete"]');
    if (delItem) delItem.style.display = (Object.keys(_scenes).length > 1 && sid !== 'default') ? '' : 'none';
    menu.style.left = Math.min(e.clientX, window.innerWidth - 200) + 'px';
    menu.style.top = Math.min(e.clientY, window.innerHeight - 100) + 'px';
    menu.classList.add('visible');
  }

  function closeSceneCtxMenu() {
    var menu = document.getElementById('scene-ctx-menu');
    if (menu) menu.classList.remove('visible');
  }

  function showDeleteConfirmation(sid) {
    if (sid === 'default') return;
    var panel = document.getElementById('result-panel');
    var overlay = document.getElementById('overlay');
    var title = document.getElementById('result-panel-title');
    var body = document.getElementById('result-panel-body');
    title.textContent = 'Delete scene';
    body.innerHTML =
      '<div style="font-family:var(--font-mono);padding:16px 0;text-align:center;font-size:13px;color:var(--text-primary)">' +
      'Are you sure you want to delete this scene?' +
      '<div style="margin-top:16px;display:flex;gap:8px;justify-content:center">' +
      '<button id="confirm-delete-yes" class="pkg-btn" style="background:var(--accent-red,#e74c3c);color:#fff">Delete</button>' +
      '<button id="confirm-delete-no" class="pkg-btn">Cancel</button>' +
      '</div></div>';
    panel.classList.add('open');
    overlay.classList.add('open');
    document.getElementById('confirm-delete-yes').onclick = function () {
      closeResultPanel();
      deleteScene(sid);
    };
    document.getElementById('confirm-delete-no').onclick = function () {
      closeResultPanel();
    };
  }

  function renderSceneBar() {
    var bar = document.getElementById('scene-bar');
    if (!bar) return;
    bar.innerHTML = '';
    var ids = Object.keys(_scenes);
    ids.forEach(function (sid) {
      var btn = document.createElement('button');
      btn.className = 'scene-btn' + (sid === _activeScene ? ' active' : '');
      btn.dataset.sceneId = sid;
      if (_scenes[sid].image) {
        var img = document.createElement('img');
        img.className = 'scene-btn-img';
        img.src = _scenes[sid].image;
        img.alt = '';
        btn.appendChild(img);
      } else if (typeof feather !== 'undefined' && feather.icons[_scenes[sid].label]) {
        var i = document.createElement('i');
        i.setAttribute('data-feather', _scenes[sid].label);
        i.setAttribute('width', '18');
        i.setAttribute('height', '18');
        btn.appendChild(i);
      } else {
        btn.textContent = _scenes[sid].label || '📄';
      }
      btn.title = _scenes[sid].name || sid;
      btn.draggable = true;
      btn.addEventListener('dragstart', function (e) { e.dataTransfer.setData('text/plain', sid); });
      btn.addEventListener('dragover', function (e) { e.preventDefault(); });
      btn.addEventListener('drop', function (e) {
        e.preventDefault();
        var from = e.dataTransfer.getData('text/plain');
        if (!from || from === sid) return;
        var ids = Object.keys(_scenes);
        var idxFrom = ids.indexOf(from);
        var idxTo = ids.indexOf(sid);
        if (idxFrom < 0 || idxTo < 0) return;
        ids.splice(idxFrom, 1);
        ids.splice(idxTo, 0, from);
        var reordered = {};
        ids.forEach(function (k) { reordered[k] = _scenes[k]; });
        _scenes = reordered;
        renderSceneBar();
        persistScenes();
      });
      btn.addEventListener('click', function () { switchScene(sid); });
      btn.addEventListener('contextmenu', function (e) { openSceneCtxMenu(e, sid); });
      bar.appendChild(btn);
    });
    var addBtn = document.createElement('button');
    addBtn.className = 'scene-btn scene-btn-add';
    addBtn.textContent = '+';
    addBtn.title = 'Create scene';
    addBtn.addEventListener('click', createScene);
    bar.appendChild(addBtn);
    if (typeof feather !== 'undefined') feather.replace();
  }

  function switchScene(sid) {
    if (sid === _activeScene || !_scenes[sid]) return;
    saveAllLayouts();
    _activeScene = sid;
    apiFetch('/api/scenes/activate', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: sid })
    });
    renderSceneBar();
    applyHiddenState();
    applySavedLayouts();
    applyWidgetStyles();
  }

  function createScene() {
    if (Object.keys(_scenes).length >= 18) {
      showToast('Maximum 18 scenes');
      return;
    }
    apiFetch('/api/scenes', { method: 'POST' }).then(function (data) {
      if (data && data.ok) {
        return apiFetch('/api/scenes');
      }
    }).then(function (data) {
      if (data && !data.error) {
        _scenes = data.scenes || _scenes;
        _activeScene = data.active || _activeScene;
        renderSceneBar();
        applyHiddenState();
        applySavedLayouts();
      }
    });
  }

  function deleteScene(sid) {
    if (!sid || Object.keys(_scenes).length <= 1 || sid === 'default') return;
    apiFetch('/api/scenes/' + encodeURIComponent(sid), { method: 'DELETE' }).then(function () {
      return apiFetch('/api/scenes');
    }).then(function (data) {
      if (data && !data.error) {
        _scenes = data.scenes || _scenes;
        _activeScene = data.active || _activeScene;
        renderSceneBar();
        applyHiddenState();
        applySavedLayouts();
      }
    });
  }

  function openSceneSettings() {
    var panel = document.getElementById('result-panel');
    var overlay = document.getElementById('overlay');
    var title = document.getElementById('result-panel-title');
    var body = document.getElementById('result-panel-body');
    title.textContent = 'Scene Settings';

    var html = '<div style="font-family:var(--font-mono);padding:2px 0;">';
    Object.keys(_scenes).forEach(function (sid) {
      var s = _scenes[sid];
      var isDefault = sid === 'default';
      var label = s.label || '📄';
      var name = s.name || sid;
      html += '<div class="ctx-hidden-item" data-scene="' + sid + '" style="margin-bottom:6px;">';
      var iconHtml = '';
      if (s.image) {
        iconHtml = '<img src="' + s.image + '" style="width:22px;height:22px;object-fit:cover;border-radius:3px;vertical-align:middle;">';
      } else if (typeof feather !== 'undefined' && feather.icons[label]) {
        iconHtml = '<i data-feather="' + label + '" width="18" height="18"></i>';
      } else {
        iconHtml = '<span style="font-size:18px">' + label + '</span>';
      }
      html += '<span>' + iconHtml + ' <span style="color:var(--text-primary);font-size:12px;margin-left:4px;">' + escapeHtml(name) + '</span> <span style="color:var(--text-muted);font-size:9px;">(' + sid + ')</span></span>';
      html += '<span style="display:flex;gap:4px;">';
      html += '<button class="pkg-btn scene-settings-label" data-sid="' + sid + '" style="font-size:10px;padding:2px 6px;">Label</button>';
      html += '<button class="pkg-btn scene-settings-icon" data-sid="' + sid + '" style="font-size:10px;padding:2px 6px;">Icon</button>';
      html += '<button class="pkg-btn scene-settings-size" data-sid="' + sid + '" style="font-size:10px;padding:2px 6px;">Size</button>';
      if (!isDefault) {
        html += '<button class="pkg-btn scene-settings-del" data-sid="' + sid + '" style="font-size:10px;padding:2px 6px;border-color:var(--accent-red);color:var(--accent-red)">Del</button>';
      }
      html += '</span></div>';
    });
    html += '</div>';
    body.innerHTML = html;
    if (typeof feather !== 'undefined') feather.replace();

    body.querySelectorAll('.scene-settings-label').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var sid = btn.dataset.sid;
        var s = _scenes[sid];
        var current = s.name || sid;
        showLabelEditor(sid, current);
      });
    });

    body.querySelectorAll('.scene-settings-icon').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var sid = btn.dataset.sid;
        showIconPicker(sid);
      });
    });

    body.querySelectorAll('.scene-settings-del').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (Object.keys(_scenes).length <= 1) return;
        closeResultPanel();
        showDeleteConfirmation(btn.dataset.sid);
      });
    });

    body.querySelectorAll('.scene-settings-size').forEach(function (btn) {
      btn.addEventListener('click', function () {
        showSizeEditor(btn.dataset.sid);
      });
    });

    panel.classList.add('open');
    overlay.classList.add('open');
  }

  function openExtensionsSettings() {
    var panel = document.getElementById('result-panel');
    var overlay = document.getElementById('overlay');
    var title = document.getElementById('result-panel-title');
    var body = document.getElementById('result-panel-body');
    title.textContent = 'Extensions';

    body.innerHTML =
      '<div style="font-family:var(--font-mono);padding:2px 0;">' +
      '<input type="text" id="ext-settings-search" placeholder="Search extensions..." ' +
      'style="width:100%;padding:6px 8px;margin-bottom:8px;border:1px solid var(--border-color);border-radius:4px;' +
      'background:var(--bg-primary);color:var(--text-primary);font-family:var(--font-mono);font-size:12px;outline:none;box-sizing:border-box;">' +
      '<div id="ext-settings-list"></div>' +
      '</div>';

    function renderExtList(filter) {
      var list = document.getElementById('ext-settings-list');
      var data = window.extensionsData || {};
      var ids = Object.keys(data).sort();
      var f = (filter || '').toLowerCase();
      var html = '';
      ids.forEach(function (id) {
        var ext = data[id];
        var name = ext.name || id;
        if (f && name.toLowerCase().indexOf(f) < 0 && id.toLowerCase().indexOf(f) < 0) return;
        var isError = ext.loadError ? true : false;
        html += '<div class="ctx-hidden-item" data-ext="' + id + '" style="margin-bottom:6px;">';
        html += '<span style="display:flex;flex-direction:column;gap:1px;' + (isError ? 'max-width:60%;' : '') + '">';
        html += '<span>' + (isError ? '<span style="color:var(--accent-red);font-size:10px;margin-right:4px;">\u26A0</span>' : '') + '<strong style="color:var(--text-primary);font-size:12px;">' + escapeHtml(name) + '</strong> <span style="color:var(--text-muted);font-size:10px;">(' + escapeHtml(id) + ')</span></span>';
        if (isError) {
          html += '<span style="color:var(--accent-red);font-size:10px;">' + escapeHtml(ext.loadError) + '</span>';
        } else {
          html += '<span style="color:var(--text-muted);font-size:10px;">v' + escapeHtml(ext.version || '?') + (ext.author ? ' &middot; ' + escapeHtml(ext.author) : '') + '</span>';
        }
        html += '</span>';
        html += '<span style="display:flex;gap:4px;">';
        html += '<button class="pkg-btn ext-settings-del" data-ext="' + id + '" style="font-size:10px;padding:2px 6px;border-color:var(--accent-red);color:var(--accent-red)">Delete</button>';
        html += '</span></div>';
      });
      if (!html) html = '<div style="text-align:center;padding:20px;color:var(--text-muted);font-size:12px;">No extensions found.</div>';
      list.innerHTML = html;

      list.querySelectorAll('.ext-settings-del').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var eid = btn.dataset.ext;
          showDeleteExtensionConfirm(eid);
        });
      });
    }

    renderExtList('');

    document.getElementById('ext-settings-search').addEventListener('input', function () {
      renderExtList(this.value);
    });

    panel.classList.add('open');
    overlay.classList.add('open');
  }

  function showDeleteExtensionConfirm(extId) {
    var panel = document.getElementById('result-panel');
    var overlay = document.getElementById('overlay');
    var title = document.getElementById('result-panel-title');
    var body = document.getElementById('result-panel-body');
    var ext = (window.extensionsData || {})[extId] || {};
    var name = ext.name || extId;
    title.textContent = 'Delete extension';
    body.innerHTML =
      '<div style="font-family:var(--font-mono);padding:16px 0;text-align:center;font-size:13px;color:var(--text-primary)">' +
      'Are you sure you want to delete <strong>' + escapeHtml(name) + '</strong>?' +
      '<div style="margin-top:16px;display:flex;gap:8px;justify-content:center">' +
      '<button id="confirm-ext-del-yes" class="pkg-btn" style="background:var(--accent-red,#e74c3c);color:#fff">Delete</button>' +
      '<button id="confirm-ext-del-no" class="pkg-btn">Cancel</button>' +
      '</div></div>';
    document.getElementById('confirm-ext-del-yes').onclick = function () {
      apiFetch('/api/extensions/' + encodeURIComponent(extId), { method: 'DELETE' }).then(function (data) {
        if (data && data.error) {
          if (typeof showToast !== 'undefined') showToast('Error: ' + data.error);
          return;
        }
        if (typeof showToast !== 'undefined') showToast('Extension deleted: ' + name);
        // Reload extensions, scenes and widgets
        apiFetch('/api/extensions').then(function (newData) {
          if (newData && !newData.error) {
            window.extensionsData = newData;
            if (typeof buildSidebar !== 'undefined') buildSidebar(newData);
          }
          // Refresh scene widgets (backend already removed this extension's widgets)
          loadState().then(function () {
            applyHiddenState();
            applySavedLayouts();
          });
          openExtensionsSettings();
        });
      });
    };
    document.getElementById('confirm-ext-del-no').onclick = function () {
      openExtensionsSettings();
    };
  }

  function showLabelEditor(sid, current) {
    var panel = document.getElementById('result-panel');
    var overlay = document.getElementById('overlay');
    var title = document.getElementById('result-panel-title');
    var body = document.getElementById('result-panel-body');
    title.textContent = 'Edit label - ' + sid;

    body.innerHTML =
      '<div style="font-family:var(--font-mono);padding:12px 0;text-align:center;">' +
      '<div style="font-size:11px;color:var(--text-muted);margin-bottom:8px;">Scene name</div>' +
      '<input type="text" id="label-editor-input" value="' + escapeHtml(current) + '" style="width:80%;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:var(--radius-sm);padding:8px;color:var(--text-primary);font-family:var(--font-mono);font-size:14px;text-align:center;">' +
      '<div style="margin-top:14px;display:flex;gap:8px;justify-content:center">' +
      '<button id="label-editor-save" class="pkg-btn" style="background:var(--accent-cyan);color:#000">Save</button>' +
      '<button id="label-editor-cancel" class="pkg-btn">Cancel</button>' +
      '</div></div>';

    document.getElementById('label-editor-save').onclick = function () {
      var val = document.getElementById('label-editor-input').value.trim();
      if (val) {
        apiFetch('/api/scenes/' + encodeURIComponent(sid), {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: val })
        }).then(function () { return apiFetch('/api/scenes'); }).then(function (data) {
          if (data && !data.error) { _scenes = data.scenes; renderSceneBar(); openSceneSettings(); }
        });
      }
    };
    document.getElementById('label-editor-cancel').onclick = function () {
      openSceneSettings();
    };
  }

  function showIconPicker(sid) {
    var panel = document.getElementById('result-panel');
    var overlay = document.getElementById('overlay');
    var title = document.getElementById('result-panel-title');
    var body = document.getElementById('result-panel-body');
    var s = _scenes[sid];
    title.textContent = 'Change icon - ' + sid;
    var currentLabel = s.label || '📄';
    var currentImage = s.image || '';
    var featherNames = ['activity','airplay','alert-circle','alert-triangle','align-center','align-justify','align-left','align-right','anchor','aperture','archive','arrow-down','arrow-down-circle','arrow-down-left','arrow-down-right','arrow-left','arrow-left-circle','arrow-right','arrow-right-circle','arrow-up','arrow-up-circle','arrow-up-left','arrow-up-right','at-sign','award','bar-chart-2','battery','battery-charging','bell','bluetooth','bold','book','bookmark','box','briefcase','calendar','camera','cast','check','check-circle','check-square','chevron-down','chevron-left','chevron-right','chevron-up','chrome','circle','clipboard','clock','cloud','cloud-drizzle','cloud-lightning','cloud-rain','cloud-snow','code','codepen','coffee','command','compass','copy','cpu','credit-card','crop','crosshair','database','delete','disc','divide','dollar-sign','download','droplet','edit','edit-2','edit-3','external-link','eye','eye-off','facebook','fast-forward','feather','figma','file','file-text','film','filter','flag','folder','frown','gift','git-branch','git-commit','git-merge','git-pull-request','github','gitlab','globe','grid','hard-drive','hash','headphones','heart','help-circle','hexagon','home','image','inbox','info','instagram','italic','key','layers','layout','life-buoy','link-2','linkedin','list','loader','lock','log-in','log-out','mail','map','map-pin','maximize','maximize-2','meh','menu','message-circle','message-square','mic','minimize','minimize-2','minus','minus-circle','monitor','moon','more-horizontal','more-vertical','move','music','navigation','navigation-2','npm','octagon','package','paperclip','pause','pause-circle','pen-tool','percent','phone','phone-call','phone-forwarded','phone-incoming','phone-missed','phone-off','phone-outgoing','pie-chart','play','play-circle','plus','plus-circle','plus-square','pocket','power','printer','radio','refresh-ccw','refresh-cw','repeat','rewind','rss','save','scissors','search','send','server','settings','share-2','shield','shopping-bag','shopping-cart','shuffle','sidebar','skip-back','skip-forward','slash','sliders','smartphone','smile','speaker','square','star','stop-circle','sun','sunrise','sunset','tablet','tag','target','terminal','thermometer','thumbs-down','thumbs-up','toggle-left','toggle-right','trash-2','trello','trending-down','trending-up','triangle','truck','tv','twitter','type','umbrella','underline','unlock','upload','user','user-check','user-minus','user-plus','user-x','users','video','video-off','voicemail','volume-1','volume-2','volume-x','watch','wifi','wind','wrench','x','x-circle','x-octagon','x-square','youtube','zap','zap-off','zoom-in','zoom-out'];
    var html = '<div style="font-family:var(--font-mono);padding:4px 0;">';
    html += '<div style="margin-bottom:6px;">';
    html += '<input type="text" id="icon-picker-search" placeholder="Search icons..." style="width:100%;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:var(--radius-sm);padding:5px 8px;color:var(--text-primary);font-family:var(--font-mono);font-size:11px;">';
    html += '</div>';
    html += '<div style="display:flex;gap:4px;margin-bottom:6px;">';
    html += '<button id="icon-picker-tab-icons" class="pkg-btn" style="flex:1;font-size:10px;padding:3px;background:rgba(0,212,255,0.15);border-color:var(--accent-cyan)">Icons</button>';
    html += '<button id="icon-picker-tab-upload" class="pkg-btn" style="flex:1;font-size:10px;padding:3px">Upload</button>';
    html += '</div>';
    html += '<div id="icon-picker-grid" style="display:grid;grid-template-columns:repeat(7,1fr);gap:3px;max-height:160px;overflow-y:auto;padding:2px 0;">';
    featherNames.forEach(function (ic) {
      if (typeof feather === 'undefined' || !feather.icons[ic]) return;
      var active = (!currentImage && currentLabel === ic) ? ';border-color:var(--accent-cyan);background:rgba(0,212,255,0.25);box-shadow:0 0 8px rgba(0,212,255,0.3)' : '';
      html += '<div class="icon-picker-item" data-icon="' + ic + '" title="' + ic + '" style="display:flex;align-items:center;justify-content:center;cursor:pointer;padding:4px;border-radius:var(--radius-sm);border:1px solid transparent' + active + '"><i data-feather="' + ic + '" width="16" height="16"></i></div>';
    });
    html += '</div>';
    html += '<div id="icon-picker-upload" tabindex="0" style="display:none;text-align:center;padding:12px 0;border:1px dashed var(--border-color);border-radius:var(--radius-sm);cursor:pointer;outline:none;">';
    html += '<div style="font-size:24px;margin-bottom:2px;">📁</div>';
    html += '<div style="font-size:10px;color:var(--text-muted)">Click to select file · Ctrl+V to paste</div>';
    html += '</div>';
    html += '<div style="margin-top:8px;text-align:center;">';
    html += '<button id="icon-picker-cancel" class="pkg-btn" style="font-size:10px;padding:3px 12px;">Cancel</button>';
    html += '</div></div>';
    body.innerHTML = html;
    if (typeof feather !== 'undefined') feather.replace();

    function saveIcon(ic) {
      apiFetch('/api/scenes/' + encodeURIComponent(sid), {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label: ic, image: null })
      }).then(function () { return apiFetch('/api/scenes'); }).then(function (data) {
        if (data && !data.error) { _scenes = data.scenes; renderSceneBar(); }
      });
    }

    body.querySelectorAll('.icon-picker-item').forEach(function (el) {
      el.addEventListener('click', function () {
        body.querySelectorAll('.icon-picker-item').forEach(function (e) { e.style.borderColor = 'transparent'; e.style.background = ''; });
        el.style.borderColor = 'var(--accent-cyan)';
        el.style.background = 'rgba(0,212,255,0.25)';
        el.style.boxShadow = '0 0 8px rgba(0,212,255,0.3)';
        saveIcon(el.dataset.icon);
      });
    });

    document.getElementById('icon-picker-search').addEventListener('input', function () {
      var q = this.value.toLowerCase().trim();
      document.querySelectorAll('.icon-picker-item').forEach(function (el) {
        el.style.display = (!q || el.dataset.icon.indexOf(q) !== -1) ? 'flex' : 'none';
      });
    });

    document.getElementById('icon-picker-tab-icons').addEventListener('click', function () {
      document.getElementById('icon-picker-grid').style.display = 'grid';
      document.getElementById('icon-picker-upload').style.display = 'none';
      document.getElementById('icon-picker-tab-icons').style.background = 'rgba(0,212,255,0.15)';
      document.getElementById('icon-picker-tab-icons').style.borderColor = 'var(--accent-cyan)';
      document.getElementById('icon-picker-tab-upload').style.background = '';
      document.getElementById('icon-picker-tab-upload').style.borderColor = '';
    });
    document.getElementById('icon-picker-tab-upload').addEventListener('click', function () {
      document.getElementById('icon-picker-grid').style.display = 'none';
      document.getElementById('icon-picker-upload').style.display = 'block';
      document.getElementById('icon-picker-tab-upload').style.background = 'rgba(0,212,255,0.15)';
      document.getElementById('icon-picker-tab-upload').style.borderColor = 'var(--accent-cyan)';
      document.getElementById('icon-picker-tab-icons').style.background = '';
      document.getElementById('icon-picker-tab-icons').style.borderColor = '';
    });

    var uploadArea = document.getElementById('icon-picker-upload');
    var fileInput = document.getElementById('scene-img-input');
    var uploadClickHandler = function () { fileInput.value = ''; fileInput.click(); };

    function showUploadPreview(imgPath) {
      uploadArea.removeEventListener('click', uploadClickHandler);
      uploadArea.innerHTML =
        '<img src="' + imgPath + '" style="max-width:80px;max-height:80px;object-fit:contain;border-radius:4px;margin:4px auto;display:block;">' +
        '<div style="margin-top:8px;display:flex;gap:8px;justify-content:center;">' +
        '<button id="icon-upload-save" class="pkg-btn" style="font-size:10px;padding:3px 10px;border-color:var(--accent-cyan);">Save</button>' +
        '<button id="icon-upload-cancel" class="pkg-btn" style="font-size:10px;padding:3px 10px;">Cancel</button>' +
        '</div>';
      document.getElementById('icon-upload-save').onclick = function (e) {
        e.stopPropagation();
        apiFetch('/api/scenes/' + encodeURIComponent(sid), {
          method: 'PUT', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ image: imgPath })
        }).then(function () { return apiFetch('/api/scenes'); }).then(function (data) {
          if (data && !data.error) { _scenes = data.scenes; renderSceneBar(); openSceneSettings(); }
        });
      };
      document.getElementById('icon-upload-cancel').onclick = function (e) {
        e.stopPropagation();
        uploadArea.innerHTML = initialUploadHTML;
        uploadArea.addEventListener('click', uploadClickHandler);
      };
    }

    function doUpload(file) {
      var fd = new FormData();
      fd.append('image', file);
      apiFetch('/api/scenes/upload-image', { method: 'POST', body: fd }).then(function (res) {
        if (res && res.ok && res.path) {
          showUploadPreview(res.path);
        }
      });
    }

    var initialUploadHTML = uploadArea.innerHTML;
    uploadArea.addEventListener('click', uploadClickHandler);
    uploadArea.addEventListener('paste', function (e) {
      var items = e.clipboardData.items;
      for (var i = 0; i < items.length; i++) {
        if (items[i].type.indexOf('image') !== -1) {
          doUpload(items[i].getAsFile());
          break;
        }
      }
    });
    fileInput.onchange = function () {
      if (!fileInput.files || !fileInput.files[0]) return;
      doUpload(fileInput.files[0]);
    };

    document.getElementById('icon-picker-cancel').addEventListener('click', function () {
      openSceneSettings();
    });

    panel.classList.add('open');
    overlay.classList.add('open');
  }

  function showSizeEditor(sid) {
    var panel = document.getElementById('result-panel');
    var overlay = document.getElementById('overlay');
    var title = document.getElementById('result-panel-title');
    var body = document.getElementById('result-panel-body');
    var s = _scenes[sid];
    title.textContent = 'Grid size - ' + sid;
    var cols = s.cols || 12;
    var rows = s.rows || 6;
    body.innerHTML =
      '<div style="font-family:var(--font-mono);padding:8px 0;">' +
      '<div style="margin-bottom:10px;">' +
      '<label style="display:block;font-size:10px;color:var(--text-muted);margin-bottom:3px;">Columns</label>' +
      '<input type="number" id="size-editor-cols" value="' + cols + '" min="4" max="24" style="width:100%;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:var(--radius-sm);padding:5px 8px;color:var(--text-primary);font-family:var(--font-mono);font-size:13px;">' +
      '</div>' +
      '<div style="margin-bottom:12px;">' +
      '<label style="display:block;font-size:10px;color:var(--text-muted);margin-bottom:3px;">Rows</label>' +
      '<input type="number" id="size-editor-rows" value="' + rows + '" min="1" max="24" style="width:100%;background:var(--bg-primary);border:1px solid var(--border-color);border-radius:var(--radius-sm);padding:5px 8px;color:var(--text-primary);font-family:var(--font-mono);font-size:13px;">' +
      '</div>' +
      '<div id="size-editor-warning" style="display:none;margin-bottom:10px;padding:6px 10px;background:rgba(255,170,0,0.15);border:1px solid rgba(255,170,0,0.3);border-radius:4px;color:var(--text-primary);font-size:11px;line-height:1.4;">\u26A0\uFE0F  Values above 16 may look cramped or overflow. Consider reducing if elements are cut off.</div>' +
      '<div style="text-align:center;display:flex;gap:8px;justify-content:center;">' +
      '<button id="size-editor-save" class="pkg-btn" style="font-size:11px;padding:4px 14px;border-color:var(--accent-cyan);">Save</button>' +
      '<button id="size-editor-cancel" class="pkg-btn" style="font-size:11px;padding:4px 14px;">Cancel</button>' +
      '</div></div>';
    panel.classList.add('open');
    overlay.classList.add('open');

    function updateWarning() {
      var c = parseInt(document.getElementById('size-editor-cols').value, 10);
      var r = parseInt(document.getElementById('size-editor-rows').value, 10);
      document.getElementById('size-editor-warning').style.display = (c > 16 || r > 16) ? 'block' : 'none';
    }
    document.getElementById('size-editor-cols').addEventListener('input', updateWarning);
    document.getElementById('size-editor-rows').addEventListener('input', updateWarning);
    updateWarning();

    document.getElementById('size-editor-save').onclick = function () {
      var c = parseInt(document.getElementById('size-editor-cols').value, 10);
      var r = parseInt(document.getElementById('size-editor-rows').value, 10);
      if (isNaN(c) || c < 4) c = 12;
      if (c > 24) c = 24;
      if (isNaN(r) || r < 1) r = 6;
      if (r > 24) r = 24;
      apiFetch('/api/scenes/' + encodeURIComponent(sid), {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cols: c, rows: r })
      }).then(function () { return apiFetch('/api/scenes'); }).then(function (data) {
        if (data && !data.error) {
          _scenes = data.scenes;
          renderSceneBar();
          if (sid === _activeScene) {
            applySavedLayouts();
          }
          openSceneSettings();
        }
      });
    };
    document.getElementById('size-editor-cancel').onclick = function () {
      openSceneSettings();
    };
  }

  // ----- settings dropdown -----
  var _settingsMainHTML =
    '<div class="ctx-menu-item" data-action="scenes">\u{1F3E0}  Scene settings</div>' +
    '<div class="ctx-menu-item" data-action="extensions">\u{1F4E6}  Extensions</div>' +
    '<div class="ctx-menu-separator"></div>' +
    '<div class="ctx-menu-item" data-action="window">\u{1F5A5}  Window settings</div>' +
    '<div class="ctx-menu-separator"></div>' +
    '<div class="ctx-menu-item" id="autostart-item" data-action="autostart">\u{23F1}  Loading...</div>';

  var _settingsWindowHTML =
    '<div class="ctx-menu-item" data-action="back" style="color:var(--text-muted);font-size:10px">\u{2190}  Back</div>' +
    '<div class="ctx-menu-separator"></div>' +
    '<div class="ctx-menu-item" data-action="windowed">\u{1F5A5}  Windowed</div>' +
    '<div class="ctx-menu-item" data-action="frameless">\u{1F5A5}  Frameless</div>' +
    '<div class="ctx-menu-item" data-action="fullscreen">\u{1F5A5}  Fullscreen</div>';

  function openSettingsDropdown(e) {
    e.stopPropagation();
    closeCtxMenu();
    closeSceneCtxMenu();
    closeSettingsDropdown();
    var btn = e.currentTarget;
    var rect = btn.getBoundingClientRect();
    var menu = document.getElementById('settings-ctx-menu');
    if (!menu) {
      menu = document.createElement('div');
      menu.id = 'settings-ctx-menu';
      menu.className = 'ctx-menu';
      document.body.appendChild(menu);
      menu.addEventListener('click', function (e) {
        e.stopPropagation();
        var item = e.target.closest('.ctx-menu-item');
        if (!item) return;
        var action = item.dataset.action;
        if (action === 'window') {
          menu.innerHTML = _settingsWindowHTML;
        } else if (action === 'back') {
          menu.innerHTML = _settingsMainHTML;
        } else if (action === 'scenes') {
          closeSettingsDropdown();
          openSceneSettings();
        } else if (action === 'extensions') {
          closeSettingsDropdown();
          openExtensionsSettings();
        } else if (action === 'windowed' || action === 'frameless' || action === 'fullscreen') {
          closeSettingsDropdown();
          setWindowMode(action);
        } else if (action === 'autostart') {
          apiFetch('/api/autostart', { method: 'POST' }).then(function (res) {
            if (res && !res.error) updateAutostartItem(res);
          });
        }
      });
    }
    menu.innerHTML = _settingsMainHTML;
    menu.style.left = Math.min(rect.left, window.innerWidth - 200) + 'px';
    menu.style.top = Math.min(rect.bottom + 4, window.innerHeight - 100) + 'px';
    menu.classList.add('visible');
    apiFetch('/api/autostart').then(function (res) {
      if (res && !res.error) updateAutostartItem(res);
    });
  }

  function updateAutostartItem(res) {
    var item = document.getElementById('autostart-item');
    if (!item) return;
    if (res.available === false) {
      item.textContent = '\u{23F1}  Start on boot (not available)';
      item.style.opacity = '0.4';
      return;
    }
    item.style.opacity = '1';
    item.textContent = res.enabled ? '\u2705  Start on boot' : '\u{2B1C}  Start on boot';
  }

  function closeSettingsDropdown() {
    var menu = document.getElementById('settings-ctx-menu');
    if (menu) menu.classList.remove('visible');
  }

  function setWindowMode(mode) {
    if (typeof currentWindowMode === 'undefined') { currentWindowMode = 'windowed'; }
    if (window.pywebview) {
      pywebview.api.set_window_mode(mode).then(function (applied) {
        currentWindowMode = mode;
        if (!applied && mode !== 'fullscreen') {
          if (typeof showToast !== 'undefined') showToast('Restart CoreFrame to apply');
        }
      }).catch(function (err) {
        console.warn('set_window_mode failed:', err);
        if (typeof applyWindowModeFallback !== 'undefined') applyWindowModeFallback(mode);
        currentWindowMode = mode;
      });
    } else {
      if (typeof applyWindowModeFallback !== 'undefined') applyWindowModeFallback(mode);
      currentWindowMode = mode;
    }
  }

  // ----- init -----
  function init() {
    getOrCreateCtxMenu();

    document.getElementById('btn-settings').addEventListener('click', function (e) {
      openSettingsDropdown(e);
    });

    document.addEventListener('contextmenu', function (e) {
      if (e.target.closest('#mode-indicator-bar')) { closeCtxMenu(); return; }
      if (e.target.closest('#scene-bar')) return;
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
      if (!e.target.closest('#scene-ctx-menu')) closeSceneCtxMenu();
      if (!e.target.closest('#settings-ctx-menu') && !e.target.closest('#btn-settings')) closeSettingsDropdown();
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') {
        closeCtxMenu();
        closeSceneCtxMenu();
        closeSettingsDropdown();
        exitMoveMode();
        resizeTarget = null;
        exitResizeMode();
      }
    });

    // Load persisted state from server
    loadState().then(function () {
      _stateLoaded = true;
      if (document.querySelector('.widget')) {
        applyHiddenState();
        applySavedLayouts();
        applyWidgetStyles();
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
      applyWidgetStyles();
    } else {
      var check = setInterval(function () {
        if (_stateLoaded) {
          clearInterval(check);
          applyHiddenState();
          applySavedLayouts();
          applyWidgetStyles();
        }
      }, 50);
    }
  }

  window.__widgetControl = {
    enterMoveMode: enterMoveMode,
    exitMoveMode: exitMoveMode,
    enterResizeMode: enterResizeMode,
    exitResizeMode: exitResizeMode,
    applyWidgetState: applyWidgetState,
    switchScene: switchScene,
    createScene: createScene,
    deleteScene: deleteScene,
    openSceneSettings: openSceneSettings,
    _activeScene: function () { return _activeScene; },
    _scenes: function () { return _scenes; },
    currentScene: currentScene,
    getHidden: getHidden,
    openEmptyCtxMenu: openEmptyCtxMenu,
    openCtxMenu: openCtxMenu
  };

})();
