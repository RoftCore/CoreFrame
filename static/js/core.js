let extensionsData = {};
let widgetTimers = {};

// Sys-grid history for mini charts
const sysHistory = { cpu: [], ram: [], gpu: [], disk: [] };

document.addEventListener('DOMContentLoaded', async () => {
  clockTick();
  setInterval(clockTick, 1000);

  initResultPanel();
  initWebSocket();

  const data = await apiFetch('/api/extensions');
  if (data.error) {
    document.getElementById('main-content').innerHTML = `<div class="loading"><div class="spinner"></div>Failed to connect: ${escapeHtml(data.error)}</div>`;
    return;
  }
  extensionsData = data;
  buildSidebar(data);
  renderWidgets(data);

  // Start HUD polling (IP, VPN, ports)
  refreshHud();
  setInterval(refreshHud, 5000);
});

function renderWidgets(data) {
  const container = document.getElementById('main-content');
  container.innerHTML = '';

  const categories = {};
  for (const [extId, ext] of Object.entries(data)) {
    if (extId === 'system_monitor' || extId === 'network_monitor') continue;
    const cat = ext.category || 'general';
    if (!categories[cat]) categories[cat] = [];
    categories[cat].push({ ...ext, id: extId });
  }

  for (const [cat, exts] of Object.entries(categories)) {
    const group = document.createElement('div');
    group.className = 'ext-group';

    const header = document.createElement('div');
    header.className = 'ext-group-header';
    header.textContent = cat;
    group.appendChild(header);

    const grid = document.createElement('div');
    grid.className = 'widget-grid';

    for (const ext of exts) {
      for (const wDef of (ext.widgets || [])) {
        const widgetEl = createWidget(wDef, ext.id);
        grid.appendChild(widgetEl);
      }
    }

    group.appendChild(grid);
    container.appendChild(group);
  }

  refreshAllWidgets(data);
  startWidgetIntervals(data);
}

function refreshAllWidgets(data) {
  for (const [extId, ext] of Object.entries(data)) {
    for (const wDef of (ext.widgets || [])) {
      refreshWidget(extId, wDef);
    }
  }
}

async function refreshWidget(extId, wDef) {
  const el = document.querySelector(`[data-widget-id="${wDef.id}"][data-ext-id="${extId}"]`);
  if (!el) return;
  const response = await apiFetch(`/api/extension/${extId}/${wDef.action}`);
  updateWidgetValue(el, response);
}

function startWidgetIntervals(data) {
  for (const timer in widgetTimers) clearInterval(widgetTimers[timer]);

  for (const [extId, ext] of Object.entries(data)) {
    if (extId === 'system_monitor') continue;
    const interval = ext.refresh_interval || 5000;
    for (const wDef of (ext.widgets || [])) {
      const key = `${extId}-${wDef.id}`;
      widgetTimers[key] = setInterval(() => refreshWidget(extId, wDef), interval);
    }
  }
}

// --- HUD Network (top-right) ---
async function refreshHud() {
  const [ipResp, vpnResp, portsResp] = await Promise.all([
    apiFetch('/api/extension/network_monitor/get_ip'),
    apiFetch('/api/extension/network_monitor/check_vpn'),
    apiFetch('/api/extension/network_monitor/get_open_ports')
  ]);

  // IP
  const ipVal = document.getElementById('hud-ip-value');
  if (ipVal) ipVal.textContent = ipResp.value || '--';

  // IP click to force-refresh
  const ipItem = document.getElementById('hud-ip');
  if (ipItem) {
    ipItem.onclick = async () => {
      const resp = await apiFetch('/api/extension/network_monitor/force_ip');
      if (ipVal) ipVal.textContent = resp.value || '--';
    };
  }

  // VPN
  const vpnDot = document.getElementById('hud-vpn-dot');
  const vpnVal = document.getElementById('hud-vpn-value');
  if (vpnResp.value && typeof vpnResp.value === 'object') {
    const status = vpnResp.value.status || 'warn';
    if (vpnDot) { vpnDot.className = 'hud-dot ' + status; }
    if (vpnVal) {
      vpnVal.textContent = vpnResp.value.text || status;
      vpnVal.className = 'hud-value';
      if (status === 'ok') vpnVal.classList.add('vpn-ok');
      else if (status === 'warn') vpnVal.classList.add('vpn-warn');
      else vpnVal.classList.add('vpn-off');
    }
  }

  // Ports
  const portsVal = document.getElementById('hud-ports-value');
  if (portsVal) {
    const ports = Array.isArray(portsResp.value) ? portsResp.value : [];
    const open = ports.filter(p => p.value === 'OPEN').length;
    portsVal.textContent = open > 0 ? open + ' open' : '0';
  }
}

// --- WebSocket (system monitor realtime) ---
function initWebSocket() {
  const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
  const wsUrl = `${protocol}//${location.host}`;
  const socket = io(wsUrl);

  socket.on('connect', () => {
    document.getElementById('connection-dot').className = 'hud-dot ok';
  });

  socket.on('history', (data) => {
    for (const [id, values] of Object.entries(data)) {
      if (!sysHistory[id]) sysHistory[id] = [];
      sysHistory[id] = values;
      const barColors = {
        cpu: 'var(--accent-cyan)',
        ram: 'var(--accent-purple)',
        gpu: 'var(--accent-yellow)',
        disk: 'var(--accent-green)'
      };
      const canvas = document.getElementById(`sys-${id}-chart`);
      if (canvas && values.length > 0) {
        const color = getComputedStyle(document.documentElement).getPropertyValue(barColors[id].replace('var(', '').replace(')', '')).trim() || '#00d4ff';
        drawSysMiniChart(canvas, values, color);
        const percent = values[values.length - 1];
        const valueEl = document.getElementById(`sys-${id}-value`);
        if (valueEl) valueEl.textContent = percent.toFixed(1) + '%';
        const barEl = document.getElementById(`sys-${id}-bar`);
        if (barEl) barEl.style.width = Math.min(percent, 100) + '%';
      }
    }
  });

  socket.on('disconnect', () => {
    document.getElementById('connection-dot').className = 'hud-dot error';
  });

  socket.on('realtime_update', (data) => {
    // Update widget panels (existing)
    Object.keys(data).forEach(id => {
      const el = document.querySelector(`[data-widget-id="${id}"][data-ext-id="system_monitor"]`);
      if (el) {
        updateWidgetValue(el, { value: data[id] });
      }
    });

    // Update sys-grid (bottom-left 2x2)
    updateSysGrid(data);
  });
}

function updateSysGrid(data) {
  const labels = { cpu: 'CPU', ram: 'RAM', gpu: 'GPU', disk: 'DISK' };
  const barColors = {
    cpu: 'var(--accent-cyan)',
    ram: 'var(--accent-purple)',
    gpu: 'var(--accent-yellow)',
    disk: 'var(--accent-green)'
  };

  for (const [id, val] of Object.entries(data)) {
    if (!labels[id]) continue;

    let percent = 0;
    if (typeof val === 'number') percent = val;
    else if (typeof val === 'object' && val.percent !== undefined) percent = val.percent;
    else if (typeof val === 'object' && val.load !== undefined) percent = val.load;

    // Value text
    const valueEl = document.getElementById(`sys-${id}-value`);
    if (valueEl) valueEl.textContent = percent.toFixed(1) + '%';

    // Temperature (CPU and GPU)
    const tempEl = document.getElementById(`sys-${id}-temp`);
    if (tempEl && typeof val === 'object' && val.temp !== undefined) {
      tempEl.textContent = val.temp + '°C';
    } else if (tempEl) {
      tempEl.textContent = '';
    }

    // Progress bar
    const barEl = document.getElementById(`sys-${id}-bar`);
    if (barEl) barEl.style.width = Math.min(percent, 100) + '%';

    // Mini chart
    if (!sysHistory[id]) sysHistory[id] = [];
    sysHistory[id].push(percent);
    if (sysHistory[id].length > 40) sysHistory[id].shift();

    const canvas = document.getElementById(`sys-${id}-chart`);
    if (canvas) {
      const color = getComputedStyle(document.documentElement).getPropertyValue(barColors[id].replace('var(', '').replace(')', '')).trim() || '#00d4ff';
      drawSysMiniChart(canvas, sysHistory[id], color);
    }
  }
}

function drawSysMiniChart(canvas, data, color) {
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

  const stepX = w / 39;
  const startIdx = 40 - data.length;

  ctx.strokeStyle = color;
  ctx.lineWidth = 1.5;
  ctx.lineJoin = 'round';
  ctx.beginPath();

  data.forEach((v, i) => {
    const x = (startIdx + i) * stepX;
    const y = h - ((v / 100) * h);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Gradient fill
  ctx.lineTo(w, h);
  ctx.lineTo(startIdx * stepX, h);
  ctx.closePath();
  const grad = ctx.createLinearGradient(0, 0, 0, h);
  grad.addColorStop(0, color + '44');
  grad.addColorStop(1, color + '00');
  ctx.fillStyle = grad;
  ctx.fill();
}

function initResultPanel() {
  document.getElementById('result-panel-close').addEventListener('click', closeResultPanel);
  document.getElementById('overlay').addEventListener('click', closeResultPanel);
  document.getElementById('hud-vpn').addEventListener('click', showVpnPanel);
}

async function showVpnPanel() {
  const panel = document.getElementById('result-panel');
  const overlay = document.getElementById('overlay');
  document.getElementById('result-panel-title').textContent = 'VPN Control';
  const body = document.getElementById('result-panel-body');
  body.classList.remove('vpn-panel-body');
  body.innerHTML = '<div class="flex items-center gap-8"><div class="spinner"></div>Loading...</div>';
  panel.classList.add('open');
  overlay.classList.add('open');
  await renderVpnControl(body);
}



function closeResultPanel() {
  document.getElementById('result-panel').classList.remove('open');
  document.getElementById('overlay').classList.remove('open');
}
