function initFortune() {
  var widget = document.querySelector('.ext-fortune_cookie');
  if (!widget) return;

  widget.innerHTML =
    '<div class="fortune-container">' +
      '<div class="fortune-text" id="fortune-text">Click Crack for wisdom...</div>' +
      '<div class="fortune-menu-row" style="display:flex;gap:6px;margin-top:8px;flex-shrink:0;justify-content:center;position:relative">' +
        '<button class="fortune-btn" id="fortune-crack">Crack</button>' +
        '<button class="fortune-btn fortune-gear" id="fortune-gear" title="Language"><i data-feather="settings"></i></button>' +
        '<div class="fortune-menu" id="fortune-menu">' +
          '<button class="fortune-menu-item" id="fortune-lang-en">EN</button>' +
          '<button class="fortune-menu-item" id="fortune-lang-es">ES</button>' +
        '</div>' +
      '</div>' +
    '</div>';

  try { if (window.feather) feather.replace(); } catch (e) {}

  function fetchFortune() {
    var textEl = document.getElementById('fortune-text');
    if (!textEl) return;
    textEl.textContent = 'Thinking...';
    apiFetch('/api/extension/fortune_cookie/get_fortune').then(function (data) {
      if (data && data.value) {
        textEl.textContent = data.value;
        textEl.style.opacity = '0';
        requestAnimationFrame(function () {
          textEl.style.transition = 'opacity 0.3s';
          textEl.style.opacity = '1';
        });
        setTimeout(function () {
          textEl.style.transition = '';
        }, 400);
      }
    });
  }

  function markLang(lang) {
    var en = document.getElementById('fortune-lang-en');
    var es = document.getElementById('fortune-lang-es');
    if (en) en.classList.toggle('active', lang === 'en');
    if (es) es.classList.toggle('active', lang === 'es');
  }

  function setLang(lang) {
    var textEl = document.getElementById('fortune-text');
    apiFetch('/api/extension/fortune_cookie/set_language', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ language: lang, current: textEl ? textEl.textContent : '' })
    }).then(function (data) {
      if (data && data.value) {
        markLang(data.value.language);
        menu.classList.remove('open');
        if (data.value.text && textEl) {
          textEl.textContent = data.value.text;
        } else {
          fetchFortune();
        }
      } else if (data && data.error && typeof showToast === 'function') {
        showToast(data.error);
      }
    });
  }

  document.getElementById('fortune-crack').addEventListener('click', function () {
    this.textContent = '*crack*';
    var self = this;
    setTimeout(function () { self.textContent = 'Crack'; }, 800);
    fetchFortune();
  });

  var menu = document.getElementById('fortune-menu');
  document.getElementById('fortune-gear').addEventListener('click', function (e) {
    e.stopPropagation();
    menu.classList.toggle('open');
  });
  document.addEventListener('click', function (e) {
    if (!e.target.closest('.fortune-menu-row')) menu.classList.remove('open');
  });
  document.getElementById('fortune-lang-en').addEventListener('click', function () { setLang('en'); });
  document.getElementById('fortune-lang-es').addEventListener('click', function () { setLang('es'); });

  apiFetch('/api/extension/fortune_cookie/get_config').then(function (data) {
    if (data && data.value) markLang(data.value.language);
  });

  fetchFortune();
}

(function wait() {
  if (typeof extensionsData !== 'undefined' && document.querySelector('.ext-fortune_cookie')) {
    initFortune();
    return;
  }
  setTimeout(wait, 200);
})();
