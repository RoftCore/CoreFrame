async function loadExtensionsAsync(tries) {
  // Retries: one failed call during a host restart used to leave the dashboard empty for good.
  tries = tries || 8;
  for (let attempt = 1; attempt <= tries; attempt++) {
    try {
      const data = await apiFetch('/api/extensions');
      if (data && !data.error && Object.keys(data).length) {
        extensionsData = data;
        window.extensionsData = data;
        for (const [extId, ext] of Object.entries(data)) {
          extensionLoadState[extId] = {
            status: ext.loadError ? 'error' : 'loaded',
            loadError: ext.loadError,
          };
        }
        buildSidebar(data);
        renderWidgets(data);
        loadExtensionAssets(data);
// Disabled extensions are installed and registered, but not running.
        for (const [extId, ext] of Object.entries(data)) {
          if (ext.disabled) addExtensionToUI(extId, ext);
        }
        return true;
      }
    } catch (e) {
      if (attempt === tries) console.error('Extension load attempt failed:', e);
    }
    if (attempt < tries) await new Promise(r => setTimeout(r, 700 * attempt));
  }
  console.error('Initial extension load failed after ' + tries + ' attempts');
  return false;
}

async function pollExtensionUpdates() {
  try {
    // Self-heal: an empty dashboard means the list never landed, and this poll runs every second.
    if (!Object.keys(extensionsData || {}).length && !pollExtensionUpdates._healing) {
      pollExtensionUpdates._healing = true;
      loadExtensionsAsync(3).finally(() => { pollExtensionUpdates._healing = false; });
    }
    const health = await apiFetch('/api/extensions/health');
    if (!health || health.error) return;
    let hasChanges = false;
    for (const [extId, info] of Object.entries(health)) {
      const prevState = extensionLoadState[extId] || { status: 'unknown' };
      extensionLoadState[extId] = {
        status: info.status,
        loadError: info.load_error,
        loaded: info.loaded,
      };
      if (prevState.status !== info.status || prevState.loaded !== info.loaded) {
        hasChanges = true;
        if (info.loaded && !prevState.loaded) {
          const extData = await apiFetch('/api/extensions');
          if (extData && extData[extId]) {
            extensionsData = extData;
            window.extensionsData = extData;
            addExtensionToUI(extId, extData[extId]);
          }
        } else if (info.status === 'error' || info.status === 'dead') {
          updateExtensionStatusInSidebar(extId, info.status, info.last_error);
        } else if (info.status === 'loading') {
          updateExtensionStatusInSidebar(extId, 'loading');
        }
      }
    }
    if (hasChanges && window.__widgetControl && !window.__coreframeDragging) {
      window.__widgetControl.applyWidgetState();
    }

    // Leftover placeholders: the branch above only fires on a loaded transition, which one that landed between renders never produces.
    const placeholders = document.querySelectorAll('.widget-extension.cf-placeholder');
    if (placeholders.length) {
      let stale = false;
      for (const el of placeholders) {
        const info = health[el.dataset.extId];
        if (info && info.loaded) { stale = true; break; }
      }
      if (stale) {
        const fresh = await apiFetch('/api/extensions');
        if (fresh && !fresh.error) {
          extensionsData = fresh;
          window.extensionsData = fresh;
          for (const el of placeholders) {
            const extId = el.dataset.extId;
            const ext = fresh[extId];
            if (ext && !ext.pending && !ext.disabled && el.dataset.placeholder === '1') {
              addExtensionToUI(extId, ext);
            }
          }
        }
      }
    }
  } catch (e) {}
}
