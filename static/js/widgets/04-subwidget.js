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
  // Each type overwrites this with the node it actually paints into.
  body.dataset.cfValueSel = '.widget-value';

  switch (type) {
    case 'text':
      body.innerHTML = '<div class="widget-value" id="val-' + id + '">--</div>';
      break;
    case 'badge':
      body.dataset.cfValueSel = '.badge-label';
      body.innerHTML = '<div class="widget-badge"><span class="badge-dot" id="dot-' + id + '"></span><span class="badge-label" id="lbl-' + id + '">Loading...</span></div>';
      break;
    case 'list':
      body.dataset.cfValueSel = '.widget-list-items';
      body.innerHTML = '<div class="widget-list-items" id="lst-' + id + '"></div>';
      break;
    case 'chart':
      body.dataset.cfValueSel = '.chart-value';
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
                html += '<button class="widget-form-browse" data-browse="' + f.id + '" data-browse-action="' + f.browse_action + '"><i data-feather="folder" width="14" height="14"></i></button>';
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
          if (typeof feather !== 'undefined') feather.replace();
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
      const icon = widgetDef.icon || 'settings';
      const pos = widgetDef.position || 'top-right';
      const tooltip = widgetDef.tooltip || '';
      const items = widgetDef.items || [];
      var ddTrigger = document.createElement('button');
      ddTrigger.className = 'widget-dd-trigger';
      if (icon && icon.startsWith('/')) {
        ddTrigger.innerHTML = '<img src="' + icon + '" alt="" style="width:16px;height:16px">';
      } else {
        ddTrigger.innerHTML = '<i data-feather="' + icon + '" width="16" height="16"></i>';
      }
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

