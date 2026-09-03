// ── CoreFrame Permission System ─────────────────────────────────────
// Handles consent modals, escalation requests, and legacy migration.

(function () {
  'use strict';

  const LEVEL_LABELS = {
    0: 'Basic',
    1: 'Storage',
    2: 'User Files',
    3: 'Network',
    4: 'System',
    5: 'Admin',
  };

  const LEVEL_COLORS = {
    0: '#00ff88',
    1: '#00d4ff',
    2: '#00d4ff',
    3: '#ffbb00',
    4: '#ff6600',
    5: '#ff3355',
  };

  const LEVEL_DESCRIPTIONS = {
    0: 'No access to system resources',
    1: 'Only accesses its own local data',
    2: 'Accesses files manually selected by the user',
    3: 'Makes outgoing network connections (HTTP/HTTPS)',
    4: 'Accesses system information (CPU, RAM, processes)',
    5: 'Full system control: files, registry, services',
  };

  // ── Consent Modal ────────────────────────────────────────────────

  function showConsentModal(extId, extName, level, permissions) {
    return new Promise((resolve) => {
      const overlay = document.getElementById('overlay');
      const existing = document.getElementById('perm-modal');
      if (existing) existing.remove();

      const levelLabel = LEVEL_LABELS[level] || `Level ${level}`;
      const color = LEVEL_COLORS[level] || '#00d4ff';
      const description = permissions?.description || LEVEL_DESCRIPTIONS[level] || '';
      const requires = permissions?.requires || [];

      const modal = document.createElement('div');
      modal.id = 'perm-modal';
      modal.className = 'perm-modal';
      modal.innerHTML = `
        <div class="perm-modal-content">
          <div class="perm-modal-header">
            <div class="perm-modal-icon" style="color:${color}">
              <i data-feather="shield" width="24" height="24"></i>
            </div>
            <h3 class="perm-modal-title">Permission Required</h3>
          </div>
          <div class="perm-modal-body">
            <p class="perm-modal-ext-name">${escapeHtml(extName)}</p>
            <div class="perm-modal-level" style="border-color:${color};color:${color}">
              ${escapeHtml(levelLabel)}
            </div>
            <p class="perm-modal-desc">${escapeHtml(description)}</p>
            ${requires.length > 0 ? `
              <div class="perm-modal-requires">
                <span class="perm-modal-requires-label">Requires:</span>
                ${requires.map(r => `<span class="perm-modal-tag">${escapeHtml(r)}</span>`).join('')}
              </div>
            ` : ''}
            ${level >= 5 ? `
              <div class="perm-modal-warning">
                <i data-feather="alert-triangle" width="16" height="16"></i>
                <span>This level grants full system control. Only grant it if you trust this extension.</span>
              </div>
            ` : ''}
            ${level === 4 ? `
              <div class="perm-modal-warning level-system">
                <i data-feather="info" width="16" height="16"></i>
                <span>Can access system information such as processes, memory, and files.</span>
              </div>
            ` : ''}
          </div>
          <div class="perm-modal-actions">
            <button class="perm-btn perm-btn-deny" id="perm-deny">Deny</button>
            <button class="perm-btn perm-btn-grant" id="perm-grant" style="border-color:${color};color:${color}">Grant</button>
          </div>
        </div>
      `;

      document.body.appendChild(modal);
      overlay.classList.add('open');
      if (typeof feather !== 'undefined') feather.replace();

      const cleanup = (granted) => {
        modal.remove();
        overlay.classList.remove('open');
        resolve(granted);
      };

      document.getElementById('perm-deny').addEventListener('click', () => cleanup(false));
      document.getElementById('perm-grant').addEventListener('click', () => cleanup(true));
      overlay.addEventListener('click', function handler() {
        overlay.removeEventListener('click', handler);
        cleanup(false);
      });
    });
  }

  // ── Escalation Modal ─────────────────────────────────────────────

  function showEscalationModal(extId, extName, method, level) {
    return new Promise((resolve) => {
      const overlay = document.getElementById('overlay');
      const existing = document.getElementById('perm-escalation-modal');
      if (existing) existing.remove();

      const levelLabel = LEVEL_LABELS[level] || `Level ${level}`;
      const color = LEVEL_COLORS[level] || '#ff3355';

      const modal = document.createElement('div');
      modal.id = 'perm-escalation-modal';
      modal.className = 'perm-modal';
      modal.innerHTML = `
        <div class="perm-modal-content perm-modal-escalation">
          <div class="perm-modal-header">
            <div class="perm-modal-icon" style="color:${color}">
              <i data-feather="alert-triangle" width="24" height="24"></i>
            </div>
            <h3 class="perm-modal-title">Permission Escalation</h3>
          </div>
          <div class="perm-modal-body">
            <p class="perm-modal-ext-name">${escapeHtml(extName)}</p>
            <div class="perm-modal-level" style="border-color:${color};color:${color}">
              ${escapeHtml(levelLabel)}
            </div>
            <p class="perm-modal-method">
              <code>${escapeHtml(method)}</code>
            </p>
            <p class="perm-modal-desc">This action requires elevated permissions. Grant temporarily or permanently.</p>
          </div>
          <div class="perm-modal-actions">
            <button class="perm-btn perm-btn-deny" id="esc-deny">Deny</button>
            <button class="perm-btn perm-btn-temp" id="esc-temp">Once</button>
            <button class="perm-btn perm-btn-grant" id="esc-permanent" style="border-color:${color};color:${color}">Always</button>
          </div>
        </div>
      `;

      document.body.appendChild(modal);
      overlay.classList.add('open');
      if (typeof feather !== 'undefined') feather.replace();

      const cleanup = (grantType) => {
        modal.remove();
        overlay.classList.remove('open');
        resolve(grantType);
      };

      document.getElementById('esc-deny').addEventListener('click', () => cleanup('deny'));
      document.getElementById('esc-temp').addEventListener('click', () => cleanup('temp'));
      document.getElementById('esc-permanent').addEventListener('click', () => cleanup('permanent'));
      overlay.addEventListener('click', function handler() {
        overlay.removeEventListener('click', handler);
        cleanup('deny');
      });
    });
  }

  // ── Migration Modal ──────────────────────────────────────────────

  function showMigrationModal(extId, extName) {
    return new Promise((resolve) => {
      const overlay = document.getElementById('overlay');
      const existing = document.getElementById('perm-migration-modal');
      if (existing) existing.remove();

      const modal = document.createElement('div');
      modal.id = 'perm-migration-modal';
      modal.className = 'perm-modal';
      modal.innerHTML = `
        <div class="perm-modal-content perm-modal-migration">
          <div class="perm-modal-header">
            <div class="perm-modal-icon" style="color:#ffbb00">
              <i data-feather="alert-circle" width="24" height="24"></i>
            </div>
            <h3 class="perm-modal-title">Extension Without Permissions</h3>
          </div>
          <div class="perm-modal-body">
            <p class="perm-modal-ext-name">${escapeHtml(extName)}</p>
            <p class="perm-modal-desc">This extension has no permissions defined (legacy version). Select the access level it should have:</p>
            <div class="perm-migration-options">
              <label class="perm-migration-option">
                <input type="radio" name="migration-level" value="basic">
                <span class="perm-migration-label" style="color:${LEVEL_COLORS[0]}">Basic</span>
                <span class="perm-migration-desc">Visual interface only</span>
              </label>
              <label class="perm-migration-option">
                <input type="radio" name="migration-level" value="storage" checked>
                <span class="perm-migration-label" style="color:${LEVEL_COLORS[1]}">Storage</span>
                <span class="perm-migration-desc">Accesses its own files</span>
              </label>
              <label class="perm-migration-option">
                <input type="radio" name="migration-level" value="user_files">
                <span class="perm-migration-label" style="color:${LEVEL_COLORS[2]}">User Files</span>
                <span class="perm-migration-desc">Files selected by the user</span>
              </label>
              <label class="perm-migration-option">
                <input type="radio" name="migration-level" value="network">
                <span class="perm-migration-label" style="color:${LEVEL_COLORS[3]}">Network</span>
                <span class="perm-migration-desc">Outgoing network connections</span>
              </label>
              <label class="perm-migration-option">
                <input type="radio" name="migration-level" value="system">
                <span class="perm-migration-label" style="color:${LEVEL_COLORS[4]}">System</span>
                <span class="perm-migration-desc">System information</span>
              </label>
              <label class="perm-migration-option">
                <input type="radio" name="migration-level" value="admin">
                <span class="perm-migration-label" style="color:${LEVEL_COLORS[5]}">Admin</span>
                <span class="perm-migration-desc">Full control</span>
              </label>
            </div>
          </div>
          <div class="perm-modal-actions">
            <button class="perm-btn perm-btn-deny" id="mig-skip">Skip</button>
            <button class="perm-btn perm-btn-grant" id="mig-apply" style="border-color:#ffbb00;color:#ffbb00">Apply</button>
          </div>
        </div>
      `;

      document.body.appendChild(modal);
      overlay.classList.add('open');
      if (typeof feather !== 'undefined') feather.replace();

      const cleanup = (level) => {
        modal.remove();
        overlay.classList.remove('open');
        resolve(level);
      };

      document.getElementById('mig-skip').addEventListener('click', () => cleanup(null));
      document.getElementById('mig-apply').addEventListener('click', () => {
        const selected = document.querySelector('input[name="migration-level"]:checked');
        cleanup(selected ? selected.value : null);
      });
      overlay.addEventListener('click', function handler() {
        overlay.removeEventListener('click', handler);
        cleanup(null);
      });
    });
  }

  // ── Permission Badge for Extension Cards ─────────────────────────

  function createPermissionBadge(extData) {
    if (!extData.permissions || extData.permissions.level < 0) return '';
    const level = extData.permissions.level;
    if (level === 0) return '';
    const label = LEVEL_LABELS[level] || `N${level}`;
    const color = LEVEL_COLORS[level] || '#00d4ff';
    return `<span class="perm-badge" style="color:${color};border-color:${color}" title="${escapeHtml(label)}">${escapeHtml(label)}</span>`;
  }

  // ── WebSocket Event Handlers ─────────────────────────────────────

  function initPermissionHandlers() {
    const socket = window.__socket;
    if (!socket) return;

    // Extension needs consent
    socket.on('extension_needs_consent', async (data) => {
      const { id, name, level, permissions } = data;
      const granted = await showConsentModal(id, name, level, permissions);
      if (granted) {
        try {
          const res = await apiFetch(`/api/extensions/${id}/permissions/grant`, {
            method: 'POST',
            body: JSON.stringify({ level: level, escalations: [] }),
          });
          if (res && res.loaded) {
            location.reload();
          } else {
            showPermDeniedToast(name);
          }
        } catch (e) {
          console.error('[PERM] Failed to grant consent:', e);
        }
      } else {
        showPermDeniedToast(name);
        apiFetch(`/api/extensions/${id}/permissions/deny`, { method: 'POST' }).catch(() => {});
      }
    });

    // Extension needs escalation
    socket.on('extension_escalation_request', async (data) => {
      const { id, name, method, level } = data;
      const grantType = await showEscalationModal(id, name, method, level);
      try {
        if (grantType === 'permanent') {
          await apiFetch(`/api/extensions/${id}/permissions/escalation`, {
            method: 'POST',
            body: JSON.stringify({ method: method, grant: true, once: false }),
          });
        } else if (grantType === 'temp') {
          await apiFetch(`/api/extensions/${id}/permissions/escalation`, {
            method: 'POST',
            body: JSON.stringify({ method: method, grant: true, once: true }),
          });
        }
      } catch (e) {
        console.error('[PERM] Failed to handle escalation:', e);
      }
    });

    // Extension needs migration (legacy)
    socket.on('extension_legacy_detected', async (data) => {
      const { id, name } = data;
      const level = await showMigrationModal(id, name);
      if (level) {
        try {
          await apiFetch(`/api/extensions/${id}/migrate`, {
            method: 'POST',
            body: JSON.stringify({ level: level }),
          });
          location.reload();
        } catch (e) {
          console.error('[PERM] Failed to migrate:', e);
        }
      }
    });

    // Installation step: needs consent
    socket.on('extension_install_progress', async (data) => {
      if (data.step === 'needs_consent') {
        const level = data.level || 3;
        const granted = await showConsentModal(data.id, data.name, level, {});
        if (granted) {
          try {
            const res = await apiFetch(`/api/extensions/${data.id}/permissions/grant`, {
              method: 'POST',
              body: JSON.stringify({ level: level, escalations: [] }),
            });
            if (res && res.loaded) {
              location.reload();
            } else {
              showPermDeniedToast(data.name);
            }
          } catch (e) {
            console.error('[PERM] Failed to grant consent after install:', e);
          }
        } else {
          showPermDeniedToast(data.name);
        }
      } else if (data.step === 'needs_migration') {
        const level = await showMigrationModal(data.id, data.name);
        if (level) {
          try {
            await apiFetch(`/api/extensions/${data.id}/migrate`, {
              method: 'POST',
              body: JSON.stringify({ level: level }),
            });
            location.reload();
          } catch (e) {
            console.error('[PERM] Failed to migrate after install:', e);
          }
        }
      }
    });
  }

  // ── Check pending on startup ─────────────────────────────────────

  async function checkPendingOnStartup() {
    try {
      const pending = await apiFetch('/api/extensions/pending_consent');
      if (!pending || typeof pending !== 'object') return;

      const entries = Object.values(pending);
      if (entries.length === 0) return;

      // Show modals sequentially (not all at once)
      for (const entry of entries) {
        if (entry.type === 'consent') {
          const level = entry.level || 3;
          const perms = entry.permissions || {};
          const granted = await showConsentModal(entry.id, entry.name, level, perms);
          if (granted) {
            try {
              const res = await apiFetch(`/api/extensions/${entry.id}/permissions/grant`, {
                method: 'POST',
                body: JSON.stringify({ level: level, escalations: [] }),
              });
              if (res && res.loaded) {
                location.reload();
                return; // Reload after first grant
              } else {
                showPermDeniedToast(entry.name);
              }
            } catch (e) {
              console.error('[PERM] Failed to grant consent on startup:', e);
            }
          } else {
            showPermDeniedToast(entry.name);
            apiFetch(`/api/extensions/${entry.id}/permissions/deny`, { method: 'POST' }).catch(() => {});
          }
        } else if (entry.type === 'migration') {
          const level = await showMigrationModal(entry.id, entry.name);
          if (level) {
            try {
              await apiFetch(`/api/extensions/${entry.id}/migrate`, {
                method: 'POST',
                body: JSON.stringify({ level: level }),
              });
              location.reload();
              return;
            } catch (e) {
              console.error('[PERM] Failed to migrate on startup:', e);
            }
          }
        }
      }
    } catch (e) {
      console.error('[PERM] checkPendingOnStartup failed:', e);
    }
  }

  // ── Toast for denied permissions ─────────────────────────────────

  function showPermDeniedToast(extName) {
    const toast = document.createElement('div');
    toast.className = 'perm-toast';
    toast.innerHTML = `<span>${escapeHtml(extName)}: permission denied. Extension not loaded.</span>`;
    document.body.appendChild(toast);
    setTimeout(() => toast.classList.add('show'), 10);
    setTimeout(() => {
      toast.classList.remove('show');
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  }

  // ── Utility ──────────────────────────────────────────────────────

  function escapeHtml(str) {
    if (!str) return '';
    return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ── Public API ───────────────────────────────────────────────────

  window.__permissions = {
    showConsentModal,
    showEscalationModal,
    showMigrationModal,
    createPermissionBadge,
    initPermissionHandlers,
    checkPendingOnStartup,
    LEVEL_LABELS,
    LEVEL_COLORS,
  };
})();
