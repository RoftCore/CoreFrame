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
// One observer and one sweep for every card instead of one observer and one 8 s
// timer per card: with a thousand extensions loading, the per-card version left a
// thousand observers and a thousand timers alive until each card painted.
const cfPaintWatch = new Map();   // card -> deadline (ms)
let cfPaintMO = null;
let cfPaintSweep = null;

function cfPaintIsBar(n) {
  return n && n.nodeType === 1 &&
    (n.classList.contains('cf-loading-bars') || n.classList.contains('cf-placeholder-bar'));
}

function cfPaintRelease(card) {
  if (!card) return;
  cfPaintWatch.delete(card);
  if (cfPaintMO) { try { cfPaintMO.unobserve(card); } catch (e) {} }
}

function cfPaintClear(card) {
  cfPaintRelease(card);
  if (!card.isConnected) return;
  cfClearLoadingState(card);
  // The extension has painted: make its images decode off the main thread.
  if (typeof cfAsyncImages === 'function') cfAsyncImages(card);
}

function cfPaintOnMutations(records) {
  const hit = new Set();
  for (let i = 0; i < records.length; i++) {
    const r = records[i];
    const node = r.target;
    const el = node && node.nodeType === 1 ? node : (node && node.parentElement);
    const card = el && el.closest ? el.closest('.widget-extension') : null;
    if (!card || !cfPaintWatch.has(card)) continue;
    // A card that lost .cf-loading is done; stop watching it.
    if (!card.classList.contains('cf-loading')) { cfPaintRelease(card); continue; }
    if (r.type === 'characterData') { hit.add(card); continue; }
    // Ignore the shimmer bars appearing; anything else is the extension painting.
    let real = false;
    for (let j = 0; j < r.addedNodes.length && !real; j++) if (!cfPaintIsBar(r.addedNodes[j])) real = true;
    for (let j = 0; j < r.removedNodes.length && !real; j++) if (!cfPaintIsBar(r.removedNodes[j])) real = true;
    if (real) hit.add(card);
  }
  hit.forEach(cfPaintClear);
}

// Safety net: whatever happens, a card must never stay hidden forever. One timer
// for the whole queue, rescheduled to the earliest deadline.
function cfPaintArmSweep() {
  if (cfPaintSweep || !cfPaintWatch.size) return;
  let next = Infinity;
  cfPaintWatch.forEach(function (deadline) { if (deadline < next) next = deadline; });
  cfPaintSweep = setTimeout(function () {
    cfPaintSweep = null;
    const now = Date.now();
    const expired = [];
    cfPaintWatch.forEach(function (deadline, card) { if (deadline <= now) expired.push(card); });
    for (let i = 0; i < expired.length; i++) cfPaintClear(expired[i]);
    cfPaintArmSweep();
  }, Math.max(0, next - Date.now()));
}

function cfWatchForFirstPaint(card, extId) {
  if (!card || typeof MutationObserver === 'undefined') return;
  if (!card.classList.contains('cf-loading')) return;
  cfPaintWatch.set(card, Date.now() + 8000);
  if (!cfPaintMO) cfPaintMO = new MutationObserver(cfPaintOnMutations);
  // Watch the card: an extension that assigns widget.innerHTML drops .widget-body.
  cfPaintMO.observe(card, { childList: true, subtree: true, characterData: true });
  cfPaintArmSweep();
}

// Start the refresh clock and the deferred prime once an extension's card exists.
function cfStartExtensionClocks(extId, ext, card) {
  // A late card: index its DOM once and hand its widgets to the shared scheduler.
  if (typeof cfPollAddExtension === 'function') {
    cfPollIndexCard(card || cfPollCard(extId));
    cfPollAddExtension(extId, ext);
  }
  // Out-of-view cards freeze their animations instead of ticking for nobody.
  if (typeof cfIdleObserve === 'function') cfIdleObserve(card || (typeof cfPollCard === 'function' ? cfPollCard(extId) : null));
  // Deferred for js extensions so their script claims the card before the core writes.
  const isJs = (ext.js_modules || []).length > 0;
  if (cfNeedsWidgetPriming(ext, extId)) {
    if (isJs) {
      setTimeout(function () {
        if (cfNeedsWidgetPriming(ext, extId)) {
          if (typeof cfPollPrime === 'function') cfPollPrime(extId, ext);
          else (ext.widgets || []).forEach(wDef => refreshWidget(extId, wDef));
        }
      }, CF_PRIME_DEFER_MS);
    } else if (typeof cfPollPrime === 'function') {
      cfPollPrime(extId, ext);
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
      // One coalesced pass for the whole boot, not one full-document scan per card.
      if (typeof cfFeatherReplace === 'function') cfFeatherReplace();
      else if (typeof feather !== 'undefined') feather.replace();
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
    ? (ext.icon.startsWith('/') ? '<img src="' + ext.icon + '" alt="" loading="lazy" decoding="async" style="width:16px;height:16px">' : '<i data-feather="' + ext.icon + '" width="16" height="16"></i>')
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
