// ── Widget rendering ──────────────────────────────────────────────

function renderWidgets(data) {
  const container = document.getElementById('main-content');
  if (typeof clearProgressTimers === 'function') clearProgressTimers();
  if (typeof clearDropdownMenus === 'function') clearDropdownMenus();
  container.innerHTML = '';
  const grid = document.createElement('div');
  grid.className = 'widget-grid';
  for (const [extId, ext] of Object.entries(data)) {
    if (ext.disabled) continue;      // no card for a disabled extension
    if (!ext.widgets || ext.widgets.length === 0) continue;
    try {
      // Pending extensions hold their real grid slot, so the layout is final from the first paint.
      const card = ext.pending
        ? createPlaceholderCard({ ...ext, id: extId })
        : createExtensionCard({ ...ext, id: extId });
      grid.appendChild(card);
      // The skeleton animates in like any card: it takes its grid slot, so it
      // should not pop in static. cfApplyAppearAnimation's once-flag means the
      // later promotion does not replay it.
      cfApplyAppearAnimation(card, ext);
      if (!ext.pending) {
        if ((ext.js_modules || []).length) cfMarkLoadingState(card, (ext.widgets || []).length);
        // A card built here starts in cf-loading, so it needs its own watcher:
        // addExtensionToUI only promotes placeholders and would leave this one
        // shimmering forever (the "stuck loading after a reload" case).
        cfWatchForFirstPaint(card, extId);
      }
    } catch (e) {
      console.error('[EXT] Failed to render card for ' + extId + ':', e);
    }
  }
  container.style.visibility = 'hidden';
  container.appendChild(grid);
  refreshAllWidgets(data);
  startWidgetIntervals(data);
  if (window.__widgetControl) window.__widgetControl.applyWidgetState();
}
