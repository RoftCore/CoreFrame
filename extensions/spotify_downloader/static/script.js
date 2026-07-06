var _sdState = null;
var _sdPollTimer = null;

function initSpotifyDownloader() {
  var widget = document.querySelector('.ext-spotify_downloader');
  if (!widget) { setTimeout(initSpotifyDownloader, 300); return; }
  var body = widget.querySelector('.widget-body');
  if (!body) return;

  body.innerHTML =
    '<div class="sd-container">' +
      '<div class="sd-row" style="gap:4px">' +
        '<input class="sd-input" id="sd-url" type="text" placeholder="Spotify playlist URL..." spellcheck="false">' +
        '<button class="sd-btn sd-btn-primary" id="sd-go">Download</button>' +
        '<button class="sd-btn" id="sd-settings" title="Settings">\u2699</button>' +
      '</div>' +
      '<div class="sd-progress-wrap" id="sd-progress-wrap" style="display:none">' +
        '<div class="sd-progress-bar" id="sd-progress-bar"><div class="sd-progress-fill" id="sd-progress-fill"></div></div>' +
        '<div class="sd-progress-text" id="sd-progress-text"></div>' +
      '</div>' +
      '<div class="sd-current" id="sd-current"></div>' +
      '<div class="sd-result" id="sd-result"></div>' +
    '</div>';

  document.getElementById('sd-go').addEventListener('click', function () {
    var url = document.getElementById('sd-url').value.trim();
    if (!url) return;
    _sdStart(url);
  });

  document.getElementById('sd-url').addEventListener('keydown', function (e) {
    if (e.key === 'Enter') { document.getElementById('sd-go').click(); }
  });

  document.getElementById('sd-settings').addEventListener('click', function (e) {
    e.stopPropagation();
    _sdShowConfig();
  });
}

function _sdStart(url) {
  _sdSetUI('downloading');
  apiFetch('/api/extension/spotify_downloader/start_download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url: url })
  }).then(function (data) {
    if (data && data.error) {
      _sdSetUI('error', data.error);
      return;
    }
    _sdPoll();
  });
}

function _sdPoll() {
  if (_sdPollTimer) clearTimeout(_sdPollTimer);
  apiFetch('/api/extension/spotify_downloader/get_status').then(function (data) {
    if (!data || !data.value) { _sdPollTimer = setTimeout(_sdPoll, 1000); return; }
    _sdState = data.value;
    var s = data.value;
    if (s.status === 'downloading') {
      _sdUpdateProgress(s);
      _sdPollTimer = setTimeout(_sdPoll, 800);
    } else {
      _sdSetUI(s.status, s);
    }
  });
}

function _sdUpdateProgress(s) {
  var wrap = document.getElementById('sd-progress-wrap');
  var fill = document.getElementById('sd-progress-fill');
  var text = document.getElementById('sd-progress-text');
  var cur = document.getElementById('sd-current');
  wrap.style.display = 'block';
  var pct = s.total > 0 ? Math.round((s.progress / s.total) * 100) : 0;
  fill.style.width = Math.min(pct, 100) + '%';
  text.textContent = s.progress + ' / ' + s.total + ' tracks';
  cur.textContent = s.current || '';
}

function _sdSetUI(status, data) {
  var wrap = document.getElementById('sd-progress-wrap');
  var fill = document.getElementById('sd-progress-fill');
  var text = document.getElementById('sd-progress-text');
  var cur = document.getElementById('sd-current');
  var result = document.getElementById('sd-result');

  if (status === 'downloading') {
    wrap.style.display = 'block';
    fill.style.width = '0%';
    text.textContent = 'Starting...';
    cur.textContent = '';
    result.innerHTML = '';
    return;
  }

  if (status === 'completed') {
    wrap.style.display = 'none';
    cur.textContent = '';
    var name = data && data.playlist_name ? data.playlist_name : 'Playlist';
    var total = data && data.total ? data.total : '?';
    var missing = data && data.missing ? data.missing : [];
    var html = '<div class="sd-done">Done! ' + total + ' track' + (total !== 1 ? 's' : '') + ' downloaded.</div>';
    if (missing.length) {
      html += '<div class="sd-warn">' + missing.length + ' track' + (missing.length !== 1 ? 's' : '') + ' not found.</div>';
    }
    html += '<button class="sd-btn sd-btn-small" id="sd-open-folder">Open Folder</button>';
    result.innerHTML = html;
    var openBtn = document.getElementById('sd-open-folder');
    if (openBtn) {
      openBtn.addEventListener('click', function () {
        var p = (data && data.zip_path) || '';
        if (p) {
          var folder = p.substring(0, p.lastIndexOf('\\'));
          apiFetch('/api/extension/spotify_downloader/open_folder', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ path: folder })
          });
        }
      });
    }
    var goBtn = document.getElementById('sd-go');
    goBtn.textContent = 'Download';
    goBtn.disabled = false;
    document.getElementById('sd-url').disabled = false;
    return;
  }

  if (status === 'error') {
    var errMsg = data && data.error ? data.error : 'Unknown error';
    wrap.style.display = 'none';
    cur.textContent = '';
    result.innerHTML = '<div class="sd-error">Error: ' + errMsg + '</div>';
    var goBtn = document.getElementById('sd-go');
    goBtn.textContent = 'Download';
    goBtn.disabled = false;
    document.getElementById('sd-url').disabled = false;
    return;
  }

  // idle
  wrap.style.display = 'none';
  cur.textContent = '';
  result.innerHTML = '';
}

function _sdShowConfig() {
  apiFetch('/api/extension/spotify_downloader/get_config').then(function (data) {
    var cfg = data && data.value ? data.value : { quality: '320', format: 'mp3' };

    var overlay = document.createElement('div');
    overlay.className = 'sd-config-overlay';
    var dialog = document.createElement('div');
    dialog.className = 'sd-config-dialog';
    dialog.innerHTML =
      '<div class="sd-config-header">Spotify Downloader Settings</div>' +
      '<div class="sd-config-body">' +
        '<label class="sd-config-label">Quality (kbps)</label>' +
        '<select class="sd-config-select" id="sd-cfg-quality">' +
          '<option value="128"' + (cfg.quality === '128' ? ' selected' : '') + '>128 kbps</option>' +
          '<option value="192"' + (cfg.quality === '192' ? ' selected' : '') + '>192 kbps</option>' +
          '<option value="320"' + (cfg.quality === '320' ? ' selected' : '') + '>320 kbps</option>' +
        '</select>' +
        '<label class="sd-config-label">Format</label>' +
        '<select class="sd-config-select" id="sd-cfg-format">' +
          '<option value="mp3"' + (cfg.format === 'mp3' ? ' selected' : '') + '>MP3</option>' +
          '<option value="mp4"' + (cfg.format === 'mp4' ? ' selected' : '') + '>MP4</option>' +
        '</select>' +
        '<label class="sd-config-label">Download Path</label>' +
        '<div style="display:flex;gap:4px">' +
          '<input class="sd-input" id="sd-cfg-path" type="text" value="' + (cfg.download_path || '') + '" style="flex:1;min-width:0">' +
          '<button class="sd-btn" id="sd-cfg-browse" title="Browse">\uD83D\uDCC1</button>' +
        '</div>' +
      '</div>' +
      '<div class="sd-config-footer">' +
        '<button class="sd-btn" id="sd-cfg-cancel">Cancel</button>' +
        '<button class="sd-btn sd-btn-primary" id="sd-cfg-save">Save</button>' +
      '</div>';

    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    document.getElementById('sd-cfg-browse').addEventListener('click', function () {
      apiFetch('/api/extension/spotify_downloader/browse_folder').then(function (data) {
        if (data && data.value) {
          document.getElementById('sd-cfg-path').value = data.value;
        }
      });
    });

    document.getElementById('sd-cfg-cancel').addEventListener('click', function () { overlay.remove(); });
    document.getElementById('sd-cfg-save').addEventListener('click', function () {
      var quality = document.getElementById('sd-cfg-quality').value;
      var format = document.getElementById('sd-cfg-format').value;
      var path = document.getElementById('sd-cfg-path').value.trim();
      apiFetch('/api/extension/spotify_downloader/save_config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ quality: quality, format: format, download_path: path })
      });
      overlay.remove();
    });
  });
}

// Boot
(function boot() {
  if (typeof extensionsData !== 'undefined') { initSpotifyDownloader(); return; }
  setTimeout(boot, 300);
})();
