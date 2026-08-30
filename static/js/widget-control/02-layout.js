(function () {
  'use strict';

  var s = window.__wc;

  // --- shared icon renderer ---
  var _featherIconNames = {
    activity:1, airplay:1, alertCircle:1, alertOctagon:1, alertTriangle:1,
    alignCenter:1, alignJustify:1, alignLeft:1, alignRight:1, anchor:1,
    aperture:1, archive:1, arrowDown:1, arrowDownCircle:1, arrowDownLeft:1,
    arrowDownRight:1, arrowLeft:1, arrowLeftCircle:1, arrowRight:1, arrowRightCircle:1,
    arrowUp:1, arrowUpCircle:1, arrowUpLeft:1, arrowUpRight:1, atSign:1,
    award:1, barChart:1, barChart2:1, battery:1, batteryCharging:1,
    bell:1, bellOff:1, bluetooth:1, bold:1, book:1,
    bookOpen:1, bookmark:1, bookmark2:1, borderAll:1, borderBottom:1,
    borderInner:1, borderLeft:1, borderOuter:1, borderRight:1, borderTop:1,
    box:1, briefcase:1, calendar:1, camera:1, cameraOff:1,
    cast:1, check:1, checkCircle:1, checkSquare:1, chevronDown:1,
    chevronLeft:1, chevronRight:1, chevronUp:1, chevronDown2:1, chevronLeft2:1,
    chevronRight2:1, chevronUp2:1, clipboard:1, clock:1, cloud:1,
    cloudDrizzle:1, cloudLightning:1, cloudRain:1, cloudSnow:1, code:1,
    codepen:1, codesandbox:1, coffee:1, columns:1, command:1,
    compass:1, copy:1, cornerDownLeft:1, cornerDownRight:1, cornerLeftDown:1,
    cornerLeftUp:1, cornerRightDown:1, cornerRightUp:1, cornerUpLeft:1, cornerUpRight:1,
    cpu:1, creditCard:1, crop:1, crosshair:1, database:1,
    delete:1, desktop:1, divertLeft:1, divertRight:1, dollarSign:1,
    download:1, downloadCloud:1, dribbble:1, droplet:1, edit:1,
    edit2:1, edit3:1, externalLink:1, eye:1, eyeOff:1,
    facebook:1, fastForward:1, feather:1, figma:1, file:1,
    fileMinus:1, filePlus:1, fileText:1, film:1, filter:1,
    flag:1, flame:1, flashlight:1, flashlightOff:1, folder:1,
    folderMinus:1, folderPlus:1, framer:1, frown:1, gift:1,
    gitBranch:1, gitCommit:1, gitMerge:1, gitPullRequest:1, globe:1,
    grid:1, hardDrive:1, hash:1, headphones:1, heart:1,
    heartOff:1, helpCircle:1, home:1, image:1, inbox:1,
    info:1, instagram:1, italic:1, key:1, layers:1,
    layout:1, lifeBuoy:1, link:1, link2:1, list:1,
    loader:1, lock:1, logIn:1, logOut:1, mail:1,
    map:1, mapPin:1, maximize:1, maximize2:1, meh:1,
    menu:1, messageCircle:1, messageSquare:1, mic:1, micOff:1,
    minimize:1, minimize2:1, minus:1, minusCircle:1, minusSquare:1,
    monitor:1, moon:1, moreHorizontal:1, moreVertical:1, mouse:1,
    move:1, music:1, navigation:1, navigation2:1, npm:1,
    octagon:1, package:1, paperclip:1, pause:1, pauseCircle:1,
    penTool:1, percent:1, phone:1, phoneCall:1, phoneForwarded:1,
    phoneIncoming:1, phoneMissed:1, phoneOff:1, phoneOutgoing:1, pieChart:1,
    play:1, playCircle:1, plus:1, plusCircle:1, plusSquare:1,
    pocket:1, power:1, printer:1, radio:1, refreshCcw:1,
    refreshCw:1, repeat:1, rewind:1, rss:1, save:1,
    scissors:1, search:1, send:1, server:1, settings:1,
    share2:1, shield:1, shieldOff:1, shoppingBag:1, shoppingCart:1,
    shuffle:1, sidebar:1, skipBack:1, skipForward:1, slack:1,
    slash:1, sliders:1, smartphone:1, smile:1, snowflake:1,
    sort:1, speaker:1, square:1, star:1, stopCircle:1,
    sun:1, sunrise:1, sunset:1, tablet:1, tag:1,
    target:1, terminal:1, thermometer:1, thumbsDown:1, thumbsUp:1,
    toggleLeft:1, toggleRight:1, tool:1, trash:1, trash2:1,
    triangle:1, truck:1, tv:1, twitch:1, twitter:1,
    type:1, umbrella:1, underline:1, undo:1, unlock:1,
    upload:1, uploadCloud:1, user:1, userCheck:1, userMinus:1,
    userPlus:1, users:1, userX:1, video:1, videoOff:1,
    voicemail:1, volume:1, volume1:1, volume2:1, volumeX:1,
    watch:1, wifi:1, wind:1, x:1, xCircle:1,
    xOctagon:1, xSquare:1, youtube:1, zap:1, zapOff:1,
    zero:1
  }
  var _defaultIcons = {
    system:'monitor',cybersecurity:'shield',security:'lock',fun:'smile',ui:'layout',
    media:'play',ai:'cpu',processes:'list',network:'wifi',disk:'hard-drive',
    default:'box'
  };

  function renderExtIconHtml(icon, extId) {
    if (icon && _featherIconNames[icon]) {
      return '<i data-feather="' + icon + '"></i>';
    }
    if (icon && icon.startsWith('/')) {
      return '<img src="' + icon + '" alt="">';
    }
    var ext = (window.extensionsData && window.extensionsData[extId]) || {};
    var cat = ext.category || '';
    var fallback = _defaultIcons[cat] || _defaultIcons.default;
    return '<i data-feather="' + fallback + '"></i>';
  }
  window.renderExtIconHtml = renderExtIconHtml;

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
    // Safety net: extensions with widgets that have no DOM card and no scene entry
    if (window.extensionsData) {
      for (var extId in window.extensionsData) {
        if (h[extId]) continue;
        if (sw[extId]) continue;
        var ext = window.extensionsData[extId];
        if (ext && ext.widgets && ext.widgets.length > 0 && !document.querySelector('.widget-extension.ext-' + extId)) {
          h[extId] = true;
        }
      }
    }
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

    var existingSearch = panel.querySelector('.result-panel-search');
    if (existingSearch) existingSearch.remove();

    var searchDiv = document.createElement('div');
    searchDiv.className = 'result-panel-search';
    searchDiv.innerHTML = '<input type="text" id="hidden-search" placeholder="Search hidden widgets...">';
    panel.querySelector('.result-panel-header').insertAdjacentElement('afterend', searchDiv);

    const hidden = s.getHidden();
    const keys = Object.keys(hidden);

    function renderHidden(filter) {
      var f = (filter || '').toLowerCase();
      var filtered = keys.filter(function (extId) {
        if (!f) return true;
        var ext = (window.extensionsData && window.extensionsData[extId]) || {};
        var name = (ext.name || extId).toLowerCase();
        return name.indexOf(f) >= 0 || extId.toLowerCase().indexOf(f) >= 0;
      });
      if (filtered.length === 0) {
        body.innerHTML = '<div style="padding:20px;color:var(--text-muted);font-family:var(--font-mono);font-size:12px;">' +
          (f ? 'No matches' : 'No hidden widgets') + '</div>';
        return;
      }
      var html = '<div class="ext-grid">';
      filtered.forEach(function (extId) {
        var ext = (window.extensionsData && window.extensionsData[extId]) || {};
        var name = ext.name || extId;
        var icon = ext.icon || '';
        var version = ext.version || '';
        var iconHtml = renderExtIconHtml(icon, extId);
        html += '<div class="ext-card" data-ext-id="' + extId + '">' +
          '<div class="ext-card-icon">' + iconHtml + '</div>' +
          '<div class="ext-card-name">' + escapeHtml(name) + '</div>' +
          (version ? '<div class="ext-card-meta">v' + escapeHtml(version) + '</div>' : '') +
          '<div class="ext-card-actions"><button class="ext-card-btn" data-action="show">Show</button></div>' +
        '</div>';
      });
      html += '</div>';
      body.innerHTML = html;
      if (window.feather) window.feather.replace();
      body.querySelectorAll('.ext-card-btn[data-action="show"]').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
          e.stopPropagation();
          var card = btn.closest('.ext-card');
          var extId = card.dataset.extId;
          if (!s.unhideWidget(extId)) return;
          card.remove();
          if (body.querySelectorAll('.ext-card').length === 0) {
            body.innerHTML = '<div style="padding:20px;color:var(--text-muted);font-family:var(--font-mono);font-size:12px;">No hidden widgets</div>';
          }
          if (Object.keys(s.getHidden()).length === 0) {
            s.closeCtxMenu();
          }
        });
      });
    }

    renderHidden('');
    document.getElementById('hidden-search').addEventListener('input', function () {
      renderHidden(this.value);
    });

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
        // Widgets not in scene state are hidden by default (user must Show them)
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
    // First, preserve existing hidden widgets with their saved positions
    var old = s.currentScene().widgets;
    for (var hid in old) {
      if (old[hid] && old[hid].hidden) {
        sw[hid] = { col: old[hid].col, row: old[hid].row, w: old[hid].w, h: old[hid].h, hidden: true };
      }
    }
    // Then add/update visible widgets from DOM
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
    s.currentScene().widgets = sw;
    s.persistScenes();
  };

  s.applySavedLayouts = function () {
    var cols = s.sceneCols();
    var sc = s.currentScene();
    var rows = (sc && sc.rows) || 6;
    var grid = document.querySelector('.widget-grid');
    if (grid) {
      grid.style.gridTemplateColumns = 'repeat(' + cols + ', 1fr)';
      grid.style.gridTemplateRows = 'repeat(' + rows + ', 1fr)';
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
        var clampedRow = Math.max(1, Math.min(pos.row || 1, rows));
        var clampedH = Math.min(pos.h || 2, rows - clampedRow + 1);
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
    if (!s.editMode) return;
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

  //  edit mode (unified move + resize)

  s.enterEditMode = function () {
    if (s.editMode) return;
    s.editMode = true;
    freezeAllPositions();
    document.body.classList.add('edit-mode');
    var grid = document.querySelector('.widget-grid');
    if (grid) {
      // Use requestAnimationFrame to ensure grid is rendered before drawing overlay
      requestAnimationFrame(function () { drawGridOverlay(grid); });
    }
    window.addEventListener('resize', redrawOverlay);

    const bar = document.createElement('div');
    bar.id = 'mode-indicator-bar';
    bar.className = 'mode-indicator';
    bar.innerHTML =
      '<span>EDIT \u2014 Drag to move, edges to resize</span>' +
      '<button class="mode-exit-btn" id="mode-exit-btn">Exit \u2715</button>';
    document.body.prepend(bar);
    document.getElementById('mode-exit-btn').addEventListener('click', s.exitEditMode);

    // --- move state ---
    let dragEl = null, startCol = 1, startRow = 1, wSpan = 2, hSpan = 2;
    let overlayable = false;
    let _wasDragged = false;
    let grabDX = 0, grabDY = 0, ghostW = 0, ghostH = 0;
    let placeholder = null;
    let swapTarget = null;
    let _mode = null; // 'move' or 'resize' — set on mousedown

    // --- resize state ---
    let resizeEdges = {};
    let dragStartCol, dragStartRow, dragStartW, dragStartH;

    const BORDER = 12;

    function getGridMetrics() {
      var g = document.querySelector('.widget-grid');
      if (!g) return null;
      var r = g.getBoundingClientRect();
      var sc = s.currentScene();
      return {
        grid: g, rect: r,
        colW: r.width / s.sceneCols(),
        maxCol: (sc && sc.cols) || 12,
        maxRow: (sc && sc.rows) || 6
      };
    }

    function pixelToCol(metrics, px) {
      var ghostLeft = px - ghostW / 2;
      var ghostRight = px + ghostW / 2;
      var bestCol = 1;
      var bestOverlap = -1;
      for (var c = 1; c <= metrics.maxCol - wSpan + 1; c++) {
        var cellLeft = metrics.rect.left + (c - 1) * metrics.colW;
        var cellRight = metrics.rect.left + (c + wSpan - 1) * metrics.colW;
        var overlap = Math.min(ghostRight, cellRight) - Math.max(ghostLeft, cellLeft);
        if (overlap > bestOverlap) {
          bestOverlap = overlap;
          bestCol = c;
        }
      }
      return bestCol;
    }

    function pixelToRowClamped(metrics, py) {
      var ghostTop = py - ghostH / 2;
      var ghostBottom = py + ghostH / 2;
      var rowPitch = getGridRowPitch(metrics.grid);
      var gap = parseFloat(getComputedStyle(metrics.grid).rowGap || getComputedStyle(metrics.grid).gap) || 8;
      var bestRow = 1;
      var bestOverlap = -1;
      for (var r = 1; r <= metrics.maxRow - hSpan + 1; r++) {
        var cellTop = (r - 1) * rowPitch;
        var cellBottom = (r + hSpan - 1) * rowPitch - gap;
        var overlap = Math.min(ghostBottom, cellBottom) - Math.max(ghostTop, cellTop);
        if (overlap > bestOverlap) {
          bestOverlap = overlap;
          bestRow = r;
        }
      }
      return bestRow;
    }

    function getOverlappingWidgets(col, row, w, h, excludeEl) {
      var result = [];
      var targetCells = {};
      for (var c = col; c < col + w; c++)
        for (var r = row; r < row + h; r++)
          targetCells[c + ',' + r] = true;
      document.querySelectorAll('.widget-extension').forEach(function (el) {
        if (el === excludeEl || el.style.display === 'none' || el.dataset.overlayable === 'true') return;
        var gc = (el.style.gridColumn || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
        var gr = (el.style.gridRow || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
        if (!gc || !gr) return;
        var eCol = parseInt(gc[1], 10), eSpan = parseInt(gc[2], 10);
        var eRow = parseInt(gr[1], 10), eSpanH = parseInt(gr[2], 10);
        for (var ec = eCol; ec < eCol + eSpan; ec++)
          for (var er = eRow; er < eRow + eSpanH; er++)
            if (targetCells[ec + ',' + er]) { result.push(el); return; }
      });
      return result;
    }

    function getOverlappingWidgetsMulti(col, row, w, h, excludeList) {
      var result = [];
      var targetCells = {};
      for (var c = col; c < col + w; c++)
        for (var r = row; r < row + h; r++)
          targetCells[c + ',' + r] = true;
      document.querySelectorAll('.widget-extension').forEach(function (el) {
        if (excludeList.indexOf(el) !== -1 || el.style.display === 'none' || el.dataset.overlayable === 'true') return;
        var gc = (el.style.gridColumn || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
        var gr = (el.style.gridRow || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
        if (!gc || !gr) return;
        var eCol = parseInt(gc[1], 10), eSpan = parseInt(gc[2], 10);
        var eRow = parseInt(gr[1], 10), eSpanH = parseInt(gr[2], 10);
        for (var ec = eCol; ec < eCol + eSpan; ec++)
          for (var er = eRow; er < eRow + eSpanH; er++)
            if (targetCells[ec + ',' + er]) { result.push(el); return; }
      });
      return result;
    }

    function canWidgetFit(el, col, row) {
      var gc = (el.style.gridColumn || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
      var gr = (el.style.gridRow || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
      if (!gc || !gr) return false;
      var w = parseInt(gc[2], 10), h = parseInt(gr[2], 10);
      var metrics = getGridMetrics();
      if (!metrics) return false;
      if (col + w - 1 > metrics.maxCol || row + h - 1 > metrics.maxRow) return false;
      var others = getOverlappingWidgets(col, row, w, h, el);
      return others.length === 0;
    }

    function findFreeSpot(el, avoidEl, targetCol, targetRow, targetW, targetH, metrics) {
      var gc = (el.style.gridColumn || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
      var gr = (el.style.gridRow || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
      if (!gc || !gr) return null;
      var sw = parseInt(gc[2], 10), sh = parseInt(gr[2], 10);
      var curCol = parseInt(gc[1], 10), curRow = parseInt(gr[1], 10);
      var blockedCells = {};
      for (var tc = targetCol; tc < targetCol + targetW; tc++)
        for (var tr = targetRow; tr < targetRow + targetH; tr++)
          blockedCells[tc + ',' + tr] = true;
      var best = null, bestDist = Infinity;
      for (var r = 1; r <= metrics.maxRow - sh + 1; r++) {
        for (var c = 1; c <= metrics.maxCol - sw + 1; c++) {
          var dist = Math.abs(c - curCol) + Math.abs(r - curRow);
          if (dist === 0) continue;
          var hitsBlocked = false;
          for (var sc = c; sc < c + sw; sc++)
            for (var sr = r; sr < r + sh; sr++)
              if (blockedCells[sc + ',' + sr]) { hitsBlocked = true; break; }
          if (hitsBlocked) continue;
          var others = getOverlappingWidgetsMulti(c, r, sw, sh, [el, avoidEl]);
          if (others.length === 0 && dist < bestDist) {
            bestDist = dist;
            best = { col: c, row: r };
          }
        }
      }
      return best;
    }

    function removePlaceholder() {
      if (placeholder) { placeholder.remove(); placeholder = null; }
    }

    function updateTargetIndicator(metrics, col, row, state) {
      if (!placeholder) return;
      placeholder.style.gridColumn = col + ' / span ' + wSpan;
      placeholder.style.gridRow = row + ' / span ' + hSpan;
      placeholder.classList.remove('widget-drag-placeholder-occupied', 'widget-drag-placeholder-displace');
      if (state === 'occupied') placeholder.classList.add('widget-drag-placeholder-occupied');
      else if (state === 'displace') placeholder.classList.add('widget-drag-placeholder-displace');
    }

    function clearSwapTarget() {
      if (swapTarget) { swapTarget.classList.remove('widget-swap-target'); swapTarget = null; }
    }

    function placeWidget(el, col, row, w, h) {
      el.style.position = '';
      el.style.left = '';
      el.style.top = '';
      el.style.width = '';
      el.style.height = '';
      el.style.zIndex = '';
      el.classList.remove('widget-dragging');
      var metrics = getGridMetrics();
      if (metrics && metrics.grid) metrics.grid.appendChild(el);
      el.style.gridColumn = col + ' / span ' + w;
      el.style.gridRow = row + ' / span ' + h;
    }

    // --- edge detection (for resize) ---

    function detectEdges(w, mx, my) {
      var r = w.getBoundingClientRect();
      return {
        top: Math.abs(my - r.top) < BORDER,
        bottom: Math.abs(my - r.bottom) < BORDER,
        left: Math.abs(mx - r.left) < BORDER,
        right: Math.abs(mx - r.right) < BORDER
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

    function getGridColRow(mx, my, g, colW) {
      var gridRect = g.getBoundingClientRect();
      return {
        col: Math.max(1, Math.floor((mx - gridRect.left) / colW) + 1),
        row: Math.max(1, pixelToRow(g, my - gridRect.top))
      };
    }

    // --- hover: update cursor ---

    function onHover(e) {
      if (_mode) return;
      var widget = e.target.closest('.widget-extension');
      document.querySelectorAll('.widget-edge-hover').forEach(function(el) {
        el.classList.remove('widget-edge-hover');
        el.style.cursor = '';
      });
      if (!widget || widget.style.display === 'none') {
        document.body.style.cursor = '';
        return;
      }
      var edges = detectEdges(widget, e.clientX, e.clientY);
      var cursor = cursorForEdges(edges);
      if (cursor) {
        widget.classList.add('widget-edge-hover');
        widget.style.cursor = cursor;
        document.body.style.cursor = '';
      } else {
        widget.style.cursor = 'grab';
        document.body.style.cursor = '';
      }
    }

    // --- unified mousedown ---

    function onDown(e) {
      if (!s.editMode || e.button !== 0) return;
      var widget = e.target.closest('.widget-extension');
      if (!widget || widget.closest('#mode-indicator-bar')) return;

      var edges = detectEdges(widget, e.clientX, e.clientY);
      var isEdge = edges.top || edges.bottom || edges.left || edges.right;

      if (isEdge) {
        // --- RESIZE ---
        e.preventDefault();
        _mode = 'resize';
        resizeEdges = edges;
        var info = getWidgetGridInfo(widget);
        if (!info) { _mode = null; return; }
        dragStartCol = info.col; dragStartRow = info.row;
        dragStartW = info.w; dragStartH = info.h;
        dragEl = widget;
        dragEl.classList.add('widget-resizing');
        document.addEventListener('mousemove', onResizeDrag, true);
        document.addEventListener('mouseup', onResizeUp, true);
      } else {
        // --- MOVE ---
        _wasDragged = false;
        dragEl = widget;
        overlayable = dragEl.dataset.overlayable === 'true';

        var metrics = getGridMetrics();
        if (!metrics) { dragEl = null; return; }

        var wr = dragEl.getBoundingClientRect();
        startCol = Math.max(1, Math.round((wr.left - metrics.rect.left) / metrics.colW) + 1);
        var sc = s.currentScene();
        var maxRow = (sc && sc.rows) || 6;
        startRow = Math.max(1, Math.min(maxRow - hSpan + 1, pixelToRow(metrics.grid, wr.top - metrics.rect.top)));

        var cs = getComputedStyle(dragEl);
        var gc = cs.gridColumn || dragEl.style.gridColumn || 'auto / span 2';
        var gr = cs.gridRow || dragEl.style.gridRow || 'auto / span 2';
        wSpan = parseInt((gc.match(/span\s+(\d+)/) || [,'2'])[1], 10);
        hSpan = parseInt((gr.match(/span\s+(\d+)/) || [,'2'])[1], 10);

        grabDX = e.clientX - wr.left;
        grabDY = e.clientY - wr.top;
        ghostW = wr.width;
        ghostH = wr.height;

        dragEl.style.position = 'fixed';
        dragEl.style.left = (e.clientX - grabDX) + 'px';
        dragEl.style.top = (e.clientY - grabDY) + 'px';
        dragEl.style.width = ghostW + 'px';
        dragEl.style.height = ghostH + 'px';
        dragEl.style.zIndex = '9999';
        dragEl.style.margin = '0';
        dragEl.classList.add('widget-dragging');
        document.body.appendChild(dragEl);
        document.body.classList.add('widget-drag-active');

        document.addEventListener('mousemove', onMove, true);
        document.addEventListener('mouseup', onMoveUp, true);
      }
    }

    // --- MOVE ---

    function onMove(e) {
      if (!dragEl || !_wasDragged && (Math.abs(e.clientX - (parseFloat(dragEl.style.left) + grabDX)) > 3 || Math.abs(e.clientY - (parseFloat(dragEl.style.top) + grabDY)) > 3)) {
        _wasDragged = true;
      }
      if (!dragEl) return;

      var metrics = getGridMetrics();
      if (!metrics) return;

      var newLeft = Math.max(metrics.rect.left, Math.min(metrics.rect.right - ghostW, e.clientX - grabDX));
      var newTop = Math.max(metrics.rect.top, Math.min(metrics.rect.bottom - ghostH, e.clientY - grabDY));
      dragEl.style.left = newLeft + 'px';
      dragEl.style.top = newTop + 'px';

      var tCol = pixelToCol(metrics, newLeft + ghostW / 2);
      var tRow = pixelToRowClamped(metrics, newTop + ghostH / 2);

      if (!placeholder) {
        placeholder = document.createElement('div');
        placeholder.className = 'widget-drag-placeholder';
        metrics.grid.appendChild(placeholder);
      }

      var overlapping = getOverlappingWidgets(tCol, tRow, wSpan, hSpan, dragEl);
      clearSwapTarget();

      if (overlapping.length === 0) {
        dragEl.classList.remove('widget-collision');
        updateTargetIndicator(metrics, tCol, tRow, 'free');
      } else if (overlapping.length === 1 && !overlayable) {
        var candidate = overlapping[0];
        var candGc = (candidate.style.gridColumn || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
        var candGr = (candidate.style.gridRow || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
        var canSwap = canWidgetFit(candidate, startCol, startRow);
        var canDisplace = false;
        if (!canSwap && candGc && candGr) {
          var cW = parseInt(candGc[2], 10), cH = parseInt(candGr[2], 10);
          var curCol = parseInt(candGc[1], 10), curRow = parseInt(candGr[1], 10);
          var blockedCells = {};
          for (var tc = tCol; tc < tCol + wSpan; tc++)
            for (var tr = tRow; tr < tRow + hSpan; tr++)
              blockedCells[tc + ',' + tr] = true;
          for (var r = 1; r <= metrics.maxRow - cH + 1; r++) {
            for (var c = 1; c <= metrics.maxCol - cW + 1; c++) {
              if (Math.abs(c - curCol) + Math.abs(r - curRow) === 0) continue;
              var hitsBlocked = false;
              for (var sc = c; sc < c + cW; sc++)
                for (var sr = r; sr < r + cH; sr++)
                  if (blockedCells[sc + ',' + sr]) { hitsBlocked = true; break; }
              if (hitsBlocked) continue;
              var others = getOverlappingWidgets(c, r, cW, cH, candidate);
              if (others.length === 0) { canDisplace = true; break; }
            }
            if (canDisplace) break;
          }
        }
        if (canSwap) {
          swapTarget = candidate;
          candidate.classList.add('widget-swap-target');
          updateTargetIndicator(metrics, tCol, tRow, 'free');
          dragEl.classList.remove('widget-collision');
        } else if (canDisplace) {
          updateTargetIndicator(metrics, tCol, tRow, 'displace');
          dragEl.classList.remove('widget-collision');
        } else {
          dragEl.classList.add('widget-collision');
          updateTargetIndicator(metrics, tCol, tRow, 'occupied');
        }
      } else {
        dragEl.classList.add('widget-collision');
        updateTargetIndicator(metrics, tCol, tRow, 'occupied');
      }
    }

    function onMoveUp() {
      document.removeEventListener('mousemove', onMove, true);
      document.removeEventListener('mouseup', onMoveUp, true);
      if (!dragEl) return;

      var metrics = getGridMetrics();
      var extId = dragEl.dataset.extId;

      clearSwapTarget();
      removePlaceholder();

      if (metrics) {
        var newLeft = parseFloat(dragEl.style.left);
        var newTop = parseFloat(dragEl.style.top);
        var tCol = pixelToCol(metrics, newLeft + ghostW / 2);
        var tRow = pixelToRowClamped(metrics, newTop + ghostH / 2);

        var overlapping = getOverlappingWidgets(tCol, tRow, wSpan, hSpan, dragEl);
        if (overlapping.length === 0 && !overlayable) {
          placeWidget(dragEl, tCol, tRow, wSpan, hSpan);
          if (extId) s.saveWidgetLayout(extId, tCol, tRow, wSpan, hSpan);
        } else if (overlapping.length === 1 && !overlayable) {
          var other = overlapping[0];
          var otherGc = (other.style.gridColumn || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
          var otherGr = (other.style.gridRow || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
          if (otherGc && otherGr) {
            var oCol = parseInt(otherGc[1], 10), oRow = parseInt(otherGr[1], 10);
            var oW = parseInt(otherGc[2], 10), oH = parseInt(otherGr[2], 10);
            var otherId = other.dataset.extId;

            if (oW === wSpan && oH === hSpan) {
              var swapFree = canWidgetFit(other, startCol, startRow);
              if (swapFree) {
                placeWidget(dragEl, tCol, tRow, wSpan, hSpan);
                if (extId) s.saveWidgetLayout(extId, tCol, tRow, wSpan, hSpan);
                placeWidget(other, startCol, startRow, oW, oH);
                if (otherId) s.saveWidgetLayout(otherId, startCol, startRow, oW, oH);
              } else {
                var altSpot = findFreeSpot(other, dragEl, tCol, tRow, wSpan, hSpan, metrics);
                if (altSpot) {
                  placeWidget(dragEl, tCol, tRow, wSpan, hSpan);
                  if (extId) s.saveWidgetLayout(extId, tCol, tRow, wSpan, hSpan);
                  placeWidget(other, altSpot.col, altSpot.row, oW, oH);
                  if (otherId) s.saveWidgetLayout(otherId, altSpot.col, altSpot.row, oW, oH);
                } else {
                  var selfSpot = findFreeSpot(dragEl, null, tCol, tRow, wSpan, hSpan, metrics);
                  if (selfSpot) {
                    placeWidget(dragEl, selfSpot.col, selfSpot.row, wSpan, hSpan);
                    if (extId) s.saveWidgetLayout(extId, selfSpot.col, selfSpot.row, wSpan, hSpan);
                  } else {
                    placeWidget(dragEl, startCol, startRow, wSpan, hSpan);
                    if (extId) s.saveWidgetLayout(extId, startCol, startRow, wSpan, hSpan);
                  }
                }
              }
            } else {
              var spot = findFreeSpot(other, dragEl, tCol, tRow, wSpan, hSpan, metrics);
              if (spot) {
                placeWidget(dragEl, tCol, tRow, wSpan, hSpan);
                if (extId) s.saveWidgetLayout(extId, tCol, tRow, wSpan, hSpan);
                placeWidget(other, spot.col, spot.row, oW, oH);
                if (otherId) s.saveWidgetLayout(otherId, spot.col, spot.row, oW, oH);
              } else {
                var selfSpot2 = findFreeSpot(dragEl, null, tCol, tRow, wSpan, hSpan, metrics);
                if (selfSpot2) {
                  placeWidget(dragEl, selfSpot2.col, selfSpot2.row, wSpan, hSpan);
                  if (extId) s.saveWidgetLayout(extId, selfSpot2.col, selfSpot2.row, wSpan, hSpan);
                } else {
                  placeWidget(dragEl, startCol, startRow, wSpan, hSpan);
                  if (extId) s.saveWidgetLayout(extId, startCol, startRow, wSpan, hSpan);
                }
              }
            }
          } else {
            var safeSpot = findFreeSpot(dragEl, null, tCol, tRow, wSpan, hSpan, metrics);
            if (safeSpot) {
              placeWidget(dragEl, safeSpot.col, safeSpot.row, wSpan, hSpan);
              if (extId) s.saveWidgetLayout(extId, safeSpot.col, safeSpot.row, wSpan, hSpan);
            } else {
              placeWidget(dragEl, startCol, startRow, wSpan, hSpan);
              if (extId) s.saveWidgetLayout(extId, startCol, startRow, wSpan, hSpan);
            }
          }
        } else if (!overlayable) {
          var placed = false;
          var candidates = [
            { col: tCol, row: startRow },
            { col: startCol, row: tRow }
          ];
          candidates.sort(function (a, b) {
            var dA = Math.abs(a.col - tCol) + Math.abs(a.row - tRow);
            var dB = Math.abs(b.col - tCol) + Math.abs(b.row - tRow);
            return dA - dB;
          });
          for (var i = 0; i < candidates.length; i++) {
            var cand = candidates[i];
            if (cand.col < 1 || cand.row < 1) continue;
            if (cand.col + wSpan - 1 > metrics.maxCol || cand.row + hSpan - 1 > metrics.maxRow) continue;
            var cOver = getOverlappingWidgets(cand.col, cand.row, wSpan, hSpan, dragEl);
            if (cOver.length === 0) {
              placeWidget(dragEl, cand.col, cand.row, wSpan, hSpan);
              if (extId) s.saveWidgetLayout(extId, cand.col, cand.row, wSpan, hSpan);
              placed = true;
              break;
            }
          }
          if (!placed) {
            var lastResort = findFreeSpot(dragEl, null, tCol, tRow, wSpan, hSpan, metrics);
            if (lastResort) {
              placeWidget(dragEl, lastResort.col, lastResort.row, wSpan, hSpan);
              if (extId) s.saveWidgetLayout(extId, lastResort.col, lastResort.row, wSpan, hSpan);
            } else {
              placeWidget(dragEl, startCol, startRow, wSpan, hSpan);
              if (extId) s.saveWidgetLayout(extId, startCol, startRow, wSpan, hSpan);
            }
          }
        } else {
          placeWidget(dragEl, tCol, tRow, wSpan, hSpan);
          if (extId) s.saveWidgetLayout(extId, tCol, tRow, wSpan, hSpan);
        }
      } else {
        placeWidget(dragEl, startCol, startRow, wSpan, hSpan);
      }

      var finalGc = (dragEl.style.gridColumn || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
      var finalGr = (dragEl.style.gridRow || '').match(/^(\d+)\s*\/\s*span\s+(\d+)$/);
      if (finalGc && finalGr) {
        var fCol = parseInt(finalGc[1], 10), fW = parseInt(finalGc[2], 10);
        var fRow = parseInt(finalGr[1], 10), fH = parseInt(finalGr[2], 10);
        var finalOverlap = getOverlappingWidgets(fCol, fRow, fW, fH, dragEl);
        if (finalOverlap.length > 0) {
          var rescue = findFreeSpot(dragEl, null, fCol, fRow, fW, fH, getGridMetrics());
          if (rescue) {
            placeWidget(dragEl, rescue.col, rescue.row, fW, fH);
            if (extId) s.saveWidgetLayout(extId, rescue.col, rescue.row, fW, fH);
          }
        }
      }

      dragEl.classList.remove('widget-dragging', 'widget-collision');
      document.body.classList.remove('widget-drag-active');
      dragEl = null;
      _wasDragged = false;
      _mode = null;
    }

    // --- RESIZE ---

    function onResizeDrag(e) {
      if (_mode !== 'resize' || !dragEl) return;
      var grid = dragEl.closest('.widget-grid');
      if (!grid) return;
      var colW = grid.getBoundingClientRect().width / s.sceneCols();
      var pos = getGridColRow(e.clientX, e.clientY, grid, colW);
      var sc = s.currentScene();
      var maxRow = (sc && sc.rows) || 6;

      var mainEl = document.getElementById('main');
      var mainRect = mainEl.getBoundingClientRect();
      if (e.clientY > mainRect.bottom - 24 && pos.row > maxRow) {
        mainEl.scrollTop += 12;
      } else if (e.clientY < mainRect.top + 24 && pos.row < 1) {
        mainEl.scrollTop -= 12;
      }

      var newCol = dragStartCol, newRow = dragStartRow;
      var newW = dragStartW, newH = dragStartH;

      if (resizeEdges.right) {
        newW = Math.max(1, Math.min(s.sceneCols() - newCol + 1, pos.col - newCol + 1));
      }
      if (resizeEdges.left) {
        var maxCol = dragStartCol + dragStartW - 1;
        var delta = dragStartCol - pos.col;
        newCol = Math.max(1, Math.min(maxCol, dragStartCol - delta));
        newW = Math.max(1, Math.min(s.sceneCols() - newCol + 1, dragStartW + delta));
      }
      if (resizeEdges.bottom) {
        newH = Math.max(1, Math.min(maxRow - newRow + 1, pos.row - newRow + 1));
      }
      if (resizeEdges.top) {
        var maxRowPos = dragStartRow + dragStartH - 1;
        var delta = dragStartRow - pos.row;
        newRow = Math.max(1, Math.min(maxRowPos, dragStartRow - delta));
        newH = Math.max(1, Math.min(maxRow - newRow + 1, dragStartH + delta));
      }

      var ov = dragEl.dataset.overlayable === 'true';
      if (!ov && hasCollisionWithNonOverlayable(dragEl.dataset.extId, newCol, newRow, newW, newH)) {
        dragEl.classList.add('widget-collision');
        return;
      }
      dragEl.classList.remove('widget-collision');
      dragEl.style.gridColumn = newCol + ' / span ' + newW;
      dragEl.style.gridRow = newRow + ' / span ' + newH;
    }

    function onResizeUp() {
      document.removeEventListener('mousemove', onResizeDrag, true);
      document.removeEventListener('mouseup', onResizeUp, true);
      if (dragEl) {
        dragEl.classList.remove('widget-collision', 'widget-resizing');
        s.saveAllLayouts();
      }
      dragEl = null;
      resizeEdges = {};
      _mode = null;
    }

    function onClickSuppress(e) {
      if (_wasDragged) { e.stopPropagation(); _wasDragged = false; }
    }

    document.addEventListener('mousedown', onDown);
    document.addEventListener('mousemove', onHover);
    document.addEventListener('click', onClickSuppress, true);
    document._editCleanup = function () {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('mousemove', onHover);
      document.removeEventListener('mousemove', onMove, true);
      document.removeEventListener('mouseup', onMoveUp, true);
      document.removeEventListener('mousemove', onResizeDrag, true);
      document.removeEventListener('mouseup', onResizeUp, true);
      document.removeEventListener('click', onClickSuppress, true);
      document.body.style.cursor = '';
    };
  };

  s.exitEditMode = function () {
    if (!s.editMode) return;
    s.editMode = false;
    var grid = document.querySelector('.widget-grid');
    if (grid) { grid.style.minHeight = ''; grid.style.position = ''; removeGridOverlay(grid); }
    window.removeEventListener('resize', redrawOverlay);
    document.body.classList.remove('edit-mode');
    document.body.classList.remove('widget-drag-active');
    if (document._editCleanup) { document._editCleanup(); document._editCleanup = null; }
    const bar = document.getElementById('mode-indicator-bar');
    if (bar) bar.remove();
    // Restore orphaned dragged widgets back to grid
    document.querySelectorAll('.widget-dragging').forEach(function (el) {
      el.classList.remove('widget-dragging');
      el.style.position = '';
      el.style.left = '';
      el.style.top = '';
      el.style.width = '';
      el.style.height = '';
      el.style.zIndex = '';
      el.style.margin = '';
      el.style.opacity = '';
      el.style.transform = '';
      el.style.boxShadow = '';
      el.style.borderColor = '';
      el.style.pointerEvents = '';
      // Force reflow to clear visual state immediately
      void el.offsetHeight;
      // If widget is not inside the grid, restore it
      if (grid && !grid.contains(el)) {
        grid.appendChild(el);
        // Try to restore original grid position from dataset or current style
        var info = getWidgetGridInfo(el);
        if (info) {
          el.style.gridColumn = info.col + ' / span ' + info.w;
          el.style.gridRow = info.row + ' / span ' + info.h;
        }
      }
    });
    document.querySelectorAll('.widget-resizing').forEach(function (el) { el.classList.remove('widget-resizing'); });
    document.querySelectorAll('.widget-edge-hover').forEach(function (el) {
      el.classList.remove('widget-edge-hover');
      el.style.cursor = '';
    });
    document.querySelectorAll('.widget-swap-target').forEach(function (el) { el.classList.remove('widget-swap-target'); });
    document.body.style.cursor = '';
    document.querySelectorAll('.widget-drag-placeholder').forEach(function (el) { el.remove(); });
  };

  // keep old names as aliases for backward compat
  s.enterMoveMode = s.enterEditMode;
  s.exitMoveMode = s.exitEditMode;
  s.enterResizeMode = s.enterEditMode;
  s.exitResizeMode = s.exitEditMode;
})();
