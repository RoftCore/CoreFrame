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
        // A text widget cannot display a structure; the extension paints it itself.
        if (val.label !== undefined) {
          el.textContent = val.label;
        } else {
          el.textContent = '--';
        }
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
