var _carouselExtensions = [];
var _carouselIndex = 0;
var _carouselConfig = [];

function getCarouselExts() {
  var all = Object.keys(window.extensionsData || {}).filter(function (id) { return id !== 'app_carousel'; });
  return _carouselConfig && _carouselConfig.length ? _carouselConfig.filter(function (id) { return all.indexOf(id) !== -1; }) : all;
}

function getExtIcon(extId) {
  var ext = window.extensionsData && extensionsData[extId];
  if (!ext) return '?';
  var icons = {
    'cpu': '\u2699', 'network': '\ud83c\udf10', 'vault': '\ud83d\udd12',
    'circle': '\u25cf', 'shield': '\ud83d\udee1\ufe0f', 'activity': '\u26a1',
    'monitor': '\ud83d\udcca', 'package': '\ud83d\udce6', 'zap': '\u26a1'
  };
  return icons[ext.icon] || '\u25cf';
}

function getExtDisplay(extId) {
  var ext = window.extensionsData && extensionsData[extId];
  return ext ? ext.name : extId;
}

function renderCarousel() {
  var extIds = getCarouselExts();
  if (!extIds.length) {
    document.querySelector('.carousel-btn').textContent = '?';
    return;
  }
  if (_carouselIndex >= extIds.length) _carouselIndex = 0;
  if (_carouselIndex < 0) _carouselIndex = extIds.length - 1;
  var currentId = extIds[_carouselIndex];
  var btn = document.querySelector('.carousel-btn');
  if (!btn) return;
  var icon = getExtIcon(currentId);
  var name = getExtDisplay(currentId);
  btn.innerHTML = '<span class="carousel-btn-icon">' + icon + '</span><span class="carousel-btn-label">' + name + '</span>';
  btn.dataset.extId = currentId;
}

function openCurrentExtension() {
  var btn = document.querySelector('.carousel-btn');
  if (!btn || !btn.dataset.extId) return;
  var extId = btn.dataset.extId;
  var ext = window.extensionsData && extensionsData[extId];
  if (!ext) return;
  var action, label;
  var menuItems = ext.menu_items || [];
  if (menuItems.length) {
    action = menuItems[0].action;
    label = menuItems[0].label;
  } else if (ext.widgets && ext.widgets.length) {
    action = ext.widgets[0].action;
    label = ext.widgets[0].label || ext.name;
  }
  if (action && typeof action === 'string' && action.length && typeof executeMenuAction === 'function') {
    executeMenuAction(extId, action, label);
  }
}

function showCarouselConfig() {
  var allExts = window.extensionsData || {};
  var selected = _carouselConfig.length ? _carouselConfig : Object.keys(allExts);

  var overlay = document.createElement('div');
  overlay.className = 'carousel-config-overlay';

  var dialog = document.createElement('div');
  dialog.className = 'carousel-config-dialog';

  var header = document.createElement('div');
  header.className = 'carousel-config-header';
  header.innerHTML = '<span>Configure Carousel</span><span style="font-size:10px;color:var(--text-muted)">Select extensions to show</span>';

  var list = document.createElement('div');
  list.className = 'carousel-config-list';

  var items = [];
  Object.keys(allExts).filter(function (id) { return id !== 'app_carousel'; }).forEach(function (extId) {
    var ext = allExts[extId];
    var checked = selected.indexOf(extId) !== -1;
    var item = document.createElement('label');
    item.className = 'carousel-config-item';
    item.innerHTML = '<input type="checkbox" value="' + extId + '"' + (checked ? ' checked' : '') + '>' +
      ext.name + ' <span class="text-muted" style="font-size:10px">(' + extId + ')</span>';
    list.appendChild(item);
    items.push(item);
  });

  var footer = document.createElement('div');
  footer.className = 'carousel-config-footer';

  var cancelBtn = document.createElement('button');
  cancelBtn.className = 'carousel-config-btn';
  cancelBtn.textContent = 'Cancel';
  cancelBtn.addEventListener('click', function () { overlay.remove(); });

  var saveBtn = document.createElement('button');
  saveBtn.className = 'carousel-config-btn carousel-config-btn-primary';
  saveBtn.textContent = 'Save';
  saveBtn.addEventListener('click', function () {
    var selectedIds = [];
    list.querySelectorAll('input[type="checkbox"]:checked').forEach(function (cb) {
      selectedIds.push(cb.value);
    });
    _carouselConfig = selectedIds;
    _carouselIndex = 0;
    renderCarousel();
    apiFetch('/api/extension/app_carousel/save_config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ extensions: selectedIds })
    });
    overlay.remove();
  });

  footer.appendChild(cancelBtn);
  footer.appendChild(saveBtn);

  dialog.appendChild(header);
  dialog.appendChild(list);
  dialog.appendChild(footer);
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);
}

function initCarousel() {
  // Load saved config
  apiFetch('/api/extension/app_carousel/get_config').then(function (data) {
    if (data && Array.isArray(data.value) && data.value.length) {
      _carouselConfig = data.value;
    }
    renderCarousel();
  });

  // Build UI
  var widget = document.querySelector('.ext-app_carousel');
  if (!widget) return;
  var body = widget.querySelector('.widget-body');
  if (!body) return;
  body.innerHTML =
    '<button class="carousel-arrow" id="carousel-prev">\u25C0</button>' +
    '<div style="position:relative;display:flex;align-items:center;justify-content:center">' +
      '<button class="carousel-btn" id="carousel-open"></button>' +
      '<button class="carousel-edit-btn" id="carousel-edit" title="Configure">\u2699</button>' +
    '</div>' +
    '<button class="carousel-arrow" id="carousel-next">\u25B6</button>';

  document.getElementById('carousel-prev').addEventListener('click', function () {
    var extIds = getCarouselExts();
    if (extIds.length) {
      _carouselIndex = (_carouselIndex - 1 + extIds.length) % extIds.length;
      renderCarousel();
    }
  });

  document.getElementById('carousel-next').addEventListener('click', function () {
    var extIds = getCarouselExts();
    if (extIds.length) {
      _carouselIndex = (_carouselIndex + 1) % extIds.length;
      renderCarousel();
    }
  });

  document.getElementById('carousel-open').addEventListener('click', openCurrentExtension);

  document.getElementById('carousel-edit').addEventListener('click', function (e) {
    e.stopPropagation();
    showCarouselConfig();
  });
}

(function waitForInit() {
  if (typeof extensionsData !== 'undefined' && Object.keys(extensionsData).length) {
    initCarousel();
    return;
  }
  setTimeout(waitForInit, 200);
})();
