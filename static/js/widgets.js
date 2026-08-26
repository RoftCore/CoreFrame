const widgetHistory = {};
const _widgetHash = {};
const _progressTimers = {};
const _dropdownMenus = [];

if (!window._dropdownCloseAdded) {
  document.addEventListener('click', function () {
    var anyOpen = false;
    document.querySelectorAll('.widget-dd-menu:not([style*="display: none"])').forEach(function (m) {
      m.style.display = 'none';
      anyOpen = true;
    });
    if (anyOpen) {
      document.querySelectorAll('.widget-extension').forEach(function (c) {
        if (!c.querySelector('.widget-dd-menu:not([style*="display: none"])')) {
          c.style.overflow = '';
        }
      });
    }
  });
  window._dropdownCloseAdded = true;
}

function clearProgressTimers() {
  for (const key in _progressTimers) {
    clearTimeout(_progressTimers[key]);
    delete _progressTimers[key];
  }
}

function clearDropdownMenus() {
  for (var i = 0; i < _dropdownMenus.length; i++) {
    var m = _dropdownMenus[i];
    if (m.parentNode) m.parentNode.removeChild(m);
  }
  _dropdownMenus.length = 0;
}

// Restore chart history from localStorage so it survives page reload
(function loadPersistedHistory() {
  try {
    var saved = localStorage.getItem('coreframe-widget-history');
    if (saved) Object.assign(widgetHistory, JSON.parse(saved));
  } catch (_) {}
})();

function persistWidgetHistory() {
  try {
    localStorage.setItem('coreframe-widget-history', JSON.stringify(widgetHistory));
  } catch (_) {}
}

function startProgressPoll(extId, id, action, interval) {
  const key = extId + '-' + id;
  if (_progressTimers[key]) clearTimeout(_progressTimers[key]);
  function poll() {
    var fill = document.getElementById('prog-fill-' + extId + '-' + id);
    var info = document.getElementById('prog-info-' + extId + '-' + id);
    var cur = document.getElementById('prog-cur-' + extId + '-' + id);
    if (!fill) return;
    apiFetch('/api/extension/' + extId + '/' + action).then(function (response) {
      if (response && response.value) {
        var val = response.value;
        var status = val.status || '';
        var progress = typeof val.progress === 'number' ? val.progress : 0;
        var total = typeof val.total === 'number' ? val.total : 0;
        var current = val.current || '';
        var error = val.error || '';
        var pct = total > 0 ? Math.min(Math.round((progress / total) * 100), 100) : 0;
        fill.style.width = pct + '%';
        if (info) {
          if (status === 'completed') {
            info.textContent = 'Done! ' + total + ' track' + (total !== 1 ? 's' : '');
            info.className = 'widget-progress-info widget-progress-done';
          } else if (status === 'error') {
            info.textContent = error || 'Error';
            info.className = 'widget-progress-info widget-progress-error';
          } else if (status === 'idle' || status === '') {
            info.textContent = total > 0 ? progress + ' / ' + total : 'Ready';
            info.className = 'widget-progress-info';
          } else {
            info.textContent = total > 0 ? progress + ' / ' + total : '...';
            info.className = 'widget-progress-info widget-progress-running';
          }
        }
        if (cur) {
          cur.textContent = current;
          cur.style.display = current ? '' : 'none';
        }
      }
    });
    _progressTimers[key] = setTimeout(poll, interval);
  }
  _progressTimers[key] = setTimeout(poll, 200);
}

const EXT_DEFAULT_GRID = { w: 4, h: 2 };

function createExtensionCard(ext) {
  try {
    return _createExtensionCardInner(ext);
  } catch (e) {
    console.error('[EXT] Error creating card for ' + (ext.id || '?') + ':', e);
    var el = document.createElement('div');
    el.className = 'widget widget-extension ext-error-boundary';
    el.dataset.extId = ext.id || '';
    el.style.gridColumn = 'span 2';
    el.style.gridRow = 'span 1';
    el.style.minWidth = '0';
    el.style.minHeight = '0';
    el.style.display = 'flex';
    el.style.alignItems = 'center';
    el.style.justifyContent = 'center';
    el.style.border = '1px solid rgba(255,51,85,0.3)';
    el.style.borderRadius = 'var(--radius-md)';
    el.style.background = 'rgba(255,51,85,0.05)';
    el.style.color = 'var(--accent-red)';
    el.style.fontFamily = 'var(--font-mono)';
    el.style.fontSize = '11px';
    el.style.textAlign = 'center';
    el.style.padding = '12px';
    el.innerHTML = '<div><div style="font-size:18px;margin-bottom:4px">&#x26A0;</div>' +
      '<div>Error loading</div><div style="font-size:9px;color:var(--text-muted);margin-top:2px">' +
      escapeHtml(ext.name || ext.id || 'extension') + '</div></div>';
    return el;
  }
}

function _createExtensionCardInner(ext) {
  const { id: extId, name, widgets, grid_size, overlayable } = ext;
  const gs = grid_size || EXT_DEFAULT_GRID;

  const el = document.createElement('div');
  el.className = `widget widget-extension ext-${extId}`;
  el.dataset.extId = extId;
  el.dataset.overlayable = overlayable ? 'true' : 'false';
  if (overlayable) el.classList.add('widget-overlayable');
  el.style.gridColumn = `span ${gs.w}`;
  el.style.gridRow = `span ${gs.h}`;
  el.style.minWidth = '0';
  el.style.minHeight = '0';

  const scroll = ext.scroll;
  if (scroll) {
    el.classList.add('ext-scroll');
    if (scroll === 'x') el.classList.add('ext-scroll-x');
    else if (scroll === 'y') el.classList.add('ext-scroll-y');
    else if (scroll === 'both') el.classList.add('ext-scroll-both');
  }
  if (ext.hideScrollbar) {
    const hs = ext.hideScrollbar;
    if (hs === true || hs === 'both') el.classList.add('ext-scrollbar-hide');
    else if (hs === 'x') el.classList.add('ext-scrollbar-hide-x');
    else if (hs === 'y') el.classList.add('ext-scrollbar-hide-y');
  }

  el.style.overflow = 'hidden';

  const header = document.createElement('div');
  header.className = 'widget-header';
  header.textContent = name || extId;
  el.appendChild(header);

  const body = document.createElement('div');
  body.className = 'widget-body';

  if (widgets && widgets.length > 0) {
    for (const wDef of widgets) {
      try {
        const sub = createSubWidget(wDef, extId);
        body.appendChild(sub);
      } catch (e) {
        console.error('[EXT] Error creating sub-widget ' + (wDef.id || '?') + ':', e);
        var errEl = document.createElement('div');
        errEl.className = 'widget-sub';
        errEl.style.cssText = 'color:var(--accent-red);font-size:10px;padding:8px;text-align:center;';
        errEl.textContent = 'Widget error';
        body.appendChild(errEl);
      }
    }
  }

  el.appendChild(body);
  return el;
}

function createSubWidget(widgetDef, extId) {
  const { id, type, label, action } = widgetDef;

  const el = document.createElement('div');
  el.className = `widget-sub widget-${type}`;
  el.dataset.widgetId = id;
  el.dataset.extId = extId;
  el.dataset.action = action;
  el.dataset.format = widgetDef.format || '';

  const subLabel = document.createElement('div');
  subLabel.className = 'widget-sub-label';
  subLabel.textContent = label;
  el.appendChild(subLabel);

  const body = document.createElement('div');
  body.className = 'widget-sub-body';

  switch (type) {
    case 'text':
      body.innerHTML = '<div class="widget-value" id="val-' + id + '">--</div>';
      break;
    case 'badge':
      body.innerHTML = '<div class="widget-badge"><span class="badge-dot" id="dot-' + id + '"></span><span class="badge-label" id="lbl-' + id + '">Loading...</span></div>';
      break;
    case 'list':
      body.innerHTML = '<div class="widget-list-items" id="lst-' + id + '"></div>';
      break;
    case 'chart':
      body.innerHTML = `
        <div class="chart-container">
          <canvas id="chart-${extId}-${id}" width="120" height="60"></canvas>
          <div class="chart-value">--</div>
        </div>`;
      break;
    case 'terminal':
      body.className = 'widget-terminal-output';
      body.id = 'term-' + id;
      body.textContent = 'waiting for data...';
      break;
    case 'button':
      body.innerHTML = '<button class="widget-btn" data-ext="' + extId + '" data-action="' + action + '">' + escapeHtml(label) + '</button>';
      break;
    case 'input': {
      const ph = widgetDef.placeholder || '';
      const bl = widgetDef.button_label || 'Submit';
      const it = widgetDef.input_type || 'text';
      const fieldName = widgetDef.input_name || 'value';
      body.innerHTML =
        '<div class="widget-input-group">' +
          '<input type="' + it + '" class="widget-input" id="inp-' + extId + '-' + id + '" placeholder="' + escapeHtml(ph) + '">' +
          '<button class="widget-input-btn" id="btn-' + extId + '-' + id + '">' + escapeHtml(bl) + '</button>' +
        '</div>' +
        '<div class="widget-input-result" id="res-' + extId + '-' + id + '"></div>';
      const inp = body.querySelector('#inp-' + extId + '-' + id);
      const btn = body.querySelector('#btn-' + extId + '-' + id);
      if (inp && btn) {
        const origLabel = bl;
        const submit = function () {
          const val = inp.value.trim();
          if (!val) return;
          btn.disabled = true;
          btn.textContent = '...';
          var payload = {};
          payload[fieldName] = val;
          apiFetch('/api/extension/' + extId + '/' + action, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          }).then(function (data) {
            btn.disabled = false;
            btn.textContent = origLabel;
            var resEl = document.getElementById('res-' + extId + '-' + id);
            if (!resEl) return;
            if (data && data.error) {
              resEl.className = 'widget-input-result widget-input-error';
              resEl.textContent = 'Error: ' + data.error;
            } else if (data && data.value) {
              resEl.className = 'widget-input-result widget-input-success';
              resEl.textContent = typeof data.value === 'string' ? data.value : JSON.stringify(data.value);
            } else {
              resEl.className = 'widget-input-result widget-input-success';
              resEl.textContent = 'Done';
            }
          }).catch(function () {
            btn.disabled = false;
            btn.textContent = origLabel;
            var resEl = document.getElementById('res-' + extId + '-' + id);
            if (resEl) {
              resEl.className = 'widget-input-result widget-input-error';
              resEl.textContent = 'Request failed';
            }
          });
        };
        btn.addEventListener('click', submit);
        inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') submit(); });
      }
      break;
    }
    case 'progress': {
      const pi = widgetDef.poll_interval || 800;
      body.innerHTML =
        '<div class="widget-progress-wrap" id="prog-wrap-' + extId + '-' + id + '">' +
          '<div class="widget-progress-bar" id="prog-bar-' + extId + '-' + id + '">' +
            '<div class="widget-progress-fill" id="prog-fill-' + extId + '-' + id + '"></div>' +
          '</div>' +
          '<div class="widget-progress-info" id="prog-info-' + extId + '-' + id + '"></div>' +
          '<div class="widget-progress-current" id="prog-cur-' + extId + '-' + id + '"></div>' +
        '</div>';
      startProgressPoll(extId, id, action, pi);
      break;
    }
    case 'form': {
      const configAction = widgetDef.config_action;
      const saveAction = widgetDef.save_action;
      const fields = widgetDef.fields || [];
      var formBody = document.createElement('div');
      formBody.className = 'widget-form';
      formBody.innerHTML = '<div class="widget-form-loading">Loading...</div>';
      body.appendChild(formBody);
      if (configAction) {
        apiFetch('/api/extension/' + extId + '/' + configAction).then(function (data) {
          var config = (data && data.value) || {};
          var html = '<div class="widget-form-fields">';
          for (var fi = 0; fi < fields.length; fi++) {
            var f = fields[fi];
            var fval = config[f.id] !== undefined ? config[f.id] : (f['default'] || '');
            var escVal = escapeHtml(String(fval));
            html += '<label class="widget-form-label">' + escapeHtml(f.label || f.id) + '</label>';
            if (f.type === 'select') {
              html += '<select class="widget-form-select" data-field="' + f.id + '">';
              for (var j = 0; j < (f.options || []).length; j++) {
                var opt = f.options[j];
                var selected = String(opt.value) === String(fval) ? ' selected' : '';
                html += '<option value="' + escapeHtml(String(opt.value)) + '"' + selected + '>' + escapeHtml(opt.label || opt.value) + '</option>';
              }
              html += '</select>';
            } else if (f.type === 'checkbox') {
              html += '<div><input type="checkbox" class="widget-form-checkbox" data-field="' + f.id + '"' + (fval ? ' checked' : '') + '></div>';
            } else {
              html += '<div style="display:flex;gap:4px">';
              html += '<input type="' + (f.input_type || 'text') + '" class="widget-form-input" data-field="' + f.id + '" value="' + escVal + '">';
              if (f.browse_action) {
                html += '<button class="widget-form-browse" data-browse="' + f.id + '" data-browse-action="' + f.browse_action + '">\uD83D\uDCC1</button>';
              }
              html += '</div>';
            }
          }
          html += '</div>';
          html += '<div style="display:flex;gap:4px;margin-top:6px;justify-content:flex-end">';
          html += '<button class="widget-form-save">Save</button>';
          html += '</div>';
          html += '<div class="widget-form-msg" id="form-msg-' + extId + '-' + id + '"></div>';
          formBody.innerHTML = html;
          formBody.querySelectorAll('.widget-form-browse').forEach(function (btn) {
            btn.addEventListener('click', function () {
              var fid = btn.dataset.browse;
              var ba = btn.dataset.browseAction;
              apiFetch('/api/extension/' + extId + '/' + ba).then(function (d) {
                if (d && d.value) {
                  var inp = formBody.querySelector('[data-field="' + fid + '"]');
                  if (inp) inp.value = d.value;
                }
              });
            });
          });
          var saveBtn = formBody.querySelector('.widget-form-save');
          if (saveBtn && saveAction) {
            saveBtn.addEventListener('click', function () {
              var payload = {};
              formBody.querySelectorAll('[data-field]').forEach(function (el) {
                if (el.type === 'checkbox') payload[el.dataset.field] = el.checked;
                else payload[el.dataset.field] = el.value;
              });
              var msgEl = document.getElementById('form-msg-' + extId + '-' + id);
              apiFetch('/api/extension/' + extId + '/' + saveAction, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
              }).then(function (d) {
                if (msgEl) {
                  if (d && d.error) {
                    msgEl.className = 'widget-form-msg widget-form-error';
                    msgEl.textContent = d.error;
                  } else {
                    msgEl.className = 'widget-form-msg widget-form-success';
                    msgEl.textContent = 'Saved';
                    setTimeout(function () { if (msgEl) msgEl.textContent = ''; }, 2000);
                  }
                }
              });
            });
          }
        }).catch(function () {
          formBody.innerHTML = '<div class="widget-form-error-msg">Failed to load config</div>';
        });
      } else {
        formBody.innerHTML = '<div class="widget-form-error-msg">Missing config_action</div>';
      }
      break;
    }
    case 'dropdown': {
      const icon = widgetDef.icon || '\u2699';
      const pos = widgetDef.position || 'top-right';
      const tooltip = widgetDef.tooltip || '';
      const items = widgetDef.items || [];
      var ddTrigger = document.createElement('button');
      ddTrigger.className = 'widget-dd-trigger';
      ddTrigger.innerHTML = icon;
      if (tooltip) ddTrigger.title = tooltip;
      var ddMenu = document.createElement('div');
      ddMenu.className = 'widget-dd-menu';
      ddMenu.style.display = 'none';
      for (var di = 0; di < items.length; di++) {
        var ditem = items[di];
        if (ditem.type === 'separator') {
          var dsep = document.createElement('div');
          dsep.className = 'widget-dd-sep';
          ddMenu.appendChild(dsep);
        } else {
          var dEl = document.createElement('div');
          dEl.className = 'widget-dd-item';
          dEl.textContent = ditem.label;
          (function (action, method, data, target) {
            dEl.addEventListener('click', function (e) {
              e.stopPropagation();
              if (action === 'toggle') {
                var card = document.querySelector('.ext-' + extId);
                if (card && target) {
                  var t = card.querySelector(target);
                  if (t) t.style.display = t.style.display === 'none' ? '' : 'none';
                }
              } else {
                var url = '/api/extension/' + extId + '/' + action;
                if (method === 'POST') {
                  apiFetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: data ? JSON.stringify(data) : '{}' });
                } else {
                  apiFetch(url);
                }
              }
              ddMenu.style.display = 'none';
              var card = document.querySelector('.ext-' + extId);
              if (card) card.style.overflow = '';
            });
          })(ditem.action || '', ditem.method || 'GET', ditem.data, ditem.target);
          ddMenu.appendChild(dEl);
        }
      }
      if (pos === 'top-right' || pos === 'top-left') {
        ddTrigger.dataset.pos = pos;
        setTimeout(function () {
          var card = document.querySelector('.ext-' + extId);
          if (card) {
            ddTrigger.style.position = 'absolute';
            ddTrigger.style.top = '4px';
            ddTrigger.style[pos === 'top-right' ? 'right' : 'left'] = '4px';
            card.appendChild(ddTrigger);
            card.appendChild(ddMenu);
            ddMenu.style.position = 'absolute';
            ddMenu.style.top = '24px';
            ddMenu.style[pos === 'top-right' ? 'right' : 'left'] = '4px';
            ddMenu.style.zIndex = '20';
            _dropdownMenus.push(ddMenu);
          }
        }, 0);
      } else {
        body.appendChild(ddTrigger);
        body.appendChild(ddMenu);
        _dropdownMenus.push(ddMenu);
      }
      ddTrigger.addEventListener('click', function (e) {
        e.stopPropagation();
        var showing = ddMenu.style.display !== 'none';
        document.querySelectorAll('.widget-dd-menu').forEach(function (m) { m.style.display = 'none'; });
        if (!showing) {
          ddMenu.style.display = '';
          var card = document.querySelector('.ext-' + extId);
          if (card) card.style.overflow = 'visible';
        }
      });
      break;
    }
    default:
      body.innerHTML = '<div class="widget-value text-muted">Unknown</div>';
  }

  if (widgetDef.click_action) {
    el.dataset.clickAction = widgetDef.click_action;
    el.style.cursor = 'pointer';
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      if (typeof executeMenuAction === 'function') {
        let menuLabel = widgetDef.click_action;
        if (typeof window.extensionsData !== 'undefined' && window.extensionsData[extId] && window.extensionsData[extId].menu_items) {
          const found = window.extensionsData[extId].menu_items.find(m => m.action === widgetDef.click_action);
          if (found) menuLabel = found.label;
        }
        executeMenuAction(extId, widgetDef.click_action, menuLabel);
      }
    });
  }

  el.appendChild(body);
  return el;
}

function updateWidgetValue(widgetEl, response) {
  if (!widgetEl) return;
  if (response && response.error) {
    var valEl = widgetEl.querySelector('.widget-value, .widget-list-items, .widget-terminal-output, .badge-label');
    if (valEl) {
      valEl.textContent = '\u26A0 ' + response.error;
      valEl.style.color = 'var(--accent-red)';
    }
    return;
  }

  try {
    _updateWidgetValueInner(widgetEl, response);
  } catch (e) {
    console.error('[EXT] Error updating widget:', e);
  }
}

function _updateWidgetValueInner(widgetEl, response) {

  const extId = widgetEl.dataset.extId;
  const id = widgetEl.dataset.widgetId;
  const val = response !== undefined && response !== null ? response.value : undefined;
  const type =
    widgetEl.classList.contains('widget-text') ? 'text'
    : widgetEl.classList.contains('widget-badge') ? 'badge'
    : widgetEl.classList.contains('widget-list') ? 'list'
    : widgetEl.classList.contains('widget-chart') ? 'chart'
    : widgetEl.classList.contains('widget-terminal') ? 'terminal'
    : widgetEl.classList.contains('widget-button') ? 'button'
    : widgetEl.classList.contains('widget-input') ? 'input'
    : widgetEl.classList.contains('widget-progress') ? 'progress'
    : widgetEl.classList.contains('widget-form') ? 'form'
    : widgetEl.classList.contains('widget-dropdown') ? 'dropdown'
    : 'unknown';

  const hashKey = `${extId}-${id}`;
  const newHash = val !== null && val !== undefined ? (typeof val === 'object' ? JSON.stringify(val) : String(val)) : 'null';

  switch (type) {
    case 'text':
    case 'badge':
    case 'list': {
      if (_widgetHash[hashKey] === newHash) break;
      _widgetHash[hashKey] = newHash;
      if (type === 'text') {
        const el = widgetEl.querySelector('.widget-value');
        if (!el) break;
        formatValue(el, widgetEl.dataset.format, val);
      } else if (type === 'badge') {
        const dot = widgetEl.querySelector('.badge-dot');
        const lbl = widgetEl.querySelector('.badge-label');
        if (val && typeof val === 'object') {
          if (dot) dot.className = 'badge-dot ' + (val.status || 'warn');
          if (lbl) lbl.textContent = val.text || val.status || '--';
        } else {
          if (lbl) lbl.textContent = String(val);
        }
      } else if (type === 'list') {
        const container = widgetEl.querySelector('.widget-list-items');
        if (container) {
          const items = Array.isArray(val) ? val : [];
          container.innerHTML = items.map(item => {
            if (typeof item === 'string') return '<div class="list-item"><span class="list-item-value">' + escapeHtml(item) + '</span></div>';
            return '<div class="list-item"><span class="list-item-key">' + escapeHtml(item.label || item.key || '') + '</span><span class="list-item-value">' + escapeHtml(item.value || '') + '</span></div>';
          }).join('');
        }
      }
      break;
    }
    case 'chart': {
      const canvas = widgetEl.querySelector('canvas');
      const valueEl = widgetEl.querySelector('.chart-value');
      if (!canvas) break;

      let numericVal = 0;
      if (typeof val === 'number') numericVal = val;
      else if (val && typeof val === 'object' && 'percent' in val) numericVal = val.percent;

      const historyKey = `${extId}-${id}`;
      if (!widgetHistory[historyKey]) widgetHistory[historyKey] = [];
      widgetHistory[historyKey].push(numericVal);
      if (widgetHistory[historyKey].length > 30) widgetHistory[historyKey].shift();
      persistWidgetHistory();

      if (valueEl) formatValue(valueEl, widgetEl.dataset.format, val);

      const color = getComputedStyle(canvas).getPropertyValue('--chart-color').trim()
        || getComputedStyle(document.documentElement).getPropertyValue('--accent-blue').trim()
        || '#3498db';
      drawMiniChart(canvas, widgetHistory[historyKey], color);
      break;
    }
    case 'terminal': {
      const out = widgetEl.querySelector('.widget-terminal-output');
      if (out) {
        const text = typeof val === 'string' ? val : JSON.stringify(val, null, 2);
        out.textContent = text;
      }
      break;
    }
    case 'input':
    case 'progress':
    case 'form':
    case 'dropdown':
      break;
  }
}

function formatValue(el, format, val) {
  if (val === undefined || val === null) { el.textContent = '--'; return; }

  if (typeof val === 'object' && val.label) {
    if (typeof val.label === 'string' && /<[a-z][\s\S]*>/i.test(val.label)) {
      el.innerHTML = val.label;
    } else {
      el.textContent = val.label;
    }
    return;
  }

  switch (format) {
    case 'percent':
      el.textContent = formatPercent(typeof val === 'object' ? val.percent : val);
      break;
    case 'bytes':
      el.textContent = formatBytes(typeof val === 'number' ? val : val.bytes);
      break;
    case 'temp':
      el.textContent = formatTemp(typeof val === 'object' ? val.temp : val);
      break;
    default:
      if (typeof val === 'object') {
        el.textContent = JSON.stringify(val);
      } else {
        el.textContent = val;
      }
  }
}

function drawMiniChart(canvas, data, color) {
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * dpr;
  canvas.height = rect.height * dpr;
  ctx.scale(dpr, dpr);
  const w = rect.width;
  const h = rect.height;

  ctx.clearRect(0, 0, w, h);
  if (!data || data.length < 2) return;

  const range = 100;
  const stepX = w / 29;
  const startIdx = 30 - data.length;

  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.lineJoin = 'round';
  ctx.beginPath();

  data.forEach((v, i) => {
    const x = (startIdx + i) * stepX;
    const y = h - ((v / range) * h);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();

  ctx.lineTo(w, h);
  ctx.lineTo(startIdx * stepX, h);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, color + '66');
  grad.addColorStop(1, color + '00');
  ctx.fillStyle = grad;
  ctx.fill();

  ctx.strokeStyle = 'rgba(255,255,255,0.1)';
  ctx.lineWidth = 1;
  for (let i = 0; i <= 4; i++) {
    const y = (h / 4) * i;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }
  for (let i = 0; i <= 6; i++) {
    const x = (w / 6) * i;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
  }
}
