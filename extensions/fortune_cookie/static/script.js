function initFortune() {
  var widget = document.querySelector('.ext-fortune_cookie');
  if (!widget) return;

  widget.innerHTML =
    '<div class="fortune-container">' +
      '<div class="fortune-text" id="fortune-text">Click the cookie for wisdom...</div>' +
      '<div style="display:flex;gap:6px;margin-top:8px">' +
        '<button class="fortune-btn" id="fortune-crack">\uD83E\uDD6A Crack</button>' +
        '<button class="fortune-btn fortune-btn-new" id="fortune-new">\u21BB New</button>' +
      '</div>' +
    '</div>';

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

  document.getElementById('fortune-crack').addEventListener('click', function () {
    this.textContent = '\uD83E\uDD6A *crack*';
    var self = this;
    setTimeout(function () { self.textContent = '\uD83E\uDD6A Crack'; }, 800);
    fetchFortune();
  });

  document.getElementById('fortune-new').addEventListener('click', fetchFortune);

  fetchFortune();
}

(function wait() {
  if (typeof extensionsData !== 'undefined' && document.querySelector('.ext-fortune_cookie')) {
    initFortune();
    return;
  }
  setTimeout(wait, 200);
})();
