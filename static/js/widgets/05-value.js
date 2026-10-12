// The node this sub-widget type paints into, read from the construction marker.
function cfValueSelector(widgetEl) {
  var bodyEl = widgetEl && widgetEl.querySelector('.widget-sub-body');
  return (bodyEl && bodyEl.dataset.cfValueSel) || '.widget-value';
}

function updateWidgetValue(widgetEl, response) {
  if (!widgetEl) return;
  // Core wrote a value: the card has content, stop the loading shimmer.
  const ownerCard = widgetEl.closest('.widget-extension');
  if (ownerCard) cfClearLoadingState(ownerCard);
  // A missing value node means the extension renders this card itself.
  var valueSel = cfValueSelector(widgetEl);
  if (!widgetEl.querySelector(valueSel) && widgetEl.closest('.widget-body')) return;
  if (response && response.error) {
    // A timeout is not content: restore the empty marker so app.js retries it.
    var valEl = widgetEl.querySelector('.widget-value, .widget-list-items, .widget-terminal-output, .badge-label');
    if (valEl) {
      var isBadge = valEl.classList.contains('badge-label');
      valEl.textContent = isBadge ? 'Loading...' : (valEl.classList.contains('widget-list-items') ? '' : '--');
      valEl.style.color = '';
      var dotEl = widgetEl.querySelector('.badge-dot');
      if (dotEl) dotEl.className = 'badge-dot';
    }
    // Drop the memoized hash so the next real value is not suppressed.
    delete _widgetHash[widgetEl.dataset.extId + '-' + widgetEl.dataset.widgetId];
    console.warn('[EXT] widget value failed:', response.error);
    return;
  }

  try {
    _updateWidgetValueInner(widgetEl, response);
  } catch (e) {
    console.error('[EXT] Error updating widget:', e);
  }
}

function _cheapHash(val) {
  if (val === null || val === undefined) return 'null';
  if (typeof val !== 'object') return String(val);
  try {
    const s = JSON.stringify(val);
    if (s.length <= 200000) return s;
    let h = 0;
    for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
    return 'big:' + s.length + ':' + h.toString(16);
  } catch (e) {
    return 'err:' + String(val).slice(0, 200);
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
  const newHash = _cheapHash(val);

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
          const shown = items.slice(0, 300);
          container.innerHTML = shown.map(item => {
            if (typeof item === 'string') return '<div class="list-item"><span class="list-item-value">' + escapeHtml(item.slice(0, 500)) + '</span></div>';
            return '<div class="list-item"><span class="list-item-key">' + escapeHtml(item.label || item.key || '') + '</span><span class="list-item-value">' + escapeHtml(String(item.value || '').slice(0, 500)) + '</span></div>';
          }).join('') + (items.length > shown.length ? '<div class="list-item list-item-more">+' + (items.length - shown.length) + ' more</div>' : '');
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
        out.textContent = text.length > 100000 ? text.slice(-100000) : text;
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

