// ── Extension UI ──────────────────────────────────────────────────

// True when the card body is no longer the host's bare widget scaffold.
// Skeleton and shimmer bars do not count: they are host paint, not extension paint.
function cfCardBodyClaimed(card) {
  if (!card) return false;
  const body = card.querySelector('.widget-body');
  if (!body) return card.children.length > 1;      // extension replaced the card
  for (const child of body.children) {
    if (child.classList.contains('widget-sub')) continue;
    if (child.classList.contains('cf-placeholder-bar')) continue;
    if (child.classList.contains('cf-loading-bars')) continue;
    return true;  // non-scaffold child
  }
  return false;
}

// Drop the loading shimmer on the first paint, which is a DOM mutation here.
function cfWatchForFirstPaint(card, extId) {
  if (!card || typeof MutationObserver === 'undefined') return;
  if (!card.classList.contains('cf-loading')) return;
  // Watch the card: an extension that assigns widget.innerHTML drops .widget-body.
  const isBarNode = function (n) {
    return n && n.nodeType === 1 &&
      (n.classList.contains('cf-loading-bars') || n.classList.contains('cf-placeholder-bar'));
  };
  const mo = new MutationObserver(function (records) {
    if (!card.isConnected || !card.classList.contains('cf-loading')) { mo.disconnect(); return; }
    for (const r of records) {
      const touched = [];
      for (let i = 0; i < r.addedNodes.length; i++) touched.push(r.addedNodes[i]);
      for (let i = 0; i < r.removedNodes.length; i++) touched.push(r.removedNodes[i]);
      if (r.type === 'characterData' && r.target) { cfClearLoadingState(card); mo.disconnect(); return; }
      // Ignore the shimmer bars appearing; anything else is the extension painting.
      if (touched.length && !touched.every(isBarNode)) {
        cfClearLoadingState(card);
        mo.disconnect();
        return;
      }
    }
  });
  mo.observe(card, { childList: true, subtree: true, characterData: true });
  // Safety net: whatever happens, the card must never stay hidden forever.
  setTimeout(function () {
    mo.disconnect();
    if (card.isConnected) cfClearLoadingState(card);
  }, 8000);
}

// Start the refresh clock and the deferred prime once an extension's card exists.
function cfStartExtensionClocks(extId, ext, card) {
  const interval = cfRefreshInterval(ext);
// The clock belongs to the core only while it owns the values; a handler redraws on demand.
  if (interval > 0 && cfCoreOwnsWidgets(ext, extId)) {
    (ext.widgets || []).forEach(wDef => {
      const key = `${extId}-${wDef.id}`;
      widgetTimers[key] = setInterval(() => refreshWidget(extId, wDef), interval);
    });
  }
  // Deferred for js extensions so their script claims the card before the core writes.
  const isJs = (ext.js_modules || []).length > 0;
  if (cfNeedsWidgetPriming(ext, extId)) {
    if (isJs) {
      setTimeout(function () {
        if (cfNeedsWidgetPriming(ext, extId)) {
          (ext.widgets || []).forEach(wDef => refreshWidget(extId, wDef));
        }
      }, CF_PRIME_DEFER_MS);
    } else {
      (ext.widgets || []).forEach(wDef => refreshWidget(extId, wDef));
    }
  }
  cfNotifyCardRerender(extId);
}

function addExtensionToUI(extId, ext) {
  const sidebar = document.getElementById('sidebar-extensions');
  if (sidebar) {
    const existing = sidebar.querySelector(`.sidebar-ext[data-ext-id="${extId}"]`);
    if (!existing) {
      const item = createSidebarExtensionItem(ext, extId);
      sidebar.appendChild(item);
      if (typeof feather !== 'undefined') feather.replace();
    }
  }
  // Disabled: listed, but no card, no assets and no polling.
  if (ext.disabled) {
    if (window.__wc) { window.__wc.exitEditMode && window.__wc.editMode && window.__wc.exitEditMode(); }
    return;
  }
  if (ext.widgets && ext.widgets.length > 0) {
    const grid = document.querySelector('.widget-grid');
    if (grid) {
      const existing = grid.querySelector(`.widget-extension.ext-${extId}`);
      // A pending extension holds its slot as a skeleton: swapped in place, or the grid grows by one per load.
      if (!existing || existing.dataset.placeholder === '1') {
        // Hold the skeleton for a minimum readable time, once only, or a fast extension makes it flicker.
        if (existing && existing.dataset.placeholder === '1' && !existing.dataset.cfDeferred) {
          const born = parseInt(existing.dataset.cfPhAt || '0', 10) || Date.now();
          const wait = CF_PLACEHOLDER_MIN_MS - (Date.now() - born);
          if (wait > 0) {
            existing.dataset.cfDeferred = '1';
            setTimeout(() => addExtensionToUI(extId, ext), wait);
            return;
          }
        }
        const card = createExtensionCard({ ...ext, id: extId });
        if (existing) {
          // The placeholder element survives the swap, so everything the real card was
          // built with (scroll, overlayable, grid size) is lost unless copied over.
          existing.className = card.className;
          existing.style.gridColumn = card.style.gridColumn;
          existing.style.gridRow = card.style.gridRow;
          existing.style.minWidth = card.style.minWidth;
          existing.style.minHeight = card.style.minHeight;
          existing.dataset.overlayable = card.dataset.overlayable;
          // Keep an extension-painted body: its boot ran once and will not repaint.
          const claimed = cfCardBodyClaimed(existing);
          const oldBody = existing.querySelector('.widget-body');
          const newBody = card.querySelector('.widget-body');
          if (!claimed && oldBody && newBody) oldBody.replaceWith(newBody);
          delete existing.dataset.placeholder;
          delete existing.dataset.cfDeferred;
          existing.classList.remove('cf-placeholder');
          existing.style.pointerEvents = '';  // the skeleton is inert
          if ((ext.js_modules || []).length) cfMarkLoadingState(existing, (ext.widgets || []).length);
          // No entrance animation: the skeleton already played it on arrival.
          cfWatchForFirstPaint(existing, extId);
          if (!claimed) loadExtensionAssets({ [extId]: ext });
          cfMarkExtensionLive(extId);
          cfStartExtensionClocks(extId, ext, existing);
          return;
        }
        grid.appendChild(card);
        if ((ext.js_modules || []).length) cfMarkLoadingState(card, (ext.widgets || []).length);
        cfApplyAppearAnimation(card, ext);
        cfWatchForFirstPaint(card, extId);
        loadExtensionAssets({ [extId]: ext });
        cfMarkExtensionLive(extId);
        cfStartExtensionClocks(extId, ext, card);
      }
    }
  }
  if (window.__widgetControl) {
    window.__widgetControl.applyWidgetState();
  }
}

function updateExtensionStatusInSidebar(extId, status, error = '') {
  const item = document.querySelector(`.sidebar-ext[data-ext-id="${extId}"]`);
  if (!item) return;
  const statusEl = item.querySelector('.ext-status');
  if (statusEl) {
    statusEl.className = `ext-status ${status}`;
    if (status === 'error' || status === 'dead') {
      statusEl.title = error || 'Failed to load';
    } else if (status === 'loading') {
      statusEl.title = 'Loading...';
    } else {
      statusEl.title = 'Loaded';
    }
  }
}

function createSidebarExtensionItem(ext, extId) {
  const item = document.createElement('div');
  item.className = 'sidebar-ext';
  item.dataset.extId = extId;
  const isError = extensionLoadState[extId]?.status === 'error';
  const isLoading = extensionLoadState[extId]?.status === 'loading';
  const iconHtml = ext.icon
    ? (ext.icon.startsWith('/') ? '<img src="' + ext.icon + '" alt="" style="width:16px;height:16px">' : '<i data-feather="' + ext.icon + '" width="16" height="16"></i>')
    : '<i data-feather="cpu" width="16" height="16"></i>';
  item.innerHTML = `
    <span class="ext-icon">${iconHtml}</span>
    <span class="ext-name">${escapeHtml(ext.name || extId)}</span>
    <span class="ext-status ${isError ? 'error' : isLoading ? 'loading' : 'loaded'}" 
          title="${isError ? escapeHtml(extensionLoadState[extId].loadError || 'Error') : isLoading ? 'Loading...' : 'Loaded'}">
      ${isError ? '✗' : isLoading ? '⟳' : '✓'}
    </span>
  `;
  item.addEventListener('click', () => {
    // A disabled extension has no card; its Enable button lives in Settings.
    if (ext.disabled) return;
    const widget = document.querySelector(`.widget-extension.ext-${extId}`);
    if (widget) {
      widget.scrollIntoView({ behavior: 'smooth', block: 'center' });
      widget.style.animation = 'pulse 1s ease';
      setTimeout(() => widget.style.animation = '', 1000);
    }
  });
  return item;
}
