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
// The skeleton animates in like any card; the once-flag stops a replay on promotion.
      cfApplyAppearAnimation(card, ext);
      if (!ext.pending) {
        if ((ext.js_modules || []).length) cfMarkLoadingState(card, (ext.widgets || []).length);
// Cards built here need their own watcher; addExtensionToUI only promotes placeholders.
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
