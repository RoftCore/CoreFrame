let _COREFRAME_TOKEN = null;
async function ensureToken() {
  if (!_COREFRAME_TOKEN) {
    try {
      const res = await fetch('/api/token');
      const data = await res.json();
      _COREFRAME_TOKEN = data.token;
    } catch {}
  }
}

async function apiFetch(url, options = {}) {
  await ensureToken();
  try {
    const headers = { ...options.headers };
    if (_COREFRAME_TOKEN) headers['X-CoreFrame-Token'] = _COREFRAME_TOKEN;
    const res = await fetch(url, { ...options, headers });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    console.error(`[API] ${url}: ${err.message}`);
    return { error: err.message };
  }
}

function formatBytes(bytes) {
  if (!bytes || bytes === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return (bytes / Math.pow(1024, i)).toFixed(1) + ' ' + units[i];
}

function formatPercent(value) {
  if (value === undefined || value === null) return '--';
  return value.toFixed(1) + '%';
}

function formatTemp(value) {
  if (value === undefined || value === null) return '--';
  return value.toFixed(0) + '°C';
}

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

function escapeHtml(text) {
  if (text === undefined || text === null) return '';
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

function getProcessIcon(name) {
  const n = (name || '').toLowerCase();
  if (/chrome|edge|firefox|opera|safari|brave|vivaldi|msedge|iexplore|navigator/.test(n)) return '🌐';
  if (/code|cursor|windsurf|sublime|atom|notepad\+\+|notepad|textedit|gedit|vim|nvim|nano/.test(n)) return '📝';
  if (/terminal|cmd|powershell|gitbash|wsl|bash|zsh|sh\.exe|conhost|windowsterminal/.test(n)) return '💻';
  if (/spotify|music|wmplayer|itunes|audacity/.test(n)) return '🎵';
  if (/discord|slack|telegram|whatsapp|signal|messenger|wechat|teams|thunderbird|outlook/.test(n)) return '💬';
  if (/vlc|mpv|mplayer|wmplayer|potplayer|plex/.test(n)) return '🎬';
  if (/steam|epic|battlenet|origin|uplay|gog|game|unity|ue4|unreal/.test(n)) return '🎮';
  if (/winword|excel|powerpoint|word|excel|ppt|onenote|office|libreoffice|acrobat|pdf|acrord/.test(n)) return '📄';
  if (/explorer|finder|nautilus|thunar|dolphin|totalcmd|filezilla/.test(n)) return '📁';
  if (/python|node|java|javaw|dotnet|go|rustc|gcc|clang|make|cmake|gradle|mvn|rake/.test(n)) return '⚙️';
  if (/mysqld|postgres|mongod|redis|sqlservr|oracle|mariadb/.test(n)) return '🗄️';
  if (/nginx|apache|httpd|iis|tomcat|jenkins|docker|containerd/.test(n)) return '🌍';
  if (/sshd|ssh|putty|kitty|winscp|bitvise/.test(n)) return '🔐';
  if (/photoshop|illustrator|figma|gimp|blender|paint|mspaint|coreldraw|affinity|sketchup/.test(n)) return '🎨';
  if (/system|kernel|svchost|services|lsass|wininit|systemd|init|kthreadd|kworker|kern/.test(n)) return '⚡';
  if (/sleep|idle|suspended|stopped|parked/.test(n)) return '💤';
  return '⚪';
}

function clockTick() {
  const now = new Date();
  const h = String(now.getHours()).padStart(2, '0');
  const m = String(now.getMinutes()).padStart(2, '0');
  const s = String(now.getSeconds()).padStart(2, '0');
  document.getElementById('header-clock').textContent = `${h}:${m}:${s}`;
}
