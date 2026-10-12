function createExtensionCard(ext) {
  try {
    return _createExtensionCardInner(ext);
  } catch (e) {
    console.error('[EXT] Error creating card for ' + (ext.id || '?') + ':', e);
    var el = document.createElement('div');
    el.className = 'widget widget-extension ext-error-boundary';
    el.dataset.extId = ext.id || '';
    el.style.gridColumn = 'span 2';
    el.style.gridRow = 'span 1';
    el.style.minWidth = '0';
    el.style.minHeight = '0';
    el.style.display = 'flex';
    el.style.alignItems = 'center';
    el.style.justifyContent = 'center';
    el.style.border = '1px solid rgba(255,51,85,0.3)';
    el.style.borderRadius = 'var(--radius-md)';
    el.style.background = 'rgba(255,51,85,0.05)';
    el.style.color = 'var(--accent-red)';
    el.style.fontFamily = 'var(--font-mono)';
    el.style.fontSize = '11px';
    el.style.textAlign = 'center';
    el.style.padding = '12px';
    el.innerHTML = '<div><div style="font-size:18px;margin-bottom:4px">&#x26A0;</div>' +
      '<div>Error loading</div><div style="font-size:9px;color:var(--text-muted);margin-top:2px">' +
      escapeHtml(ext.name || ext.id || 'extension') + '</div></div>';
    return el;
  }
}

function _createExtensionCardInner(ext) {
  const { id: extId, name, widgets, grid_size, overlayable } = ext;
  const gs = grid_size || EXT_DEFAULT_GRID;

  const el = document.createElement('div');
  el.className = `widget widget-extension ext-${extId}`;
  el.dataset.extId = extId;
  el.dataset.overlayable = overlayable ? 'true' : 'false';
  if (overlayable) el.classList.add('widget-overlayable');
  el.style.gridColumn = `span ${gs.w}`;
  el.style.gridRow = `span ${gs.h}`;
  el.style.minWidth = '0';
  el.style.minHeight = '0';

  const scroll = ext.scroll;
  if (scroll) {
    el.classList.add('ext-scroll');
    if (scroll === 'x') el.classList.add('ext-scroll-x');
    else if (scroll === 'y') el.classList.add('ext-scroll-y');
    else if (scroll === 'both') el.classList.add('ext-scroll-both');
  }
  if (ext.hideScrollbar) {
    const hs = ext.hideScrollbar;
    if (hs === true || hs === 'both') el.classList.add('ext-scrollbar-hide');
    else if (hs === 'x') el.classList.add('ext-scrollbar-hide-x');
    else if (hs === 'y') el.classList.add('ext-scrollbar-hide-y');
  }

  el.style.overflow = 'hidden';

  const header = document.createElement('div');
  header.className = 'widget-header';
  const headerText = document.createElement('span');
  headerText.textContent = name || extId;
  header.appendChild(headerText);
  el.appendChild(header);

  const body = document.createElement('div');
  body.className = 'widget-body';

  if (widgets && widgets.length > 0) {
    for (const wDef of widgets) {
      try {
        const sub = createSubWidget(wDef, extId);
        body.appendChild(sub);
      } catch (e) {
        console.error('[EXT] Error creating sub-widget ' + (wDef.id || '?') + ':', e);
        var errEl = document.createElement('div');
        errEl.className = 'widget-sub';
        errEl.style.cssText = 'color:var(--accent-red);font-size:10px;padding:8px;text-align:center;';
        errEl.textContent = 'Widget error';
        body.appendChild(errEl);
      }
    }
  }

  el.appendChild(body);
  return el;
}

// Mark a fresh card as loading; cfClearLoadingState() lifts it.
function cfMarkLoadingState(card, widgetCount) {
  if (!card || card.classList.contains('cf-loading')) return;
  card.classList.add('cf-loading');
  const bars = document.createElement('div');
  bars.className = 'cf-loading-bars';
  const count = Math.max(1, Math.min(widgetCount || 1, 6));
  for (let i = 0; i < count; i++) {
    const bar = document.createElement('div');
    bar.className = 'cf-placeholder-bar';
    if (i === count - 1 && count > 1) bar.style.width = '62%';
    bars.appendChild(bar);
  }
  card.appendChild(bars);
}

// Reveal a loading card once it has real content.
function cfClearLoadingState(card) {
  if (!card || !card.classList.contains('cf-loading')) return;
  card.classList.remove('cf-loading');
  const bars = card.querySelector('.cf-loading-bars');
  if (bars) bars.remove();
}

