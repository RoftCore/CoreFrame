// ── Window mode state & F11 ───────────────────────────────────────

let currentWindowMode = new URLSearchParams(window.location.search).get('mode') || 'windowed';

function applyStartupMode() {
  var done = function () {
    try { var ae = document.activeElement; if (ae && typeof ae.blur === 'function') ae.blur(); } catch (e) {}
    document.body.classList.remove('booting');
  };
  setTimeout(done, 250);
}

function applyWindowModeFallback(mode) {
  if (mode === 'fullscreen') {
    if (document.fullscreenElement) document.exitFullscreen().catch(function(){});
    else document.documentElement.requestFullscreen().catch(function(){});
  } else {
    if (document.fullscreenElement) document.exitFullscreen().catch(function(){});
  }
}

function updateUrlMode(mode) {
  const url = new URL(window.location);
  url.searchParams.set('mode', mode);
  window.history.replaceState({}, '', url);
}

document.addEventListener('keydown', (e) => {
  if (e.key === 'F11') {
    e.preventDefault();
    const next = currentWindowMode === 'fullscreen' ? 'windowed' : 'fullscreen';
    if (window.pywebview) {
      pywebview.api.set_window_mode(next).then(function(applied) {
        currentWindowMode = next;
        updateUrlMode(next);
        if (!applied && next !== 'fullscreen') showToast('Reinicia CoreFrame para aplicar');
      }).catch(function(err) {
        console.warn('set_window_mode pywebview failed:', err);
        applyWindowModeFallback(next);
        currentWindowMode = next;
        updateUrlMode(next);
      });
    } else {
      applyWindowModeFallback(next);
      currentWindowMode = next;
      updateUrlMode(next);
    }
  }
});

// ── Minimize window ───────────────────────────────────────────────

document.getElementById('btn-minimize').addEventListener('click', function () {
  if (window.pywebview) {
    pywebview.api.minimize_window().catch(function(err) { console.warn('minimize_window failed:', err); });
  }
});

// ── Settings button (placeholder) ─────────────────────────────────

const settingsBtn = document.getElementById('btn-settings');
