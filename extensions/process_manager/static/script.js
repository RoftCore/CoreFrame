let _procSort = { key: 'cpu', dir: 'desc' };
let _widgetSort = { key: 'cpu', dir: 'desc' };
let _procData = [];
let _systemStats = {};
const _iconCache = {};
let _expandedGroups = {};
const _iconPending = new Set();
let _iconQueue = [];
let _iconLoading = false;

function groupProcesses(procs) {
  const map = {};
  procs.forEach(p => {
    const g = map[p.name] || (map[p.name] = { name: p.name, procs: [], cpu: 0, mem: 0, mem_rss: 0, disk: 0 });
    g.procs.push(p);
    g.cpu += p.cpu;
    g.mem += p.mem;
    g.mem_rss += p.mem_rss || 0;
    g.disk += p.disk || 0;
  });
  Object.values(map).forEach(g => g.procs.sort((a, b) => b.cpu - a.cpu));
  return Object.values(map);
}

function formatDisk(bytesPerSec) {
  if (!bytesPerSec || bytesPerSec <= 0) return '-';
  return formatBytes(bytesPerSec) + '/s';
}

// Create panel HTML
(function() {
  const panel = document.createElement('div');
  panel.id = 'ext-pm-panel';
  panel.innerHTML = `
    <div class="ext-pm-header">
      <span>Task Manager</span>
      <button class="ext-pm-close" id="ext-pm-toggle" title="View large">⛶</button>
    </div>
    <div class="ext-pm-toolbar">
      <input type="text" class="ext-pm-search" id="ext-pm-search" placeholder="Filter...">
    </div>
    <div class="ext-pm-stats" id="ext-pm-stats">
      <span>Processes: <strong id="ext-pm-total">--</strong></span>
      <span>CPU: <strong id="ext-pm-cpu-total">--</strong></span>
      <span>RAM: <strong id="ext-pm-ram-total">--</strong></span>
    </div>
    <div class="ext-pm-table-wrap" id="ext-pm-table-wrap">
      <table class="ext-pm-table" id="ext-pm-table">
        <thead>
          <tr>
            <th data-sort="pid">PID</th>
            <th></th>
            <th data-sort="name">Name</th>
            <th data-sort="cpu" class="sorted desc">CPU%</th>
            <th data-sort="mem">MEM%</th>
            <th data-sort="mem_rss">Memory</th>
            <th data-sort="disk">Disk</th>
            <th data-sort="user">User</th>
          </tr>
        </thead>
        <tbody id="ext-pm-tbody"></tbody>
      </table>
    </div>
  `;
  document.body.appendChild(panel);
})();

const PM_CACHE_KEY = 'ext-pm-cache';

function cacheProcessData(data) {
  try { localStorage.setItem(PM_CACHE_KEY, JSON.stringify(data)); } catch (_) {}
}

function loadCachedProcessData() {
  try {
    const raw = localStorage.getItem(PM_CACHE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_) { return null; }
}

async function initProcessPanel() {
  document.getElementById('ext-pm-toggle').addEventListener('click', showProcessManagerModal);

  document.querySelectorAll('#ext-pm-table th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (_procSort.key === key) {
        _procSort.dir = _procSort.dir === 'asc' ? 'desc' : 'asc';
      } else {
        _procSort.key = key;
        _procSort.dir = 'desc';
      }
      document.querySelectorAll('#ext-pm-table th[data-sort]').forEach(h => h.classList.remove('sorted', 'asc', 'desc'));
      th.classList.add('sorted', _procSort.dir);
      renderProcTable();
    });
  });

  document.getElementById('ext-pm-search').addEventListener('input', () => {
    renderProcTable();
  });

  // Inject visible process table into the dashboard widget
  const widgetBody = document.querySelector('.ext-process_manager .widget-body');
  if (widgetBody) {
    widgetBody.innerHTML = `
      <div class="ext-pm-widget-toolbar">
        <input type="text" class="ext-pm-widget-search" id="ext-pm-widget-search" placeholder="Filter processes..." autofocus>
        <span class="ext-pm-widget-count" id="ext-pm-widget-total">--</span>
        <button class="ext-pm-widget-expand" id="ext-pm-widget-toggle" title="Full view">⛶</button>
      </div>
      <div class="ext-pm-widget-table-wrap" id="ext-pm-widget-table-wrap">
        <table class="ext-pm-widget-table" id="ext-pm-widget-table">
          <thead>
            <tr>
              <th></th>
              <th data-wsort="name" class="${_widgetSort.key === 'name' ? 'wsorted ' + _widgetSort.dir : ''}">Name</th>
              <th data-wsort="cpu" class="${_widgetSort.key === 'cpu' ? 'wsorted ' + _widgetSort.dir : 'wsorted desc'}"><strong id="ext-pm-widget-cpu-total">--</strong> CPU%</th>
              <th data-wsort="mem" class="${_widgetSort.key === 'mem' ? 'wsorted ' + _widgetSort.dir : ''}"><strong id="ext-pm-widget-ram-total">--</strong> MEM%</th>
              <th data-wsort="disk" class="${_widgetSort.key === 'disk' ? 'wsorted ' + _widgetSort.dir : ''}">Disk</th>
              <th></th>
            </tr>
          </thead>
          <tbody id="ext-pm-widget-tbody"><tr><td colspan="6" class="ext-pm-widget-loading">Loading processes...</td></tr></tbody>
        </table>
      </div>
    `;
    document.getElementById('ext-pm-widget-toggle').addEventListener('click', showProcessManagerModal);
    document.getElementById('ext-pm-widget-search').addEventListener('input', () => {
      renderProcTable();
    });

    document.querySelectorAll('#ext-pm-widget-table th[data-wsort]').forEach(th => {
      th.addEventListener('click', () => {
        const key = th.dataset.wsort;
        if (_widgetSort.key === key) {
          _widgetSort.dir = _widgetSort.dir === 'asc' ? 'desc' : 'asc';
        } else {
          _widgetSort.key = key;
          _widgetSort.dir = key === 'name' ? 'asc' : 'desc';
        }
        document.querySelectorAll('#ext-pm-widget-table th[data-wsort]').forEach(h => {
          h.classList.remove('wsorted', 'asc', 'desc');
        });
        th.classList.add('wsorted', _widgetSort.dir);
        renderProcTable();
      });
    });

    // Pin card height to prevent CSS Grid from expanding with hundreds of rows
    const card = document.querySelector('.ext-process_manager');
    if (card) {
      card.style.maxHeight = card.offsetHeight + 'px';
    }
  }

  // Show cached data instantly if available, then refresh in background
  const cached = loadCachedProcessData();
  if (cached) {
    _procData = cached;
    renderProcTable();
  }

  await refreshProcessPanel();
}

async function refreshProcessPanel() {
  const data = await apiFetch('/api/extension/process_manager/get_processes');
  if (data.error) return;
  _procData = Array.isArray(data.value) ? data.value : [];
  _systemStats = data.system || {};
  cacheProcessData(_procData);
  renderProcTable();
  refreshModalContent();
}

function renderProcTable() {
  const q = document.getElementById('ext-pm-search').value.toLowerCase();
  const key = _procSort.key;
  const dir = _procSort.dir;

  let filtered = _procData.filter(p => p.name.toLowerCase().includes(q));
  filtered.sort((a, b) => {
    let va = a[key], vb = b[key];
    if (typeof va === 'string') va = va.toLowerCase();
    if (typeof vb === 'string') vb = vb.toLowerCase();
    if (va < vb) return dir === 'asc' ? -1 : 1;
    if (va > vb) return dir === 'asc' ? 1 : -1;
    return 0;
  });

  const groups = groupProcesses(filtered);
  groups.sort((a, b) => {
    let va = key === 'name' ? a.name.toLowerCase() : a[key];
    let vb = key === 'name' ? b.name.toLowerCase() : b[key];
    if (va < vb) return dir === 'asc' ? -1 : 1;
    if (va > vb) return dir === 'asc' ? 1 : -1;
    return 0;
  });

  // === PANEL TABLE ===
  const panelTotal = document.getElementById('ext-pm-total');
  const panelCpu = document.getElementById('ext-pm-cpu-total');
  const panelRam = document.getElementById('ext-pm-ram-total');
  const panelTbody = document.getElementById('ext-pm-tbody');
  if (panelTotal) panelTotal.textContent = _procData.length;
  if (panelCpu) panelCpu.textContent = (_systemStats.cpu || _procData.reduce((s, p) => s + p.cpu, 0)).toFixed(1) + '%';
  if (panelRam) panelRam.textContent = (_systemStats.ram || _procData.reduce((s, p) => s + p.mem, 0)).toFixed(1) + '%';
  if (panelTbody) {
    panelTbody.innerHTML = renderPanelGroupRows(groups);
    lazyLoadIcons(panelTbody, _iconCache, 4);
  }

  // === WIDGET TABLE ===
  const widgetTotal = document.getElementById('ext-pm-widget-total');
  const widgetCpu = document.getElementById('ext-pm-widget-cpu-total');
  const widgetRam = document.getElementById('ext-pm-widget-ram-total');
  const widgetSearch = document.getElementById('ext-pm-widget-search');
  const widgetTbody = document.getElementById('ext-pm-widget-tbody');
  if (widgetTotal) widgetTotal.textContent = _procData.length;
  if (widgetCpu) widgetCpu.textContent = (_systemStats.cpu || _procData.reduce((s, p) => s + p.cpu, 0)).toFixed(1) + '%';
  if (widgetRam) widgetRam.textContent = (_systemStats.ram || _procData.reduce((s, p) => s + p.mem, 0)).toFixed(1) + '%';
  if (widgetTbody && widgetSearch) {
    const wq = widgetSearch.value.toLowerCase();
    const wk = _widgetSort.key;
    const wd = _widgetSort.dir;
    let wFiltered = _procData.filter(p => p.name.toLowerCase().includes(wq));
    let wGroups = groupProcesses(wFiltered);
    wGroups.sort((a, b) => {
      let va = wk === 'name' ? a.name.toLowerCase() : a[wk];
      let vb = wk === 'name' ? b.name.toLowerCase() : b[wk];
      if (va < vb) return wd === 'asc' ? -1 : 1;
      if (va > vb) return wd === 'asc' ? 1 : -1;
      return 0;
    });
    widgetTbody.innerHTML = renderWidgetGroupRows(wGroups);
    lazyLoadIcons(widgetTbody, _iconCache, 4);
  }
}

async function killGroupProcesses(pids) {
  const name = _procData.find(p => pids.includes(p.pid))?.name || 'process';
  const confirmed = confirm(`End all ${pids.length} instances of ${name}?`);
  if (!confirmed) return;
  await Promise.allSettled(pids.map(pid =>
    apiFetch('/api/extension/process_manager/kill_process', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pid })
    })
  ));
  _procData = _procData.filter(p => !pids.includes(p.pid));
  cacheProcessData(_procData);
  renderProcTable();
  refreshModalContent();
}

function renderPanelGroupRows(groups) {
  return groups.map(g => {
    const isMulti = g.procs.length > 1;
    const isExpanded = !!_expandedGroups[g.name];
    const iconHtml = getProcessIcon(g.name);
    const memStr = g.mem_rss ? formatBytes(g.mem_rss) : '-';
    const diskStr = formatDisk(g.disk);
    const nameDisplay = isMulti ? `${escapeHtml(g.name)} <span class="proc-count">(${g.procs.length})</span>` : escapeHtml(g.name);

    let html = `<tr data-name="${escapeHtml(g.name)}" class="ext-pm-group-row${isExpanded ? ' expanded' : ''}" data-group="${escapeHtml(g.name)}">
      <td class="proc-pid">${isMulti ? '' : g.procs[0].pid}</td>
      <td class="proc-icon">${iconHtml}</td>
      <td class="proc-name">${nameDisplay}</td>
      <td class="proc-cpu">${g.cpu.toFixed(1)}%</td>
      <td class="proc-mem">${g.mem.toFixed(1)}%</td>
      <td class="proc-memrss">${memStr}</td>
      <td class="proc-disk">${diskStr}</td>
      <td class="proc-user">${isMulti
        ? `<button class="ext-pm-widget-kill" data-pids="${g.procs.map(p => p.pid).join(',')}" title="End All">✕</button>`
        : `<button class="ext-pm-widget-kill" data-pid="${g.procs[0].pid}" title="End ${escapeHtml(g.procs[0].name)} (${escapeHtml(g.procs[0].user)})">✕</button>`}</td>
    </tr>`;

    if (isMulti) {
      g.procs.forEach((p, i) => {
        const mc = p.mem_rss ? formatBytes(p.mem_rss) : '-';
        const dk = formatDisk(p.disk);
        html += `<tr data-name="${escapeHtml(p.name)}" data-pid="${p.pid}" class="ext-pm-child-row" data-group="${escapeHtml(g.name)}"${isExpanded ? '' : ' style="display:none"'}>
          <td class="proc-pid">${p.pid}</td>
          <td class="proc-icon"><span class="ext-pm-expand-placeholder"></span>${getProcessIcon(p.name)}</td>
          <td class="proc-name">${escapeHtml(p.name)} <span class="proc-index">#${i + 1}</span></td>
          <td class="proc-cpu">${p.cpu.toFixed(1)}%</td>
          <td class="proc-mem">${p.mem.toFixed(1)}%</td>
          <td class="proc-memrss">${mc}</td>
          <td class="proc-disk">${dk}</td>
          <td class="proc-user">${escapeHtml(p.user)}</td>
        </tr>`;
      });
    }

    return html;
  }).join('');
}

function renderWidgetGroupRows(groups) {
  return groups.map(g => {
    const isMulti = g.procs.length > 1;
    const isExpanded = !!_expandedGroups[g.name];
    const iconHtml = getProcessIcon(g.name);
    const diskStr = formatDisk(g.disk);
    const nameDisplay = isMulti ? `${escapeHtml(g.name)} <span class="proc-count">(${g.procs.length})</span>` : escapeHtml(g.name);

    let html = `<tr data-name="${escapeHtml(g.name)}" class="ext-pm-group-row${isExpanded ? ' expanded' : ''}" data-group="${escapeHtml(g.name)}">
      <td class="proc-icon">${iconHtml}</td>
      <td class="proc-name">${nameDisplay}</td>
      <td class="proc-cpu">${g.cpu.toFixed(1)}%</td>
      <td class="proc-mem">${g.mem.toFixed(1)}%</td>
      <td class="proc-disk">${diskStr}</td>
      <td>${isMulti
        ? `<button class="ext-pm-widget-kill" data-pids="${g.procs.map(p => p.pid).join(',')}" title="End All">✕</button>`
        : `<button class="ext-pm-widget-kill" data-pid="${g.procs[0].pid}" title="End Task">✕</button>`}</td>
    </tr>`;

    if (isMulti) {
      g.procs.forEach((p, i) => {
        const dk = formatDisk(p.disk);
        html += `<tr data-name="${escapeHtml(p.name)}" data-pid="${p.pid}" class="ext-pm-child-row" data-group="${escapeHtml(g.name)}"${isExpanded ? '' : ' style="display:none"'}>
          <td class="proc-icon"><span class="ext-pm-expand-placeholder"></span>${getProcessIcon(p.name)}</td>
          <td class="proc-name">${escapeHtml(p.name)} <span class="proc-index">#${i + 1}</span></td>
          <td class="proc-cpu">${p.cpu.toFixed(1)}%</td>
          <td class="proc-mem">${p.mem.toFixed(1)}%</td>
          <td class="proc-disk">${dk}</td>
          <td><button class="ext-pm-widget-kill" data-pid="${p.pid}" title="End Task">✕</button></td>
        </tr>`;
      });
    }

    return html;
  }).join('');
}

async function showProcessManagerModal() {
  const panel = document.getElementById('result-panel');
  const overlay = document.getElementById('overlay');
  const panelTitle = document.getElementById('result-panel-title');
  const panelBody = document.getElementById('result-panel-body');

  panelTitle.textContent = 'Task Manager';
  panelBody.classList.remove('vpn-panel-body', 'net-inspector-body', 'ext-pm-body');
  panelBody.classList.add('ext-pm-modal-body');
  panel.classList.add('open');
  overlay.classList.add('open');

  // Use already-cached data from the 3s auto-refresh — show instantly
  const procs = _procData.length ? _procData : [];
  const totalCpu = procs.reduce((s, p) => s + p.cpu, 0).toFixed(1);
  const totalRam = procs.reduce((s, p) => s + p.mem, 0).toFixed(1);
  const modalGroups = groupProcesses(procs);
  modalGroups.sort((a, b) => b.cpu - a.cpu);

  panelBody.innerHTML = `
    <div class="ext-pm-modal-toolbar">
      <input type="text" class="ext-pm-modal-search" id="ext-pm-modal-search" placeholder="Filter processes..." autofocus>
      <button class="ext-pm-modal-refresh" id="ext-pm-modal-refresh">⟳</button>
      <span class="ext-pm-modal-total">${procs.length} processes</span>
    </div>
    <div class="ext-pm-modal-table-wrap">
      <table class="ext-pm-modal-table" id="ext-pm-modal-table">
        <thead>
          <tr>
            <th data-sort="pid">PID</th>
            <th></th>
            <th data-sort="name">Name</th>
            <th data-sort="cpu" class="sorted desc">CPU%</th>
            <th data-sort="mem">MEM%</th>
            <th data-sort="mem_rss">Memory</th>
            <th data-sort="disk">Disk</th>
            <th data-sort="user">User</th>
          </tr>
        </thead>
        <tbody id="ext-pm-modal-tbody">
          ${renderPanelGroupRows(modalGroups)}
        </tbody>
      </table>
    </div>
    <div class="ext-pm-modal-footer">
      <span>CPU: <strong>${totalCpu}%</strong></span>
      <span>RAM: <strong>${totalRam}%</strong></span>
      <span>Processes: <strong>${procs.length}</strong></span>
    </div>
  `;

  let modalSort = { key: 'cpu', dir: 'desc' };

  function filterAndSortModal() {
    const q = document.getElementById('ext-pm-modal-search').value.toLowerCase();
    const tbody = document.getElementById('ext-pm-modal-tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    rows.forEach(row => {
      const name = (row.dataset.name || '').toLowerCase();
      row.style.display = name.includes(q) ? '' : 'none';
    });
  }

  panelBody.querySelector('#ext-pm-modal-search').addEventListener('input', filterAndSortModal);

  panelBody.querySelector('#ext-pm-modal-refresh').addEventListener('click', async () => {
    const btn = document.getElementById('ext-pm-modal-refresh');
    btn.textContent = '↻';
    btn.style.animation = 'spin 0.6s linear infinite';
    await refreshProcessPanel();
    refreshModalContent();
    btn.textContent = '⟳';
    btn.style.animation = '';
  });

  panelBody.querySelectorAll('#ext-pm-modal-table th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (modalSort.key === key) {
        modalSort.dir = modalSort.dir === 'asc' ? 'desc' : 'asc';
      } else {
        modalSort.key = key;
        modalSort.dir = 'desc';
      }
      panelBody.querySelectorAll('#ext-pm-modal-table th[data-sort]').forEach(h => h.classList.remove('sorted', 'asc', 'desc'));
      th.classList.add('sorted', modalSort.dir);

      const tbody = document.getElementById('ext-pm-modal-tbody');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort((a, b) => {
        const va = a.querySelector(`td:nth-child(${th.cellIndex + 1})`).textContent.trim();
        const vb = b.querySelector(`td:nth-child(${th.cellIndex + 1})`).textContent.trim();
        const na = parseFloat(va), nb = parseFloat(vb);
        if (!isNaN(na) && !isNaN(nb)) {
          return modalSort.dir === 'asc' ? na - nb : nb - na;
        }
        return modalSort.dir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
      });
      rows.forEach(r => tbody.appendChild(r));
      filterAndSortModal();
    });
  });

  const modalTbody = document.getElementById('ext-pm-modal-tbody');
  lazyLoadIcons(modalTbody, _iconCache, 4);
}

function refreshModalContent() {
  const modalTbody = document.getElementById('ext-pm-modal-tbody');
  if (!modalTbody) return;
  const q = document.getElementById('ext-pm-modal-search')?.value?.toLowerCase() || '';
  const procs = _procData;
  const totalCpu = procs.reduce((s, p) => s + p.cpu, 0).toFixed(1);
  const totalRam = procs.reduce((s, p) => s + p.mem, 0).toFixed(1);
  const filtered = q ? procs.filter(p => p.name.toLowerCase().includes(q)) : procs;
  const groups = groupProcesses(filtered);
  groups.sort((a, b) => b.cpu - a.cpu);
  modalTbody.innerHTML = renderPanelGroupRows(groups);
  lazyLoadIcons(modalTbody, _iconCache, 4);

  const footer = modalTbody.closest('.ext-pm-modal-body, .result-panel-body');
  if (footer) {
    const totalEl = footer.querySelector('.ext-pm-modal-total');
    if (totalEl) totalEl.textContent = `${procs.length} processes`;
    const footerBar = footer.querySelector('.ext-pm-modal-footer');
    if (footerBar) {
      const spans = footerBar.querySelectorAll('span');
      if (spans[0]) spans[0].innerHTML = `CPU: <strong>${totalCpu}%</strong>`;
      if (spans[1]) spans[1].innerHTML = `RAM: <strong>${totalRam}%</strong>`;
      if (spans[2]) spans[2].innerHTML = `Processes: <strong>${procs.length}</strong>`;
    }
  }
}

function attachAllRowHandlers(container) {
  // No-op: event delegation handles all row interactions
}

function lazyLoadIcons(tbody, iconCache, batchSize) {
  if (!tbody) return;
  batchSize = batchSize || 4;
  const rows = Array.from(tbody.querySelectorAll('tr'));
  const allNames = [...new Set(rows.map(r => r.dataset.name).filter(Boolean))];

  // Re-apply cached icons (rows are rebuilt each render, cache survives)
  allNames.forEach(name => {
    if (name in iconCache && iconCache[name]) {
      rows.filter(r => r.dataset.name === name).forEach(r => {
        const cell = r.querySelector('.proc-icon');
        if (cell) cell.innerHTML = `<img src="${iconCache[name]}" class="proc-icon-img" alt="">`;
      });
    }
  });

  const newNames = allNames.filter(n => !(n in iconCache) && !_iconPending.has(n));
  if (newNames.length === 0) return;
  newNames.forEach(n => _iconPending.add(n));

  // Build a quick PID lookup: first PID per name from current data
  var pidByName = {};
  _procData.forEach(function (p) { if (!(p.name in pidByName)) pidByName[p.name] = p.pid; });

  function processBatch(start) {
    const batch = newNames.slice(start, start + batchSize);
    if (batch.length === 0) return;
    Promise.allSettled(batch.map(name =>
      apiFetch('/api/extension/process_manager/get_process_icon', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pid: pidByName[name] })
      }).then(resp => {
        iconCache[name] = resp.value || null;
        _iconPending.delete(name);
        if (resp.value) {
          rows.filter(r => r.dataset.name === name).forEach(r => {
            const cell = r.querySelector('.proc-icon');
            if (cell) cell.innerHTML = `<img src="${resp.value}" class="proc-icon-img" alt="">`;
          });
        }
      }).catch(() => { iconCache[name] = null; _iconPending.delete(name); })
    )).then(() => {
      setTimeout(() => processBatch(start + batchSize), 30);
    });
  }
  processBatch(0);
}

async function showProcessContextMenu(pid, procName) {
  const overlay = document.createElement('div');
  overlay.className = 'ext-pm-context-overlay';

  const dialog = document.createElement('div');
  dialog.className = 'ext-pm-context-dialog';
  dialog.innerHTML = '<div class="flex items-center gap-8"><div class="spinner"></div>Loading details...</div>';

  overlay.appendChild(dialog);
  document.body.appendChild(overlay);

  const resp = await apiFetch('/api/extension/process_manager/get_process_details', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pid })
  });

  if (resp.error) {
    dialog.innerHTML = `<div class="ext-pm-context-err">Error: ${escapeHtml(resp.error)}</div>
      <button class="ext-pm-context-btn ext-pm-context-btn-close">Close</button>`;
    dialog.querySelector('.ext-pm-context-btn-close').addEventListener('click', () => overlay.remove());
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
    return;
  }

  const d = resp.value;
  const cmdline = d.cmdline && d.cmdline.length > 80 ? d.cmdline.substring(0, 80) + '\u2026' : (d.cmdline || 'N/A');

  dialog.innerHTML = `
    <div class="ext-pm-context-header">
      <span class="ext-pm-context-title">${escapeHtml(d.name || procName)} <span class="ext-pm-context-pid">PID: ${d.pid}</span></span>
    </div>
    <div class="ext-pm-context-info">
      <div class="ext-pm-context-row"><span>Status</span><span class="${d.status === 'running' ? 'status-running' : 'status-sleeping'}">${escapeHtml(d.status)}</span></div>
      <div class="ext-pm-context-row"><span>User</span><span>${escapeHtml(d.username)}</span></div>
      <div class="ext-pm-context-row"><span>Memory</span><span>${formatBytes(d.memory_rss)}</span></div>
      <div class="ext-pm-context-row"><span>Threads</span><span>${d.num_threads}</span></div>
      <div class="ext-pm-context-row"><span>Path</span><span class="ext-pm-context-path">${escapeHtml(d.exe || 'N/A')}</span></div>
      <div class="ext-pm-context-row ext-pm-context-row-full"><span>Command</span><span class="ext-pm-context-path">${escapeHtml(cmdline)}</span></div>
    </div>
    <div class="ext-pm-context-actions">
      <button class="ext-pm-context-btn ext-pm-context-btn-kill">End Task</button>
      <button class="ext-pm-context-btn ext-pm-context-btn-close">Close</button>
    </div>
  `;

  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });

  dialog.querySelector('.ext-pm-context-btn-kill').addEventListener('click', async () => {
    const btn = dialog.querySelector('.ext-pm-context-btn-kill');
    btn.disabled = true;
    btn.textContent = 'Terminating...';
    const resp = await apiFetch('/api/extension/process_manager/kill_process', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pid })
    });
    if (resp.error) {
      btn.textContent = 'Failed';
      btn.style.borderColor = 'var(--accent-yellow)';
      btn.disabled = false;
    } else {
      btn.textContent = 'Terminated \u2713';
      btn.style.borderColor = 'var(--accent-green)';
      _procData = _procData.filter(p => p.pid !== pid);
      cacheProcessData(_procData);
      renderProcTable();
      refreshModalContent();
    }
  });

  dialog.querySelector('.ext-pm-context-btn-close').addEventListener('click', () => overlay.remove());
}

registerMenuHook('process_manager', 'get_processes', async (panelBody) => {
  panelBody.classList.add('ext-pm-modal-body');

  // Use already-cached data — show instantly
  const procs = _procData.length ? _procData : [];
  const totalCpu = procs.reduce((s, p) => s + p.cpu, 0).toFixed(1);
  const totalRam = procs.reduce((s, p) => s + p.mem, 0).toFixed(1);
  const modalGroups = groupProcesses(procs);
  modalGroups.sort((a, b) => b.cpu - a.cpu);

  panelBody.innerHTML = `
    <div class="ext-pm-modal-toolbar">
      <input type="text" class="ext-pm-modal-search" id="ext-pm-modal-search" placeholder="Filter processes..." autofocus>
      <button class="ext-pm-modal-refresh" id="ext-pm-modal-refresh">⟳</button>
      <span class="ext-pm-modal-total">${procs.length} processes</span>
    </div>
    <div class="ext-pm-modal-table-wrap">
      <table class="ext-pm-modal-table" id="ext-pm-modal-table">
        <thead>
          <tr>
            <th></th>
            <th data-sort="pid">PID</th>
            <th data-sort="name">Name</th>
            <th data-sort="cpu" class="sorted desc">CPU%</th>
            <th data-sort="mem">MEM%</th>
            <th data-sort="mem_rss">Memory</th>
            <th data-sort="disk">Disk</th>
            <th data-sort="user">User</th>
          </tr>
        </thead>
        <tbody id="ext-pm-modal-tbody">
          ${renderPanelGroupRows(modalGroups)}
        </tbody>
      </table>
    </div>
    <div class="ext-pm-modal-footer">
      <span>CPU: <strong>${totalCpu}%</strong></span>
      <span>RAM: <strong>${totalRam}%</strong></span>
      <span>Processes: <strong>${procs.length}</strong></span>
    </div>
  `;

  setupModalInteractions(panelBody, procs);
});

function setupModalInteractions(panelBody, procs) {
  let modalSort = { key: 'cpu', dir: 'desc' };

  function filterAndSortModal() {
    const q = document.getElementById('ext-pm-modal-search').value.toLowerCase();
    const tbody = document.getElementById('ext-pm-modal-tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    rows.forEach(row => {
      const name = (row.dataset.name || '').toLowerCase();
      row.style.display = name.includes(q) ? '' : 'none';
    });
  }

  const searchInput = panelBody.querySelector('#ext-pm-modal-search');
  if (searchInput) searchInput.addEventListener('input', filterAndSortModal);

  const refreshBtn2 = panelBody.querySelector('#ext-pm-modal-refresh');
  if (refreshBtn2) {
    refreshBtn2.addEventListener('click', async () => {
      refreshBtn2.textContent = '↻';
      refreshBtn2.style.animation = 'spin 0.6s linear infinite';
      await refreshProcessPanel();
      refreshModalContent();
      refreshBtn2.textContent = '⟳';
      refreshBtn2.style.animation = '';
    });
  }

  panelBody.querySelectorAll('#ext-pm-modal-table th[data-sort]').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.dataset.sort;
      if (modalSort.key === key) {
        modalSort.dir = modalSort.dir === 'asc' ? 'desc' : 'asc';
      } else {
        modalSort.key = key;
        modalSort.dir = 'desc';
      }
      panelBody.querySelectorAll('#ext-pm-modal-table th[data-sort]').forEach(h => h.classList.remove('sorted', 'asc', 'desc'));
      th.classList.add('sorted', modalSort.dir);

      const tbody = document.getElementById('ext-pm-modal-tbody');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      rows.sort((a, b) => {
        const va = a.querySelector(`td:nth-child(${th.cellIndex + 1})`).textContent.trim();
        const vb = b.querySelector(`td:nth-child(${th.cellIndex + 1})`).textContent.trim();
        const na = parseFloat(va), nb = parseFloat(vb);
        if (!isNaN(na) && !isNaN(nb)) {
          return modalSort.dir === 'asc' ? na - nb : nb - na;
        }
        return modalSort.dir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
      });
      rows.forEach(r => tbody.appendChild(r));
      filterAndSortModal();
    });
  });

  const tbody = document.getElementById('ext-pm-modal-tbody');
  if (tbody) lazyLoadIcons(tbody, _iconCache, 4);
}

// --- Event delegation for all process table interactions ---
function setupRowDelegation() {
  document.addEventListener('click', (e) => {
    const killBtn = e.target.closest('.ext-pm-widget-kill');
    if (killBtn) {
      e.stopPropagation();
      const pids = killBtn.dataset.pids;
      if (pids) {
        killGroupProcesses(pids.split(',').map(Number));
      } else {
        const pid = parseInt(killBtn.dataset.pid);
        const row = killBtn.closest('tr');
        if (row && pid) showProcessContextMenu(pid, row.dataset.name);
      }
      return;
    }

    const groupRow = e.target.closest('.ext-pm-group-row');
    if (!groupRow) return;
    const groupName = groupRow.dataset.group;
    if (!groupName) return;
    const tbody = groupRow.closest('tbody');
    if (!tbody) return;
    const children = Array.from(tbody.querySelectorAll('tr')).filter(r =>
      r.dataset.group === groupName && r.classList.contains('ext-pm-child-row')
    );
    if (children.length === 0) return;

    _expandedGroups[groupName] = !_expandedGroups[groupName];
    const isExpanded = _expandedGroups[groupName];
    groupRow.classList.toggle('expanded', isExpanded);
    children.forEach(cr => { cr.style.display = isExpanded ? '' : 'none'; });
  });

  document.addEventListener('dblclick', (e) => {
    const childRow = e.target.closest('.ext-pm-child-row');
    if (!childRow) return;
    const pid = parseInt(childRow.dataset.pid);
    const name = childRow.dataset.name;
    if (pid) showProcessContextMenu(pid, name);
  });
}

// Auto-init when extensions data is ready
(function waitForInit() {
  if (typeof extensionsData !== 'undefined' && Object.keys(extensionsData).length) {
    setupRowDelegation();
    initProcessPanel();
    (async function poll() {
      await refreshProcessPanel();
      setTimeout(poll, 3000);
    })();
    return;
  }
  setTimeout(waitForInit, 200);
})();
