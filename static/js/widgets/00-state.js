const widgetHistory = {};
const _widgetHash = {};
const _progressTimers = {};
const _dropdownMenus = [];

if (!window._dropdownCloseAdded) {
  document.addEventListener('click', function (e) {
    if (e.target.closest('input, textarea, [contenteditable]')) return;
    var anyOpen = false;
    document.querySelectorAll('.widget-dd-menu:not([style*="display: none"])').forEach(function (m) {
      m.style.display = 'none';
      anyOpen = true;
    });
    if (anyOpen) {
      document.querySelectorAll('.widget-extension').forEach(function (c) {
        if (!c.querySelector('.widget-dd-menu:not([style*="display: none"])')) {
          c.style.overflow = '';
        }
      });
    }
  });
  window._dropdownCloseAdded = true;
}

