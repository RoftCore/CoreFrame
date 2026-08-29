const menuHooks = {};

function registerMenuHook(extId, action, handler) {
  menuHooks[`${extId}:${action}`] = handler;
}

function buildSidebar(extensionsData) {
  const nav = document.getElementById('sidebar-nav');
  nav.innerHTML = '';

  const categories = {};
  for (const [extId, ext] of Object.entries(extensionsData)) {
    const cat = ext.category || 'general';
    if (!categories[cat]) categories[cat] = [];
    categories[cat].push(ext);
  }

  for (const [cat, exts] of Object.entries(categories)) {
    const items = [];
    for (const ext of exts) {
      for (const item of (ext.menu_items || [])) {
        items.push({ ...item, extId: ext.id, icon: ext.icon });
      }
    }
    if (items.length === 0) continue;

    
  }
}

function getIcon(name) {
  const icons = {
    shield: 'shield',
    monitor: 'monitor',
    vault: 'lock',
    cpu: 'cpu',
    network: 'globe',
    disk: 'hard-drive',
    lock: 'lock',
    terminal: 'terminal',
    chart: 'bar-chart-2',
    folder: 'folder',
    circle: 'circle'
  };
  var featherName = icons[name] || 'circle';
  return '<i data-feather="' + featherName + '" width="16" height="16"></i>';
}

async function executeMenuAction(extId, action, label) {
  const panel = document.getElementById('result-panel');
  const overlay = document.getElementById('overlay');
  const panelTitle = document.getElementById('result-panel-title');
  const panelBody = document.getElementById('result-panel-body');

  const hook = menuHooks[`${extId}:${action}`];
  if (hook) {
    panelTitle.textContent = label || action;
    panelBody.innerHTML = '<div class="flex items-center gap-8"><div class="spinner"></div>Loading...</div>';
    panel.classList.add('open');
    overlay.classList.add('open');
    try {
      await hook(panelBody);
    } catch (err) {
      panelBody.innerHTML = '<span class="text-red">Error: ' + escapeHtml(err.message || String(err)) + '</span>';
    }
    return;
  }

  panelTitle.textContent = label || action;
  panelBody.innerHTML = '<div class="flex items-center gap-8"><div class="spinner"></div>Loading...</div>';
  panel.classList.add('open');
  overlay.classList.add('open');

  const data = await apiFetch(`/api/extension/${extId}/${action}`);
  panelBody.innerHTML = '';
  if (data.error) {
    panelBody.innerHTML = '<span class="text-red">Error: ' + escapeHtml(data.error) + '</span>';
    return;
  }
  const formatted = typeof data.value === 'object' ? JSON.stringify(data.value, null, 2) : String(data.value);
  panelBody.textContent = formatted;
}
