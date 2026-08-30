(function () {
  'use strict';

  var s = window.__wc;

  //  context menu 

  s.closeCtxMenu = function () {
    const m = document.getElementById('ctx-menu');
    if (m) m.classList.remove('visible');
    document.querySelectorAll('.ctx-target').forEach(function (el) { return el.classList.remove('ctx-target'); });
  };

  function getOrCreateCtxMenu() {
    let m = document.getElementById('ctx-menu');
    if (m) return m;
    m = document.createElement('div');
    m.id = 'ctx-menu';
    m.className = 'ctx-menu';
    m.innerHTML =
      '<div class="ctx-menu-item" data-action="hide"><i data-feather="trash-2" width="16" height="16"></i>  Hide widget</div>' +
      '<div class="ctx-menu-item" data-action="edit"><i data-feather="edit" width="16" height="16"></i>  Edit widget</div>' +
      '<div class="ctx-menu-item" data-action="style" id="ctx-style-btn" style="display:none"><i data-feather="layers" width="16" height="16"></i> Change Style</div>' +
      '<div class="ctx-menu-separator"></div>' +
      '<div class="ctx-menu-item" data-action="show" id="ctx-show-btn" style="display:none"><i data-feather="eye" width="16" height="16"></i>  Show hidden widgets...</div>' +
      '<div class="ctx-menu-item" data-action="install" id="ctx-install-btn" style="display:none"><i data-feather="download" width="16" height="16"></i>  Install extension...</div>';
    document.body.appendChild(m);

    m.addEventListener('click', function (e) {
      const item = e.target.closest('.ctx-menu-item');
      if (!item) return;
      const action = item.dataset.action;
      const target = document.querySelector('.ctx-target');
      if (action === 'show') {
        s.showHiddenPanel();
      } else if (action === 'install') {
        var btn = document.getElementById('btn-install');
        if (btn) btn.click();
      } else if (action === 'style') {
        s.showStylePicker(target);
      } else if (target) {
        if (action === 'hide') s.hideWidget(target);
        else if (action === 'edit') s.enterEditMode();
      }
      s.closeCtxMenu();
    });

    return m;
  }

  s.openCtxMenu = function (e, widget) {
    s.closeCtxMenu();
    document.querySelectorAll('.ctx-target').forEach(function (el) { return el.classList.remove('ctx-target'); });
    widget.classList.add('ctx-target');

    const menu = getOrCreateCtxMenu();
    menu.querySelectorAll('[data-action="hide"],[data-action="edit"]').forEach(function (el) { return el.style.display = 'flex'; });
    menu.querySelector('.ctx-menu-separator').style.display = 'block';
    const hidden = s.getHidden();
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
    if (typeof feather !== 'undefined') feather.replace();
  };

  s.openEmptyCtxMenu = function (e) {
    const hidden = s.getHidden();
    const hasHidden = Object.keys(hidden).length > 0;
    s.closeCtxMenu();
    document.querySelectorAll('.ctx-target').forEach(function (el) { return el.classList.remove('ctx-target'); });
    const menu = getOrCreateCtxMenu();
    menu.querySelectorAll('[data-action="hide"],[data-action="edit"],[data-action="style"]').forEach(function (el) { return el.style.display = 'none'; });
    menu.querySelector('.ctx-menu-separator').style.display = 'none';
    document.getElementById('ctx-show-btn').style.display = hasHidden ? 'flex' : 'none';
    document.getElementById('ctx-install-btn').style.display = hasHidden ? 'none' : 'flex';
    menu.style.left = Math.min(e.clientX, window.innerWidth - 200) + 'px';
    menu.style.top = Math.min(e.clientY, window.innerHeight - 100) + 'px';
    menu.classList.add('visible');
    if (typeof feather !== 'undefined') feather.replace();
  };

  //  extensions settings 

  s.openExtensionsSettings = function () {
    var panel = document.getElementById('result-panel');
    var overlay = document.getElementById('overlay');
    var title = document.getElementById('result-panel-title');
    var body = document.getElementById('result-panel-body');
    title.textContent = 'Extensions';

    var existingSearch = panel.querySelector('.result-panel-search');
    if (existingSearch) existingSearch.remove();

    var searchDiv = document.createElement('div');
    searchDiv.className = 'result-panel-search';
    searchDiv.innerHTML = '<input type="text" id="ext-settings-search" placeholder="Search extensions...">';
    panel.querySelector('.result-panel-header').insertAdjacentElement('afterend', searchDiv);

    body.innerHTML = '<div id="ext-settings-list"></div>';

    function renderExtList(filter) {
      var list = document.getElementById('ext-settings-list');
      if (!list) return;
      var data = window.extensionsData || {};
      var ids = Object.keys(data).sort();
      var f = (filter || '').toLowerCase();
      var html = '<div class="ext-grid">';
      var count = 0;
      ids.forEach(function (id) {
        var ext = data[id];
        var name = ext.name || id;
        if (f && name.toLowerCase().indexOf(f) < 0 && id.toLowerCase().indexOf(f) < 0) return;
        count++;
        var isError = ext.loadError ? true : false;
        var icon = ext.icon || '';
        var iconHtml = window.renderExtIconHtml ? window.renderExtIconHtml(icon, id) : '<i data-feather="box"></i>';
        var cardClass = 'ext-card' + (isError ? ' ext-card-error' : '');
        html += '<div class="' + cardClass + '" data-ext="' + id + '">';
        html += '<div class="ext-card-icon">' + iconHtml + '</div>';
        html += '<div class="ext-card-name">' + escapeHtml(name) + '</div>';
        if (isError) {
          html += '<div class="ext-card-meta" style="color:var(--accent-red);max-width:100%;white-space:normal;text-align:center;">' + escapeHtml(ext.loadError) + '</div>';
        } else {
          html += '<div class="ext-card-meta">v' + escapeHtml(ext.version || '?') + (ext.author ? ' &middot; ' + escapeHtml(ext.author) : '') + '</div>';
        }
        html += '<div class="ext-card-actions"><button class="ext-card-btn ext-card-btn-danger ext-settings-del" data-ext="' + id + '">Delete</button></div>';
        html += '</div>';
      });
      html += '</div>';
      if (!count) html = '<div style="text-align:center;padding:20px;color:var(--text-muted);font-size:12px;">No extensions found.</div>';
      list.innerHTML = html;

      if (window.feather) window.feather.replace();

      list.querySelectorAll('.ext-settings-del').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
          e.stopPropagation();
          var eid = btn.dataset.ext;
          s.showDeleteExtensionConfirm(eid);
        });
      });
    }

    renderExtList('');

    document.getElementById('ext-settings-search').addEventListener('input', function () {
      renderExtList(this.value);
    });

    panel.classList.add('open');
    overlay.classList.add('open');
  };

  s.showDeleteExtensionConfirm = function (extId, onDone) {
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
    panel.classList.add('open');
    overlay.classList.add('open');
    document.getElementById('confirm-ext-del-yes').onclick = function () {
      apiFetch('/api/extensions/' + encodeURIComponent(extId), { method: 'DELETE' }).then(function (data) {
        if (data && data.error) {
          s.showToast('Error: ' + data.error);
          return;
        }
        s.showToast('Extension deleted: ' + name);
        apiFetch('/api/extensions').then(function (newData) {
          if (newData && !newData.error) {
            window.extensionsData = newData;
            if (typeof buildSidebar !== 'undefined') buildSidebar(newData);
            var w = document.getElementById('main-content');
            if (w) w.querySelector('.widget-extension.ext-' + extId)?.remove();
            if (typeof refreshAllWidgets !== 'undefined') refreshAllWidgets(newData);
            if (typeof startWidgetIntervals !== 'undefined') startWidgetIntervals(newData);
          }
          s.loadState().then(function () {
            if (window.__widgetControl && window.__widgetControl.autoAddExtensions) window.__widgetControl.autoAddExtensions();
            s.applyHiddenState();
            s.applySavedLayouts();
            s.applyWidgetStyles();
          });
          if (typeof onDone === 'function') {
            s.closeResultPanel();
            onDone();
          } else {
            s.openExtensionsSettings();
          }
        });
      });
    };
    document.getElementById('confirm-ext-del-no').onclick = function () {
      if (typeof onDone === 'function') {
        s.closeResultPanel();
        onDone();
      } else {
        s.openExtensionsSettings();
      }
    };
  };

  //  style picker 

  s.showStylePicker = function (widget) {
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

    var sw = s.sceneWidgets();
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
        s.changeWidgetStyle(extId, styleName);
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
        s.showToast('Style changed to ' + label);
      });
    });

    panel.classList.add('open');
    overlay.classList.add('open');
  };

  s.changeWidgetStyle = function (extId, styleName) {
    if (!extId || !s.currentScene()) return;
    s.currentScene().widgets[extId] = s.currentScene().widgets[extId] || {};
    s.currentScene().widgets[extId].style = styleName;
    s.persistScenes();
    s.applyStyleToWidget(extId);
  };

  s.applyStyleToWidget = function (extId) {
    var sw = s.sceneWidgets();
    var w = document.querySelector('.widget-extension.ext-' + extId);
    if (!w || !sw[extId]) return;
    w.className = w.className.replace(/\bwidget-style-\S+/g, '').trim();
    var style = sw[extId].style;
    if (style && style !== 'default') {
      w.classList.add('widget-style-' + style);
    }
  };

  s.applyWidgetStyles = function () {
    var sw = s.sceneWidgets();
    for (var extId in sw) {
      if (sw.hasOwnProperty(extId) && sw[extId].style) {
        s.applyStyleToWidget(extId);
      }
    }
  };

  //  icon picker 

  s.showIconPicker = function (sid) {
    var panel = document.getElementById('result-panel');
    var overlay = document.getElementById('overlay');
    var title = document.getElementById('result-panel-title');
    var body = document.getElementById('result-panel-body');
    var sc = s._scenes[sid];
    title.textContent = 'Change icon - ' + sid;
    var currentLabel = sc.label || 'file';
    var currentImage = sc.image || '';
    var featherNames = [
      'activity','airplay','alert-circle','alert-triangle','align-center',
      'align-justify','align-left','align-right','anchor','aperture',
      'archive','arrow-down','arrow-down-circle','arrow-down-left','arrow-down-right',
      'arrow-left','arrow-left-circle','arrow-right','arrow-right-circle','arrow-up',
      'arrow-up-circle','arrow-up-left','arrow-up-right','at-sign','award',
      'bar-chart-2','battery','battery-charging','bell','bluetooth',
      'bold','book','bookmark','box','briefcase',
      'calendar','camera','cast','check','check-circle',
      'check-square','chevron-down','chevron-left','chevron-right','chevron-up',
      'chrome','circle','clipboard','clock','cloud',
      'cloud-drizzle','cloud-lightning','cloud-rain','cloud-snow','code',
      'codepen','coffee','command','compass','copy',
      'cpu','credit-card','crop','crosshair','database',
      'delete','disc','divide','dollar-sign','download',
      'droplet','edit','edit-2','edit-3','external-link',
      'eye','eye-off','facebook','fast-forward','feather',
      'figma','file','file-text','film','filter',
      'flag','folder','frown','gift','git-branch',
      'git-commit','git-merge','git-pull-request','github','gitlab',
      'globe','grid','hard-drive','hash','headphones',
      'heart','help-circle','hexagon','home','image',
      'inbox','info','instagram','italic','key',
      'layers','layout','life-buoy','link-2','linkedin',
      'list','loader','lock','log-in','log-out',
      'mail','map','map-pin','maximize','maximize-2',
      'meh','menu','message-circle','message-square','mic',
      'minimize','minimize-2','minus','minus-circle','monitor',
      'moon','more-horizontal','more-vertical','move','music',
      'navigation','navigation-2','npm','octagon','package',
      'paperclip','pause','pause-circle','pen-tool','percent',
      'phone','phone-call','phone-forwarded','phone-incoming','phone-missed',
      'phone-off','phone-outgoing','pie-chart','play','play-circle',
      'plus','plus-circle','plus-square','pocket','power',
      'printer','radio','refresh-ccw','refresh-cw','repeat',
      'rewind','rss','save','scissors','search',
      'send','server','settings','share-2','shield',
      'shield-off','shopping-bag','shopping-cart','shuffle','sidebar',
      'skip-back','skip-forward','slack','slash','sliders',
      'smartphone','smile','snowflake','sort','speaker',
      'square','star','stop-circle','sun','sunrise',
      'sunset','tablet','tag','target','terminal',
      'thermometer','thumbs-down','thumbs-up','toggle-left','toggle-right',
      'tool','trash','trash-2','triangle','truck',
      'tv','twitch','twitter','type','umbrella',
      'underline','undo','unlock','upload','upload-cloud',
      'user','user-check','user-minus','user-plus','users',
      'user-x','video','video-off','voicemail','volume',
      'volume-1','volume-2','volume-x','watch','wifi',
      'wind','x','x-circle','x-octagon','x-square',
      'youtube','zap','zap-off'
    ]
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
      var active = (!currentImage && currentLabel === ic) ? ';border-color:var(--accent-cyan);background:rgba(0,212,255,0.25);' : '';
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
        if (data && !data.error) { s._scenes = data.scenes; s.renderSceneBar(); }
      });
    }

    body.querySelectorAll('.icon-picker-item').forEach(function (el) {
      el.addEventListener('click', function () {
        body.querySelectorAll('.icon-picker-item').forEach(function (e) { e.style.borderColor = 'transparent'; e.style.background = ''; });
        el.style.borderColor = 'var(--accent-cyan)';
        el.style.background = 'rgba(0,212,255,0.25)';
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
          if (data && !data.error) { s._scenes = data.scenes; s.renderSceneBar(); s.openSceneSettings(); }
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
    if (!fileInput) {
      fileInput = document.createElement('input');
      fileInput.id = 'scene-img-input';
      fileInput.type = 'file';
      fileInput.accept = 'image/*';
      fileInput.style.display = 'none';
      document.body.appendChild(fileInput);
    }
    fileInput.onchange = function () {
      if (!fileInput.files || !fileInput.files[0]) return;
      doUpload(fileInput.files[0]);
    };

    document.getElementById('icon-picker-cancel').addEventListener('click', function () {
      s.openSceneSettings();
    });

    panel.classList.add('open');
    overlay.classList.add('open');
  };
})();
