const widgetHistory = {};

function createWidget(widgetDef, extId) {
  const { id, type, label, action } = widgetDef;
  const el = document.createElement('div');
  el.className = `widget widget-${type}`;
  el.dataset.widgetId = id;
  el.dataset.extId = extId;
  el.dataset.action = action;

  const header = document.createElement('div');
  header.className = 'widget-header';
  header.innerHTML = `<span>${escapeHtml(label)}</span>`;
  el.appendChild(header);

  const body = document.createElement('div');
  body.className = 'widget-body';

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
          <canvas id="chart-${extId}-${id}" width="280" height="100"></canvas>
          <div class="chart-value">--</div>
        </div>
      `;
      break;
    case 'terminal':
      body.className = 'widget-terminal-output';
      body.id = 'term-' + id;
      body.textContent = '> waiting for data...';
      el.classList.add('widget-terminal');
      break;
    case 'iframe':
      body.innerHTML = '<iframe id="ifr-' + id + '" style="width:100%;height:200px;border:none;border-radius:4px;background:#000;"></iframe>';
      break;
    case 'button':
      body.innerHTML = '<button class="widget-btn" data-ext="' + extId + '" data-action="' + action + '">' + escapeHtml(label) + '</button>';
      break;
    default:
      body.innerHTML = '<div class="widget-value text-muted">Unknown type: ' + type + '</div>';
  }

  el.appendChild(body);
  return el;
}

function updateWidgetValue(widgetEl, response) {
  if (!widgetEl || response.error) return;
  const type = widgetEl.classList.contains('widget-text') ? 'text'
    : widgetEl.classList.contains('widget-badge') ? 'badge'
    : widgetEl.classList.contains('widget-list') ? 'list'
    : widgetEl.classList.contains('widget-chart') ? 'chart'
    : widgetEl.classList.contains('widget-terminal') ? 'terminal'
    : widgetEl.classList.contains('widget-button') ? 'button'
    : 'unknown';

  const extId = widgetEl.dataset.extId;
  const id = widgetEl.dataset.widgetId;
  const val = response.value;

  switch (type) {
    case 'text': {
      const el = widgetEl.querySelector('.widget-value');
      if (!el) break;
      formatValue(el, id, val);
      break;
    }
    case 'badge': {
      const dot = widgetEl.querySelector('.badge-dot');
      const lbl = widgetEl.querySelector('.badge-label');
      if (val && typeof val === 'object') {
        if (dot) { dot.className = 'badge-dot ' + (val.status || 'warn'); }
        if (lbl) lbl.textContent = val.text || val.status || '--';
      } else {
        if (lbl) lbl.textContent = String(val);
      }
      break;
    }
    case 'list': {
      const container = widgetEl.querySelector('.widget-list-items');
      if (container) {
        const items = Array.isArray(val) ? val : [];
        container.innerHTML = items.map(item => {
          if (typeof item === 'string') return '<div class="list-item"><span class="list-item-value">' + escapeHtml(item) + '</span></div>';
          return '<div class="list-item"><span class="list-item-key">' + escapeHtml(item.label || item.key || '') + '</span><span class="list-item-value">' + escapeHtml(item.value || '') + '</span></div>';
        }).join('');
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
      else if (val && typeof val === 'object' && 'load' in val) numericVal = val.load;

      const historyKey = `${extId}-${id}`;
      if (!widgetHistory[historyKey]) widgetHistory[historyKey] = [];
      widgetHistory[historyKey].push(numericVal);
      if (widgetHistory[historyKey].length > 30) widgetHistory[historyKey].shift();

      if (valueEl) formatValue(valueEl, id, val);
      
      const colors = {
        'cpu': '#00d4ff', // Cyan
        'ram': '#6644ff', // Purple
        'disk': '#00ff88', // Green
        'gpu': '#ffbb00'  // Yellow
      };
      const color = colors[id] || getComputedStyle(document.documentElement).getPropertyValue('--accent-blue').trim() || '#3498db';
      drawMiniChart(canvas, widgetHistory[historyKey], color);
      break;
    }
    case 'terminal': {
      const out = widgetEl.querySelector('.widget-terminal-output');
      if (out) {
        const text = typeof val === 'string' ? val : JSON.stringify(val, null, 2);
        out.textContent = '> ' + text;
      }
      break;
    }
  }
}

function formatValue(el, id, val) {
  if (val === undefined || val === null) {
    el.textContent = '--';
    return;
  }

  // Common system monitor formatting
  if (id === 'cpu') {
    el.textContent = formatPercent(typeof val === 'object' ? val.percent : val);
  } else if (id === 'ram') {
    if (typeof val === 'object') {
      el.textContent = formatPercent(val.percent) + ' (' + formatBytes(val.used) + ')';
    } else {
      el.textContent = formatPercent(val);
    }
  } else if (id === 'disk') {
    if (typeof val === 'object') {
      el.textContent = formatPercent(val.percent) + ' (' + formatBytes(val.free) + ' free)';
    } else {
      el.textContent = formatBytes(val);
    }
  } else if (id === 'gpu') {
    if (typeof val === 'object') {
      el.innerHTML = `<span class="text-yellow">${formatTemp(val.temp)}</span> <span class="text-blue">${formatPercent(val.load)}</span>`;
    } else {
      el.textContent = val;
    }
  } else if (typeof val === 'object') {
    el.textContent = JSON.stringify(val);
  } else {
    el.textContent = val;
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

  // Gradient fill
  ctx.lineTo(w, h);
  ctx.lineTo(startIdx * stepX, h);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, color + '66');
  grad.addColorStop(1, color + '00');
  ctx.fillStyle = grad;
  ctx.fill();

  // Grid lines
  ctx.strokeStyle = 'rgba(255,255,255,0.1)';
  ctx.lineWidth = 1;
  // Horizontal
  for (let i = 0; i <= 4; i++) {
    const y = (h / 4) * i;
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
    ctx.stroke();
  }
  // Vertical
  for (let i = 0; i <= 6; i++) {
    const x = (w / 6) * i;
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
    ctx.stroke();
  }
}
