(function () {
  'use strict';

  var s = window.__wc;

  s.loadState = function () {
    return apiFetch('/api/widget-state').then(function (ws) {
      var savedOrder = ws && ws.sceneOrder;
      return apiFetch('/api/scenes').then(function (data) {
        if (data && !data.error) {
          s._scenes = data.scenes || {};
          var keys = Object.keys(s._scenes);
          s._sceneOrder = (savedOrder && savedOrder.length === keys.length)
            ? savedOrder.filter(function (k) { return s._scenes[k]; })
            : keys;
          s._activeScene = data.active || s._sceneOrder[0] || null;
          s._stateLoaded = true;
          s.renderSceneBar();
        }
      });
    });
  };

  //  scene bar 

  s.renderSceneBar = function () {
    var bar = document.getElementById('scene-bar');
    if (!bar) return;
    bar.innerHTML = '';
    var ids = s._sceneOrder.length ? s._sceneOrder : Object.keys(s._scenes);
    ids.forEach(function (sid) {
      var btn = document.createElement('button');
      btn.className = 'scene-btn' + (sid === s._activeScene ? ' active' : '');
      btn.dataset.sceneId = sid;
      if (s._scenes[sid].image) {
        var img = document.createElement('img');
        img.className = 'scene-btn-img';
        img.src = s._scenes[sid].image;
        img.alt = '';
        btn.appendChild(img);
      } else if (typeof feather !== 'undefined' && feather.icons[s._scenes[sid].label]) {
        var i = document.createElement('i');
        i.setAttribute('data-feather', s._scenes[sid].label);
        i.setAttribute('width', '18');
        i.setAttribute('height', '18');
        btn.appendChild(i);
      } else {
        btn.textContent = s._scenes[sid].label || '\u{1F4C4}';
      }
      btn.title = s._scenes[sid].name || sid;
      btn.draggable = true;
      btn.addEventListener('dragstart', function (e) { e.dataTransfer.setData('text/plain', sid); });
      btn.addEventListener('dragover', function (e) { e.preventDefault(); });
      btn.addEventListener('drop', function (e) {
        e.preventDefault();
        var from = e.dataTransfer.getData('text/plain');
        if (!from || from === sid) return;
        var idxFrom = s._sceneOrder.indexOf(from);
        var idxTo = s._sceneOrder.indexOf(sid);
        if (idxFrom < 0 || idxTo < 0) return;
        s._sceneOrder.splice(idxFrom, 1);
        s._sceneOrder.splice(idxTo, 0, from);
        var reordered = {};
        s._sceneOrder.forEach(function (k) { reordered[k] = s._scenes[k]; });
        s._scenes = reordered;
        s.renderSceneBar();
        s.persistScenes();
      });
      btn.addEventListener('click', function () { s.switchScene(sid); });
      btn.addEventListener('contextmenu', function (e) { s.openSceneCtxMenu(e, sid); });
      bar.appendChild(btn);
    });
    var addBtn = document.createElement('button');
    addBtn.className = 'scene-btn scene-btn-add';
    addBtn.textContent = '+';
    addBtn.title = 'Create scene';
    addBtn.addEventListener('click', s.createScene);
    bar.appendChild(addBtn);
    if (typeof feather !== 'undefined') feather.replace();
  };

  s.switchScene = function (sid) {
    if (sid === s._activeScene || !s._scenes[sid]) return;
    s.saveAllLayouts();
    s._activeScene = sid;
    s.renderSceneBar();
    s.applyHiddenState();
    s.applySavedLayouts();
    s.applyWidgetStyles();
    s.persistScenes();
  };

  s.createScene = function () {
    if (Object.keys(s._scenes).length >= 18) {
      s.showToast('Maximum 18 scenes');
      return;
    }
    apiFetch('/api/scenes', { method: 'POST' }).then(function (data) {
      if (data && data.ok) {
        return apiFetch('/api/scenes').then(function (scenesData) {
          return { newId: data.id, scenesData: scenesData };
        });
      }
    }).then(function (result) {
      if (result && result.scenesData && !result.scenesData.error) {
        s._scenes = result.scenesData.scenes || s._scenes;
        if (s._sceneOrder.indexOf(result.newId) < 0) {
          s._sceneOrder.push(result.newId);
        }
          s._activeScene = result.scenesData.active || s._activeScene;
          s.renderSceneBar();
          s.applyHiddenState();
          s.applySavedLayouts();
          s.persistScenes();
      }
    });
  };

  s.deleteScene = function (sid) {
    if (!sid || Object.keys(s._scenes).length <= 1 || sid === 'default') return;
    apiFetch('/api/scenes/' + encodeURIComponent(sid), { method: 'DELETE' }).then(function () {
      return apiFetch('/api/scenes');
    }).then(function (data) {
      if (data && !data.error) {
        s._scenes = data.scenes || s._scenes;
        var idx = s._sceneOrder.indexOf(sid);
        if (idx >= 0) s._sceneOrder.splice(idx, 1);
        s._activeScene = data.active || s._activeScene;
        s.renderSceneBar();
        s.applyHiddenState();
        s.applySavedLayouts();
      }
    });
  };

  s.openSceneSettings = function () {
    var panel = document.getElementById('result-panel');
    var overlay = document.getElementById('overlay');
    var title = document.getElementById('result-panel-title');
    var body = document.getElementById('result-panel-body');
    title.textContent = 'Scene Settings';

    var html = '<div style="font-family:var(--font-mono);padding:2px 0;">';
    (s._sceneOrder.length ? s._sceneOrder : Object.keys(s._scenes)).forEach(function (sid) {
      var sc = s._scenes[sid];
      var isDefault = sid === 'default';
      var label = sc.label || '\u{1F4C4}';
      var name = sc.name || sid;
      html += '<div class="ctx-hidden-item" data-scene="' + sid + '" style="margin-bottom:6px;">';
      var iconHtml = '';
      if (sc.image) {
        iconHtml = '<img src="' + sc.image + '" style="width:22px;height:22px;object-fit:cover;border-radius:3px;vertical-align:middle;">';
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
        var sc = s._scenes[sid];
        var current = sc.name || sid;
        s.showLabelEditor(sid, current);
      });
    });

    body.querySelectorAll('.scene-settings-icon').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var sid = btn.dataset.sid;
        s.showIconPicker(sid);
      });
    });

    body.querySelectorAll('.scene-settings-del').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (Object.keys(s._scenes).length <= 1) return;
        s.closeResultPanel();
        s.showDeleteConfirmation(btn.dataset.sid);
      });
    });

    body.querySelectorAll('.scene-settings-size').forEach(function (btn) {
      btn.addEventListener('click', function () {
        s.showSizeEditor(btn.dataset.sid);
      });
    });

    panel.classList.add('open');
    overlay.classList.add('open');
  };

  s.showDeleteConfirmation = function (sid) {
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
      s.closeResultPanel();
      s.deleteScene(sid);
    };
    document.getElementById('confirm-delete-no').onclick = function () {
      s.closeResultPanel();
    };
  };

  s.openSceneCtxMenu = function (e, sid) {
    e.preventDefault();
    e.stopPropagation();
    s.closeCtxMenu();
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
          s.showDeleteConfirmation(sceneId);
        } else if (action === 'icon') {
          s.showIconPicker(sceneId);
        }
        s.closeSceneCtxMenu();
      });
    }
    menu.dataset.sceneId = sid;
    var delItem = menu.querySelector('[data-action="delete"]');
    if (delItem) delItem.style.display = (Object.keys(s._scenes).length > 1 && sid !== 'default') ? '' : 'none';
    menu.style.left = Math.min(e.clientX, window.innerWidth - 200) + 'px';
    menu.style.top = Math.min(e.clientY, window.innerHeight - 100) + 'px';
    menu.classList.add('visible');
  };

  s.closeSceneCtxMenu = function () {
    var menu = document.getElementById('scene-ctx-menu');
    if (menu) menu.classList.remove('visible');
  };

  s.showLabelEditor = function (sid, current) {
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
          if (data && !data.error) { s._scenes = data.scenes; s.renderSceneBar(); s.openSceneSettings(); }
        });
      }
    };
    document.getElementById('label-editor-cancel').onclick = function () {
      s.openSceneSettings();
    };
  };

  s.showSizeEditor = function (sid) {
    var panel = document.getElementById('result-panel');
    var overlay = document.getElementById('overlay');
    var title = document.getElementById('result-panel-title');
    var body = document.getElementById('result-panel-body');
    var sc = s._scenes[sid];
    title.textContent = 'Grid size - ' + sid;
    var cols = sc.cols || 12;
    var rows = sc.rows || 6;
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
          s._scenes = data.scenes;
          s.renderSceneBar();
          if (sid === s._activeScene) {
            s.applySavedLayouts();
          }
          s.openSceneSettings();
        }
      });
    };
    document.getElementById('size-editor-cancel').onclick = function () {
      s.openSceneSettings();
    };
  };

  s.closeResultPanel = function () {
    if (typeof closeResultPanel === 'function') closeResultPanel();
  };

  //  settings dropdown 

  s._settingsMainHTML =
    '<div class="ctx-menu-item" data-action="scenes">\u{1F5A7}  Scene settings</div>' +
    '<div class="ctx-menu-item" data-action="extensions"><i data-feather="package" width="16" height="16"></i>  Extensions</div>' +
    '<div class="ctx-menu-separator"></div>' +
    '<div class="ctx-menu-item" data-action="window"><i data-feather="square" width="16" height="16"></i>  Window settings</div>' +
    '<div class="ctx-menu-separator"></div>' +
    '<div class="ctx-menu-item" id="autostart-item" data-action="autostart">\u{23F1}  Loading...</div>';

  s._settingsWindowHTML =
    '<div class="ctx-menu-item" data-action="back" style="color:var(--text-muted);font-size:10px">\u{2190}  Back</div>' +
    '<div class="ctx-menu-separator"></div>' +
    '<div class="ctx-menu-item" data-action="windowed">\u{1F5A5}  Windowed</div>' +
    '<div class="ctx-menu-item" data-action="frameless">\u{1F5A5}  Frameless</div>' +
    '<div class="ctx-menu-item" data-action="fullscreen">\u{1F5A5}  Fullscreen</div>';

  s.openSettingsDropdown = function (e) {
    e.stopPropagation();
    s.closeCtxMenu();
    s.closeSceneCtxMenu();
    s.closeSettingsDropdown();
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
          menu.innerHTML = s._settingsWindowHTML;
        } else if (action === 'back') {
          menu.innerHTML = s._settingsMainHTML;
        } else if (action === 'scenes') {
          s.closeSettingsDropdown();
          s.openSceneSettings();
        } else if (action === 'extensions') {
          s.closeSettingsDropdown();
          s.openExtensionsSettings();
        } else if (action === 'windowed' || action === 'frameless' || action === 'fullscreen') {
          s.closeSettingsDropdown();
          s.setWindowMode(action);
        } else if (action === 'autostart') {
          apiFetch('/api/autostart', { method: 'POST' }).then(function (res) {
            if (res && !res.error) s.updateAutostartItem(res);
          });
        }
      });
    }
    menu.innerHTML = s._settingsMainHTML;
    if (typeof feather !== 'undefined') feather.replace();
    menu.style.left = Math.min(rect.left, window.innerWidth - 200) + 'px';
    menu.style.top = Math.min(rect.bottom + 4, window.innerHeight - 100) + 'px';
    menu.classList.add('visible');
    apiFetch('/api/autostart').then(function (res) {
      if (res && !res.error) s.updateAutostartItem(res);
    });
  };

  s.updateAutostartItem = function (res) {
    var item = document.getElementById('autostart-item');
    if (!item) return;
    if (res.available === false) {
      item.textContent = '\u{23F1}  Start on boot (not available)';
      item.style.opacity = '0.4';
      return;
    }
    item.style.opacity = '1';
    item.textContent = res.enabled ? '\u2705  Start on boot' : '\u{2B1C}  Start on boot';
  };

  s.closeSettingsDropdown = function () {
    var menu = document.getElementById('settings-ctx-menu');
    if (menu) menu.classList.remove('visible');
  };

  s.setWindowMode = function (mode) {
    if (typeof currentWindowMode === 'undefined') { currentWindowMode = 'windowed'; }
    if (window.pywebview) {
      pywebview.api.set_window_mode(mode).then(function (applied) {
        currentWindowMode = mode;
        if (!applied && mode !== 'fullscreen') {
          s.showToast('Restart CoreFrame to apply');
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
  };
})();
