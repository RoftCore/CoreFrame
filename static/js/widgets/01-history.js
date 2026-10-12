function clearProgressTimers() {
  for (const key in _progressTimers) {
    clearTimeout(_progressTimers[key]);
    delete _progressTimers[key];
  }
}

function clearDropdownMenus() {
  for (var i = 0; i < _dropdownMenus.length; i++) {
    var menu = _dropdownMenus[i];
    if (menu.parentNode) menu.parentNode.removeChild(menu);
  }
  _dropdownMenus.length = 0;
}

// Restore chart history from localStorage so it survives page reload
(function loadPersistedHistory() {
  try {
    var saved = localStorage.getItem('coreframe-widget-history');
    if (saved) Object.assign(widgetHistory, JSON.parse(saved));
  } catch (_) {}
})();

function persistWidgetHistory() {
  try {
    localStorage.setItem('coreframe-widget-history', JSON.stringify(widgetHistory));
  } catch (_) {}
}

function startProgressPoll(extId, id, action, interval) {
  const key = extId + '-' + id;
  if (_progressTimers[key]) clearTimeout(_progressTimers[key]);
  function poll() {
    var fill = document.getElementById('prog-fill-' + extId + '-' + id);
    var info = document.getElementById('prog-info-' + extId + '-' + id);
    var cur = document.getElementById('prog-cur-' + extId + '-' + id);
    if (!fill) return;
    apiFetch('/api/extension/' + extId + '/' + action).then(function (response) {
      if (response && response.value) {
        var val = response.value;
        var status = val.status || '';
        var progress = typeof val.progress === 'number' ? val.progress : 0;
        var total = typeof val.total === 'number' ? val.total : 0;
        var current = val.current || '';
        var error = val.error || '';
        var pct = total > 0 ? Math.min(Math.round((progress / total) * 100), 100) : 0;
        fill.style.width = pct + '%';
        if (info) {
          if (status === 'completed') {
            info.textContent = 'Done! ' + total + ' track' + (total !== 1 ? 's' : '');
            info.className = 'widget-progress-info widget-progress-done';
          } else if (status === 'error') {
            info.textContent = error || 'Error';
            info.className = 'widget-progress-info widget-progress-error';
          } else if (status === 'idle' || status === '') {
            info.textContent = total > 0 ? progress + ' / ' + total : 'Ready';
            info.className = 'widget-progress-info';
          } else {
            info.textContent = total > 0 ? progress + ' / ' + total : '...';
            info.className = 'widget-progress-info widget-progress-running';
          }
        }
        if (cur) {
          cur.textContent = current;
          cur.style.display = current ? '' : 'none';
        }
      }
    });
    _progressTimers[key] = setTimeout(poll, interval);
  }
  _progressTimers[key] = setTimeout(poll, 200);
}
