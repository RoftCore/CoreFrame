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
        // Only the text widget has room for a structure; anywhere else stays a single line.
        if (el.classList.contains('widget-value')) formatStructure(el, val);
        else el.textContent = '--';
      } else {
        el.textContent = val;
      }
  }
}

var CF_STRUCT_ROWS = 12;

function _structScalar(v) {
  if (v === null || v === undefined) return '';
  if (typeof v === 'object') {
    var s;
    try { s = JSON.stringify(v); } catch (e) { return String(v); }
    return s.length > 80 ? s.slice(0, 79) + '…' : s;
  }
  var t = String(v);
  return t.length > 200 ? t.slice(0, 199) + '…' : t;
}

// A structure used to collapse to '--', which hid a payload the backend had already answered.
function formatStructure(el, val) {
  var rows;
  if (Array.isArray(val)) {
    rows = val.map(function (item, i) {
      if (item && typeof item === 'object' && !Array.isArray(item)) {
        return [item.label || item.key || item.name || ('#' + (i + 1)), item.value];
      }
      return ['#' + (i + 1), item];
    });
  } else {
    rows = Object.keys(val).map(function (k) { return [k, val[k]]; });
  }
  var shown = rows.slice(0, CF_STRUCT_ROWS);
  el.innerHTML = shown.map(function (r) {
    return '<div class="list-item"><span class="list-item-key">' + escapeHtml(String(r[0])) +
      '</span><span class="list-item-value">' + escapeHtml(_structScalar(r[1])) + '</span></div>';
  }).join('') + (rows.length > shown.length
    ? '<div class="list-item list-item-more">+' + (rows.length - shown.length) + ' more</div>' : '');
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
