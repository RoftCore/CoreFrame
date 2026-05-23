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
    const group = document.createElement('div');
    group.className = 'category-group';

    const label = document.createElement('div');
    label.className = 'category-label';
    label.textContent = cat;
    group.appendChild(label);

    for (const ext of exts) {
      for (const item of (ext.menu_items || [])) {
        const el = document.createElement('div');
        el.className = 'menu-item';
        el.dataset.extId = ext.id;
        el.dataset.action = item.action;

        const iconSpan = document.createElement('span');
        iconSpan.className = 'menu-item-icon';
        iconSpan.textContent = getIcon(ext.icon || 'circle');
        el.appendChild(iconSpan);

        const textSpan = document.createElement('span');
        textSpan.className = 'menu-item-text';
        textSpan.textContent = item.label;
        el.appendChild(textSpan);

        el.addEventListener('click', () => {
          executeMenuAction(ext.id, item.action, item.label);
        });

        group.appendChild(el);
      }
    }

    nav.appendChild(group);
  }
}

function getIcon(name) {
  const icons = {
    shield: '\u{1F6E1}',
    monitor: '\u{1F4BB}',
    vault: '\u{1F512}',
    cpu: '\u{2699}',
    network: '\u{1F310}',
    disk: '\u{1F4BE}',
    lock: '\u{1F510}',
    terminal: '\u{2328}',
    chart: '\u{1F4C8}',
    folder: '\u{1F4C1}',
    circle: '\u{25CF}'
  };
  return icons[name] || '\u{25CF}';
}

async function executeMenuAction(extId, action, label) {
  const panel = document.getElementById('result-panel');
  const overlay = document.getElementById('overlay');
  const panelTitle = document.getElementById('result-panel-title');
  const panelBody = document.getElementById('result-panel-body');

  panelTitle.textContent = label || action;
  panelBody.classList.remove('vpn-panel-body');
  if (extId === 'network_monitor' && action === 'vpn_control') {
    panelBody.innerHTML = '<div class="flex items-center gap-8"><div class="spinner"></div>Loading...</div>';
    panel.classList.add('open');
    overlay.classList.add('open');
    await renderVpnControl(panelBody);
    return;
  }

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

async function renderVpnControl(panelBody) {
  const [configResp, statusResp, providersResp, dnsResp, ksResp] = await Promise.all([
    apiFetch('/api/extension/network_monitor/get_vpn_config'),
    apiFetch('/api/extension/network_monitor/get_vpn_status'),
    apiFetch('/api/extension/network_monitor/get_available_providers'),
    apiFetch('/api/extension/network_monitor/dns_leak'),
    apiFetch('/api/extension/network_monitor/get_killswitch')
  ]);

  const cfg = (configResp.value || {});
  const status = (statusResp.value || {});
  const providers = Array.isArray(providersResp.value) ? providersResp.value : [];
  const dns = (dnsResp.value || {});
  const ks = (ksResp.value || {});
  const configuredProvider = (cfg.provider || '').toLowerCase();

  panelBody.classList.add('vpn-panel-body');
  const mainAction = status.active ? 'disconnect_vpn' : 'connect_vpn';
  const mainActionLabel = status.active ? 'Apagar' : 'Encender';

  const dnsLeak = dns.leak;
  const dnsDetails = dns.details || '';
  const dnsColor = !dnsLeak ? 'var(--accent-green)' : 'var(--accent-red)';

  // Build provider selector HTML
  let providerSelectorHtml = '';
  if (providers.length > 1) {
    providerSelectorHtml = `<div style="margin-bottom:12px;display:flex;gap:6px;flex-wrap:wrap">
      ${providers.map(p => {
        const isSelected = p.id === configuredProvider || (p.configured && !configuredProvider);
        const isActive = p.active;
        return `<button type="button" class="vpn-provider-btn" data-provider="${escapeHtml(p.id)}"
          style="flex:1;min-width:60px;padding:6px 8px;border:1px solid ${isSelected ? 'var(--accent-cyan)' : 'rgba(0,212,255,0.15)'};
          background:${isSelected ? 'rgba(0,212,255,0.12)' : 'rgba(0,0,0,0.3)'};
          color:${isActive ? 'var(--accent-green)' : 'var(--text-secondary)'};
          border-radius:4px;cursor:pointer;font-family:var(--font-mono);font-size:10px;text-align:center;
          text-transform:uppercase;letter-spacing:0.5px;transition:all 0.15s">
          ${escapeHtml(p.name)}${isActive ? ' ●' : ''}
        </button>`;
      }).join('')}
    </div>`;
  }

  panelBody.innerHTML = `
    ${providerSelectorHtml}
    <div class="vpn-status-line">
      <div class="vpn-status-copy">
        <span class="badge-dot ${escapeHtml(status.status || 'warn')}"></span>
        <span>${escapeHtml(status.text || 'Estado no disponible')}</span>
      </div>
      <button type="button" class="vpn-power-btn" data-vpn-action="${mainAction}">${mainActionLabel}</button>
    </div>
    ${status.active ? `
    <div class="vpn-dns-status" style="margin-bottom:10px;padding:6px 10px;border-radius:4px;font-size:10px;font-family:var(--font-mono);background:rgba(0,0,0,0.3);border:1px solid ${dnsColor}40">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span style="color:${dnsColor}">${escapeHtml(dnsDetails)}</span>
        <button type="button" class="vpn-dns-fix-btn" style="padding:4px 8px;border:1px solid ${dnsColor};border-radius:3px;background:transparent;color:${dnsColor};cursor:pointer;font-size:9px;font-family:var(--font-mono)">Fix DNS</button>
      </div>
      <div style="margin-top:4px;color:var(--text-muted);font-size:9px">
        IP real: ${escapeHtml(dns.real_ip || '?')} | DNS: ${escapeHtml(dns.dns_resolved || '?')}
      </div>
    </div>
    ` : ''}
    ${ks.available ? `
    <div style="margin-bottom:10px;padding:8px 10px;border-radius:4px;background:rgba(0,0,0,0.25);border:1px solid rgba(0,212,255,0.1)">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <span style="font-size:10px;font-family:var(--font-mono);color:var(--text-secondary);text-transform:uppercase;letter-spacing:0.5px">Killswitch</span>
        <button type="button" id="vpn-ks-btn" style="padding:4px 12px;border:1px solid ${ks.enabled ? 'var(--accent-green)' : 'rgba(255,255,255,0.15)'};border-radius:3px;background:${ks.enabled ? 'rgba(0,255,100,0.1)' : 'transparent'};color:${ks.enabled ? 'var(--accent-green)' : 'var(--text-secondary)'};cursor:pointer;font-size:9px;font-family:var(--font-mono);transition:all 0.15s">${ks.enabled ? 'ON' : 'OFF'}</button>
      </div>
      <div style="font-size:9px;color:var(--text-muted)">Bloquea tráfico fuera de la VPN</div>
    </div>
    ` : ''}
    <form id="vpn-control-form" class="vpn-form" style="border-top:1px solid rgba(0,212,255,0.08);padding-top:10px">
      <label>
        <span style="font-size:10px;text-transform:uppercase;letter-spacing:0.5px">Proveedor activo</span>
        <select name="provider" style="width:100%;padding:8px 10px;background:rgba(0,0,0,0.4);border:1px solid rgba(0,212,255,0.15);border-radius:4px;color:var(--text-primary);font-family:var(--font-mono);font-size:11px">
          <option value="">-- Seleccionar --</option>
          ${providers.map(p => `<option value="${escapeHtml(p.id)}" ${p.id === configuredProvider ? 'selected' : ''}>${escapeHtml(p.name)}${p.has_cli ? ' [CLI]' : ''}</option>`).join('')}
        </select>
      </label>
      <div class="vpn-actions" style="margin-top:8px">
        <button type="button" data-vpn-action="save_vpn_config">Guardar configuración</button>
      </div>
      <div class="vpn-feedback" style="margin-top:6px;font-size:9px;color:var(--text-muted)">${escapeHtml(status.last_action || '')}</div>
    </form>
  `;

  // Killswitch toggle
  const ksBtn = panelBody.querySelector('#vpn-ks-btn');
  if (ksBtn) {
    ksBtn.addEventListener('click', async () => {
      const feedback = panelBody.querySelector('.vpn-feedback');
      const newState = !ks.enabled;
      feedback.textContent = newState ? 'Activando killswitch...' : 'Desactivando killswitch...';
      const resp = await apiFetch('/api/extension/network_monitor/toggle_killswitch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: newState })
      });
      feedback.textContent = (resp.value || 'OK');
      await renderVpnControl(panelBody);
    });
  }

  // DNS Fix button
  const dnsFixBtn = panelBody.querySelector('.vpn-dns-fix-btn');
  if (dnsFixBtn) {
    dnsFixBtn.addEventListener('click', async () => {
      const feedback = panelBody.querySelector('.vpn-feedback');
      feedback.textContent = 'Forzando DNS...';
      await apiFetch('/api/extension/network_monitor/set_vpn_dns', { method: 'POST' });
      await renderVpnControl(panelBody);
    });
  }

  // Provider selector buttons: switch target on click
  if (providers.length > 1) {
    panelBody.querySelectorAll('.vpn-provider-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        const provider = btn.dataset.provider;
        const feedback = panelBody.querySelector('.vpn-feedback');
        feedback.textContent = 'Cambiando a ' + provider + '...';
        const resp = await apiFetch('/api/extension/network_monitor/save_vpn_config', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target_provider: provider })
        });
        if (resp.error) {
          feedback.textContent = 'Error: ' + resp.error;
          return;
        }
        await refreshWidget('network_monitor', { id: 'vpn_status', action: 'check_vpn' });
        await renderVpnControl(panelBody);
      });
    });
  }

  panelBody.querySelectorAll('[data-vpn-action]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const form = panelBody.querySelector('#vpn-control-form');
      const payload = Object.fromEntries(new FormData(form).entries());
      payload.target_provider = payload.provider;
      const action = btn.dataset.vpnAction;
      const feedback = panelBody.querySelector('.vpn-feedback');
      feedback.textContent = 'Ejecutando...';
      const resp = await apiFetch(`/api/extension/network_monitor/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (resp.error) {
        feedback.textContent = 'Error: ' + resp.error;
        return;
      }
      const value = resp.value || {};
      feedback.textContent = value.message || 'Guardado';
      await refreshWidget('network_monitor', { id: 'vpn_status', action: 'check_vpn' });
      if (action === 'connect_vpn' || action === 'disconnect_vpn') {
        await renderVpnControl(panelBody);
      }
    });
  });
}
