const _vpnCache = {
  config: apiFetch('/api/extension/network_monitor/get_vpn_config'),
  status: apiFetch('/api/extension/network_monitor/get_vpn_status'),
  providers: apiFetch('/api/extension/network_monitor/get_available_providers')
};

registerMenuHook('network_monitor', 'vpn_control', async (panelBody) => {
  panelBody.classList.add('vpn-panel-body');

  const skeleton = `
    <div class="vpn-status-line">
      <div class="vpn-status-copy">
        <span>Status:</span>
        <span id="vpn-status-text" style="color:var(--text-muted)">Detecting...</span>
      </div>
      <button class="vpn-power-btn" id="vpn-power-btn" disabled>Connect</button>
    </div>
    <div id="vpn-status-info" style="margin-bottom:12px;font-size:11px;color:var(--text-muted)">Getting information...</div>
    <div class="vpn-form">
      <label>Provider <input type="text" id="vpn-provider-input" placeholder="ProtonVPN, Mullvad, etc."></label>
      <label>Connect command <input type="text" id="vpn-connect-cmd" placeholder="windscribe connect"></label>
      <label>Disconnect command <input type="text" id="vpn-disconnect-cmd" placeholder="windscribe disconnect"></label>
      <label>Adapter keywords <input type="text" id="vpn-keywords" placeholder="ProtonVPN, wg, nordlynx"></label>
    </div>
    <div id="vpn-providers-section" style="margin-top:12px">
      <div class="vpn-section-title">Detected Providers</div>
      <div id="vpn-providers-list" style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px;color:var(--text-muted);font-size:11px">Scanning...</div>
    </div>
    <div id="vpn-last-action" class="vpn-feedback"></div>
    <div class="vpn-feedback" id="vpn-feedback"></div>
  `;
  panelBody.innerHTML = skeleton;

  _vpnCache.config.then(r => {
    const cfg = (r.value || {});
    const el = panelBody.querySelector('#vpn-provider-input');
    if (el) el.value = cfg.provider || '';
    const el2 = panelBody.querySelector('#vpn-connect-cmd');
    if (el2) el2.value = cfg.connect_command || '';
    const el3 = panelBody.querySelector('#vpn-disconnect-cmd');
    if (el3) el3.value = cfg.disconnect_command || '';
    const el4 = panelBody.querySelector('#vpn-keywords');
    if (el4) el4.value = (Array.isArray(cfg.adapter_keywords) ? cfg.adapter_keywords : (cfg.adapter_keywords || '').split(',')).map(s => s.trim()).filter(Boolean).join(', ');
    const el5 = panelBody.querySelector('#vpn-last-action');
    if (el5 && cfg.last_action) el5.textContent = cfg.last_action;
  }).catch(() => {});

  _vpnCache.status.then(r => {
    const st = (r.value || {});
    const isActive = st.active || false;
    const stText = panelBody.querySelector('#vpn-status-text');
    if (stText) {
      stText.textContent = isActive ? 'Connected' : 'Disconnected';
      stText.style.color = isActive ? 'var(--accent-green)' : 'var(--accent-red)';
    }
    const stInfo = panelBody.querySelector('#vpn-status-info');
    if (stInfo) stInfo.textContent = st.text || '';
    const powerBtn = panelBody.querySelector('#vpn-power-btn');
    if (powerBtn) {
      powerBtn.textContent = isActive ? 'Disconnect' : 'Connect';
      powerBtn.disabled = false;
    }
    attachVpnEvents(panelBody);
  }).catch(() => {
    const stText = panelBody.querySelector('#vpn-status-text');
    if (stText) { stText.textContent = 'Error'; stText.style.color = 'var(--accent-red)'; }
    const powerBtn = panelBody.querySelector('#vpn-power-btn');
    if (powerBtn) { powerBtn.disabled = false; attachVpnEvents(panelBody); }
  });

  _vpnCache.providers.then(r => {
    const provs = (r.value || []);
    const list = panelBody.querySelector('#vpn-providers-list');
    if (!list) return;
    if (provs.length) {
      list.innerHTML = provs.map(p =>
        `<button class="vpn-provider-chip ${p.active ? 'active' : ''}" data-provider="${escapeHtml(p.id)}">${escapeHtml(p.name)} ${p.active ? '•' : ''}</button>`
      ).join('');
      list.querySelectorAll('.vpn-provider-chip').forEach(chip => {
        chip.addEventListener('click', async () => {
          const target = chip.dataset.provider;
          list.querySelectorAll('.vpn-provider-chip').forEach(c => c.classList.remove('active'));
          chip.classList.add('active');
          const feedback = panelBody.querySelector('#vpn-feedback');
          const merged = (panelBody.querySelector('#vpn-provider-input')?.value?.trim?.() ? { provider: panelBody.querySelector('#vpn-provider-input').value.trim(), connect_command: panelBody.querySelector('#vpn-connect-cmd')?.value?.trim?.() || '', disconnect_command: panelBody.querySelector('#vpn-disconnect-cmd')?.value?.trim?.() || '', adapter_keywords: (panelBody.querySelector('#vpn-keywords')?.value || '').split(',').map(s => s.trim()).filter(Boolean) } : {});
          Object.assign(merged, { target_provider: target });
          try {
            if (feedback) { feedback.textContent = 'Executing...'; feedback.style.color = 'var(--accent-green)'; }
            await apiFetch('/api/extension/network_monitor/save_vpn_config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(merged) });
            const result = await apiFetch('/api/extension/network_monitor/connect_vpn', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ target_provider: target }) });
            if (feedback) feedback.textContent = result.value?.message || 'OK';
          } catch (e) {
            if (feedback) { feedback.textContent = 'Error: ' + (e.message || e); feedback.style.color = 'var(--accent-red)'; }
          }
        });
      });
    } else {
      list.textContent = 'No VPN detected';
      list.style.color = 'var(--text-muted)';
    }
  }).catch(() => {
    const list = panelBody.querySelector('#vpn-providers-list');
    if (list) { list.textContent = 'Detection error'; list.style.color = 'var(--accent-red)'; }
  });
});

function attachVpnEvents(panelBody) {
  const feedback = panelBody.querySelector('#vpn-feedback');
  const powerBtn = panelBody.querySelector('#vpn-power-btn');
  if (!powerBtn) return;

  function showFeedback(msg, isError = false) {
    if (feedback) { feedback.textContent = msg; feedback.style.color = isError ? 'var(--accent-red)' : 'var(--accent-green)'; }
  }

  function getConfigFromForm() {
    return {
      provider: panelBody.querySelector('#vpn-provider-input')?.value?.trim?.() || '',
      connect_command: panelBody.querySelector('#vpn-connect-cmd')?.value?.trim?.() || '',
      disconnect_command: panelBody.querySelector('#vpn-disconnect-cmd')?.value?.trim?.() || '',
      adapter_keywords: (panelBody.querySelector('#vpn-keywords')?.value || '').split(',').map(s => s.trim()).filter(Boolean)
    };
  }

  async function saveConfigThen(payload, actionFn) {
    const formCfg = getConfigFromForm();
    const merged = { ...formCfg, ...payload };
    try {
      await apiFetch('/api/extension/network_monitor/save_vpn_config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(merged) });
      showFeedback('Executing...');
      const result = await actionFn(merged);
      if (result.value && result.value.error) {
        showFeedback('Error: ' + result.value.error, true);
      } else {
        showFeedback(result.value?.message || 'OK');
        const newStatus = result.value?.status;
        if (newStatus) {
          panelBody.querySelector('#vpn-status-text').textContent = newStatus.active ? 'Connected' : 'Disconnected';
          panelBody.querySelector('#vpn-status-text').style.color = newStatus.active ? 'var(--accent-green)' : 'var(--accent-red)';
          powerBtn.textContent = newStatus.active ? 'Disconnect' : 'Connect';
        }
      }
    } catch (err) {
      showFeedback('Error: ' + (err.message || String(err)), true);
    }
  }

  powerBtn.addEventListener('click', async () => {
    const isActive = powerBtn.textContent === 'Disconnect';
    if (isActive) {
      await saveConfigThen({}, async () => apiFetch('/api/extension/network_monitor/disconnect_vpn', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) }));
    } else {
      await saveConfigThen({}, async () => apiFetch('/api/extension/network_monitor/connect_vpn', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) }));
    }
  });
}

function renderVpnPanel(panelBody, st, cfg, provs) {
  const active = st.active || false;
  const provider = st.provider || cfg.provider || '—';
  const text = st.text || 'No info';
  const lastAction = st.last_action || cfg.last_action || '';

  panelBody.innerHTML = `
    <div class="vpn-status-line">
      <div class="vpn-status-copy">
        <span>Status:</span>
        <span style="color:${active ? 'var(--accent-green)' : 'var(--accent-red)'}">
          ${active ? 'Connected' : 'Disconnected'}
        </span>
      </div>
      <button class="vpn-power-btn" id="vpn-power-btn">
        ${active ? 'Disconnect' : 'Connect'}
      </button>
    </div>
    <div class="vpn-status-copy" style="margin-bottom:12px;font-size:11px;color:var(--text-secondary)">
      ${escapeHtml(text)}
    </div>
    <div class="vpn-form">
      <label>
        Provider
        <input type="text" id="vpn-provider-input" value="${escapeHtml(provider)}" placeholder="ProtonVPN, Mullvad, etc.">
      </label>
      <label>
        Connect command
        <input type="text" id="vpn-connect-cmd" value="${escapeHtml(cfg.connect_command || '')}" placeholder="${escapeHtml(provs[0]?.cli_connect || 'windscribe connect')}">
      </label>
      <label>
        Disconnect command
        <input type="text" id="vpn-disconnect-cmd" value="${escapeHtml(cfg.disconnect_command || '')}" placeholder="${escapeHtml(provs[0]?.cli_disconnect || 'windscribe disconnect')}">
      </label>
      <label>
        Adapter keywords (comma separated)
        <input type="text" id="vpn-keywords" value="${escapeHtml((Array.isArray(cfg.adapter_keywords) ? cfg.adapter_keywords : (cfg.adapter_keywords || '').split(',')).map(s => s.trim()).filter(Boolean).join(', '))}" placeholder="ProtonVPN, wg, nordlynx">
      </label>
    </div>
    ${provs.length ? `
    <div style="margin-top:12px">
      <div class="vpn-section-title">Detected Providers</div>
      <div style="display:flex;flex-wrap:wrap;gap:4px;margin-top:6px">
        ${provs.map(p => `
          <button class="vpn-provider-chip ${p.active ? 'active' : ''}" data-provider="${escapeHtml(p.id)}">
            ${escapeHtml(p.name)} ${p.active ? '•' : ''}
          </button>
        `).join('')}
      </div>
    </div>
    ` : ''}
    ${lastAction ? `<div class="vpn-feedback">${escapeHtml(lastAction)}</div>` : ''}
    <div class="vpn-feedback" id="vpn-feedback"></div>
  `;

  const feedback = panelBody.querySelector('#vpn-feedback');
  const powerBtn = panelBody.querySelector('#vpn-power-btn');

  function showFeedback(msg, isError = false) {
    feedback.textContent = msg;
    feedback.style.color = isError ? 'var(--accent-red)' : 'var(--accent-green)';
  }

  function getConfigFromForm() {
    return {
      provider: panelBody.querySelector('#vpn-provider-input').value.trim(),
      connect_command: panelBody.querySelector('#vpn-connect-cmd').value.trim(),
      disconnect_command: panelBody.querySelector('#vpn-disconnect-cmd').value.trim(),
      adapter_keywords: panelBody.querySelector('#vpn-keywords').value.split(',').map(s => s.trim()).filter(Boolean)
    };
  }

  async function saveConfigThen(payload, actionFn) {
    const formCfg = getConfigFromForm();
    const merged = { ...formCfg, ...payload };
    await apiFetch('/api/extension/network_monitor/save_vpn_config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(merged)
    });
    showFeedback('Executing...');
    const result = await actionFn(merged);
    if (result.value && result.value.error) {
      showFeedback('Error: ' + result.value.error, true);
    } else {
      showFeedback(result.value?.message || 'OK');
      const newStatus = result.value?.status;
      if (newStatus) {
        panelBody.querySelector('.vpn-status-copy span:last-child').textContent = newStatus.active ? 'Connected' : 'Disconnected';
        panelBody.querySelector('.vpn-status-copy span:last-child').style.color = newStatus.active ? 'var(--accent-green)' : 'var(--accent-red)';
        powerBtn.textContent = newStatus.active ? 'Disconnect' : 'Connect';
      }
    }
  }

  powerBtn.addEventListener('click', async () => {
    if (active) {
      await saveConfigThen({}, async () => {
        const r = await apiFetch('/api/extension/network_monitor/disconnect_vpn', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({})
        });
        return r;
      });
    } else {
      await saveConfigThen({}, async () => {
        const r = await apiFetch('/api/extension/network_monitor/connect_vpn', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({})
        });
        return r;
      });
    }
  });

  panelBody.querySelectorAll('.vpn-provider-chip').forEach(chip => {
    chip.addEventListener('click', async () => {
      const target = chip.dataset.provider;
      panelBody.querySelectorAll('.vpn-provider-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      await saveConfigThen({ target_provider: target }, async () => {
        const r = await apiFetch('/api/extension/network_monitor/connect_vpn', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target_provider: target })
        });
        return r;
      });
    });
  });
}

registerMenuHook('network_monitor', 'show_ports_panel', async (panelBody) => {
  panelBody.classList.add('net-inspector-body');
  panelBody.innerHTML = '<div class="flex items-center gap-8"><div class="spinner"></div>Scanning ports...</div>';

  const [data, incoming, outgoing] = await Promise.all([
    apiFetch('/api/extension/network_monitor/get_open_ports'),
    apiFetch('/api/extension/network_monitor/get_incoming'),
    apiFetch('/api/extension/network_monitor/get_outgoing')
  ]);
  if (data.error) {
    panelBody.innerHTML = '<span class="text-red">Error: ' + escapeHtml(data.error) + '</span>';
    return;
  }

  const ports = Array.isArray(data.value) ? data.value : [];
  const incList = Array.isArray(incoming.value) ? incoming.value : [];
  const outList = Array.isArray(outgoing.value) ? outgoing.value : [];

  panelBody.innerHTML = `
    <div class="net-section">
      <div class="net-section-title">
        Open Ports <span class="net-count">(${ports.length})</span>
        <span class="net-subtitle">Quick local scan</span>
      </div>
      <div class="net-port-grid">
        ${ports.length ? ports.map(p => `
          <span class="net-port-badge">${escapeHtml(p.label)}</span>
        `).join('') : '<span style="color:var(--text-muted);font-size:11px">No common open ports</span>'}
      </div>
    </div>

    <div class="net-tabs">
      <button class="net-tab active" data-tab="incoming">Incoming (${incList.length})</button>
      <button class="net-tab" data-tab="outgoing">Outgoing (${outList.length})</button>
    </div>

    <div id="net-tab-content"></div>
  `;

  const content = panelBody.querySelector('#net-tab-content');
  let showingAll = false;

  function renderTable(rows, emptyMsg) {
    if (!rows.length) return '<div style="color:var(--text-muted);font-size:11px;padding:8px 6px">' + emptyMsg + '</div>';
    const sorted = [...rows].sort((a, b) => {
      return (b.process && b.process !== '' ? 1 : 0) - (a.process && a.process !== '' ? 1 : 0);
    });
    const limit = showingAll ? sorted.length : 200;
    const hasMore = sorted.length > 200;
    const part = sorted.slice(0, limit);
    return `<div class="net-table-header"><span>Proto</span><span>Local</span><span>Remote</span><span>State</span><span>Process</span></div>
      ${hasMore && !showingAll ? `<div style="color:var(--text-muted);font-size:10px;padding:2px 6px">Showing 200 of ${sorted.length} connections</div>` : ''}
      <div class="net-table-body">
        ${part.map(c => `
          <div class="net-row">
            <span class="net-proto">${escapeHtml(c.proto || '')}</span>
            <span class="net-addr">${escapeHtml(c.local || '')}</span>
            <span class="net-addr">${escapeHtml(c.remote || '—')}</span>
            <span class="net-state">${escapeHtml(c.state || '')}</span>
            <span class="net-proc">${escapeHtml(c.process || '')}</span>
          </div>
        `).join('')}
      </div>
      ${hasMore && !showingAll ? `<button class="vpn-power-btn" style="margin:8px auto;display:block;font-size:10px;padding:4px 12px" id="btn-show-all">See more (${sorted.length - 200} remaining)</button>` : ''}`;
  }

  function showTab(tab, expand) {
    if (!expand) showingAll = false;
    panelBody.querySelectorAll('.net-tab').forEach(t => t.classList.remove('active'));
    const btn = panelBody.querySelector(`.net-tab[data-tab="${tab}"]`);
    if (btn) btn.classList.add('active');
    if (tab === 'incoming') {
      content.innerHTML = renderTable(incList, 'No incoming connections');
    } else {
      content.innerHTML = renderTable(outList, 'No outgoing connections');
    }
    const showMore = content.querySelector('#btn-show-all');
    if (showMore) {
      showMore.addEventListener('click', () => {
        showingAll = true;
        showTab(tab, true);
      });
    }
  }

  panelBody.querySelectorAll('.net-tab').forEach(tab => {
    tab.addEventListener('click', () => showTab(tab.dataset.tab, false));
  });

  showTab('incoming');
});
