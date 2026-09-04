# Extension Guide — CoreFrame

## Table of Contents

1. [Extension Structure](#structure)
2. [extension.json — Complete Reference](#extensionjson)
3. [main.py — Python API](#mainpy)
4. [Widgets — Types and Configuration](#widgets--types)
5. [Custom Styles](#styles)
6. [JavaScript and CSS](#javascript-and-css)
7. [Menus and Actions](#menus-and-actions)
8. [Global Frontend Utilities](#global-frontend-utilities)
9. [Data Storage](#data-storage)
10. [Libraries (PyPI packages)](#libraries-pypi-packages)
11. [HTTP API reference](#http-api-reference)
12. [Real-time (WebSocket)](#real-time)
13. [Publishing an Extension](#publishing)
14. [Multi-language (Bridge)](#multi-language)

---

## Structure

```
extensions/mi_extension/
├── extension.json        # Required — configuration and widgets
├── main.py               # Required (Python) — logic
├── server.js             # Alternative if language != python
├── static/
│   ├── script.js         # Optional — JS injected in the frontend
│   └── style.css         # Optional — CSS injected in the frontend
└── lib/                  # Optional — shared dependencies
```

---

## extension.json

| Field | Type | Default | Required | Description |
|-------|------|---------|----------|-------------|
| `id` | string | — | ✅ | Unique identifier (snake_case) |
| `name` | string | — | ✅ | Display name |
| `icon` | string | `"extension"` | ❌ | Feather icon or emoji |
| `description` | string | — | ❌ | Short description |
| `version` | string | `"1.0"` | ❌ | Semantic version |
| `author` | string | — | ❌ | Author name |
| `category` | string | `"general"` | ❌ | Category (system, ui, cybersecurity, media, fun, general) |
| `language` | string | `"python"` | ❌ | `"python"` or `"node"` |
| `main` | string | `"main.py"` | ❌ | Main script based on language |
| `platforms` | string[] | all | ❌ | `["windows"]`, `["linux"]` or both |
| `grid_size` | object | `{"w":2,"h":1}` | ❌ | Default size in the grid |
| `overlayable` | bool | `false` | ❌ | Can overlap with other widgets |
| `realtime` | bool | `false` | ❌ | Uses WebSocket for push updates |
| `refresh_interval` | int | `5000` | ❌ | Polling interval in ms (0 = no polling) |
| `scroll` | string/bool | — | ❌ | `"x"`, `"y"`, `"both"` to enable overflow scroll on widget body. `false` or omit = no scroll |
| `hideScrollbar` | string/bool | `false` | ❌ | `true`/`"both"`, `"x"`, or `"y"` — hides scrollbar visually but keeps scroll functionality (WebKit: per-axis; Firefox: only `"both"`) |
| `menu_items` | array | `[]` | ❌ | Items in the side menu |
| `js_modules` | string[] | `[]` | ❌ | JS files in `static/` |
| `css_modules` | string[] | `[]` | ❌ | CSS files in `static/` |
| `widgets` | array | `[]` | ✅ | Array of widget definitions |
| `permissions` | object | — | ❌ | Permission declaration (see [Permissions](#permissions)) |

### permissions

CoreFrame 1.1.0 introduces a 6-level permission system with subprocess isolation. Every Python extension runs in its own OS process (`--ext-runner` embebido) with file/network/subprocess restrictions enforced at the OS level.

| Level | Name | Value | Description | Needs consent | Escalation |
|-------|------|-------|-------------|---------------|------------|
| `basic` | Básico | 0 | UI only, no file/network access | No | — |
| `storage` | Almacenamiento | 1 | Only `data_dir` (own files) | No | — |
| `user_files` | Archivos del usuario | 2 | Whitelisted files only (mediated via file dialog) | No | — |
| `network` | Red | 3 | Outbound HTTP/HTTPS + read `data_dir` | **Yes** | — |
| `system` | Sistema | 4 | Read system info, processes, registry (read-only) | **Yes** | `registry_write` → admin |
| `admin` | Admin | 5 | Full control: registry write, services, files | **Yes** | — |

Declare in `extension.json`:

```json
{
  "permissions": {
    "level": "system",
    "requires": ["system_info"],
    "mediated": false,
    "escalation": {
      "admin": {
        "methods": ["registry_write", "service_control", "delete_file", "toggle"],
        "description": "Deshabilitar entradas de inicio"
      }
    }
  }
}
```

- `level` < 3 loads without modal. `network`/`system`/`admin` show a consent modal on first load.
- If an extension later **raises its level** (e.g. `network` → `system`) while the user granted the old one, CoreFrame does NOT hard-deny. It re-asks consent at the new level (`needs_consent`), so the modal appears and the user can grant it.
- `escalation.admin.methods` lists actions that require **extra** admin approval even if base level is `system`. When the frontend calls one of those methods, CoreFrame shows a second modal: **Once** (single use, consumed after one successful call) vs **Always** (permanent). If denied, the widget must stay in waiting state for **10s** (cancellable) and then show a CoreFrame timeout message, not an error.

### What each level enforces (child process)

| Level | Files (`open`) | Network (`socket`) | Subprocess (`Popen`/`run`/`system`) |
|-------|----------------|--------------------|-------------------------------------|
| 0 `basic` | Nothing (only `TEMP` + own folder + exe internals) | Blocked | Blocked |
| 1 `storage` | Only own `data/<id>/` | Blocked | Blocked |
| 2 `user_files` | Own data + whitelisted files | Blocked | Blocked |
| 3 `network` | Own data (read-oriented) | **Allowed** | Blocked |
| 4 `system` | Any path (`/` = any absolute path on Windows) | Allowed | **Allowed** |
| 5 `admin` | Any path | Allowed | Allowed |

Implementation notes (so you understand the errors you may see):

- `socket` is replaced with a raisable **class** — libraries that only *import* it still load; creating a connection raises `PermissionError`.
- `subprocess.Popen` is replaced with a raisable **class** (`BlockedPopen`), not a function — libraries that *subclass* `Popen` at import time (e.g. `yt_dlp`) still import cleanly; only *spawning* raises `PermissionError`. (A plain-function replacement broke those imports with `TypeError: function() argument 'code' must be code, not str`.)
- `DATA_DIR` and `SHARED_LIB_DIR` are injected into your config as `config['_coreframe']`.
- Methods `get_config`, `get_entries`, `get_status`, `get_cpu`, `get_ram`, `get_gpu`, `get_disk`, `get_fortune`, `get_notes`, `get_ping` time out after **0.8s**; any other method after **30s**. After 3 timeouts the widget is marked `degraded` instead of blocking CoreFrame.

### Admin elevation (the right way)

Your extension runs isolated and can **never** `import coreframe.*` — there is no `from coreframe... import` available in the child process (especially in the frozen `.exe`). To perform an admin operation, ship the helper call **inside your own `main.py`** using temp JSON files + UAC (pattern used by `windows_autoruns`):

```python
import ctypes, json, os, sys, tempfile

def _get_helper_path():
    if getattr(sys, 'frozen', False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    p = os.path.join(base, "coreframe_helper.exe")
    if os.path.isfile(p):
        return p
    return os.path.join(os.path.expanduser("~"), "Documents", "CoreFrame", "coreframe_helper.exe")

def _elevated_via_helper(op_type, params, timeout=20):
    """Returns (ok, result). Triggers ONE Windows UAC prompt."""
    helper = _get_helper_path()
    tmp = tempfile.gettempdir()
    ts = int(__import__('time').time() * 1000)
    op_file = os.path.join(tmp, f"my_op_{ts}.json")
    res_file = os.path.join(tmp, f"my_res_{ts}.json")
    with open(op_file, 'w', encoding='utf-8') as f:
        json.dump({"type": op_type, "params": params}, f)
    ret = ctypes.windll.shell32.ShellExecuteW(None, "runas", helper, f'"{op_file}" "{res_file}"', None, 0)
    if ret <= 32:
        return False, f"UAC failed/cancelled (code {ret})"
    for _ in range(int(timeout * 10)):
        if os.path.exists(res_file):
            break
        __import__('time').sleep(0.1)
    if not os.path.exists(res_file):
        return False, "Helper timeout - no response"
    with open(res_file, 'r', encoding='utf-8') as f:
        res = json.load(f)
    for p in (op_file, res_file):
        try: os.remove(p)
        except Exception: pass
    if res.get('error'):
        return False, res['error']
    return True, res

# Usage:
ok, res = _elevated_via_helper("service_control", {"service": "SunshineService", "action": "disable"})
```

Helper operation types (`coreframe_helper.py` `HANDLERS`): `registry_write`, `system_command` (aliases: `bash`, `exec`), `write_file`, `edit_file` / `replace_file`, `delete_file`, `create_directory`, `service_control` (`status`/`start`/`stop`/`restart`/`enable`/`disable`), `adapter_control`, `batch` (multiple ops, single UAC prompt).

If you do direct `winreg`/`sc` without the helper, it fails with `Access is denied` unless CoreFrame itself runs as admin. With the helper, Windows shows **one UAC prompt** (blue screen) and most antiviruses whitelist `coreframe_helper.exe`.

### Frontend permission flow

Always use the global `apiFetch` (fetches `/api/token` itself and sends `X-CoreFrame-Token`). Important: it **never rejects** — HTTP errors resolve as `{error: "..."}` and the extra 403 fields are lost, so match on the message string:

```javascript
const r = await apiFetch('/api/extension/my_ext/toggle', {method:'POST', body:JSON.stringify({id})});
if (r.error && r.error.includes('Escalation')) {
  // Show ONE waiting UI for 10s with Cancel — do NOT retry toggle in a loop
  // (each retry fires another modal = spam).
  // Poll GET /api/extensions/my_ext/permissions every ~100ms until
  // granted_escalations includes your method, then retry toggle ONCE.
}
```

Rules:

- Never show `Error: Escalation required` in red. Show a waiting message (`Esperando permiso... 10s` + Cancel); on timeout show `CoreFrame: tiempo de espera agotado`, not `Error`.
- `Once` is consumed after **one successful call** — the next call asks again. `Always` persists in `permissions_consent.json`.
- Useful endpoints: `GET /api/extensions/<id>/permissions` (granted level + escalations), `POST .../permissions/grant` (`{level, escalations[]}`), `POST .../permissions/escalation` (`{method, grant, once}`), `POST .../permissions/revoke`, `GET /api/extensions/pending_consent` (startup polling).

### widgets[]

Each widget is an object:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✅ | Unique identifier within the extension |
| `type` | string | ✅ | Widget type (see [types](#widgets)) |
| `label` | string | ✅ | Visible label |
| `action` | string | ❌* | Python method to call for data retrieval |
| `click_action` | string | ❌ | Action when clicking the widget |
| `styles` | object | ❌ | Swappable styles (see [styles](#styles)) |

\* Required except for static widgets without data (`action: ""`)

---

## main.py

### Basic Structure

```python
class Extension:
    def __init__(self, config):
        self.config = config  # Dict with the extension.json content

    def mi_accion(self):
        return {"value": 42}
```

### How actions are called

- **GET** `/api/extension/<id>/<action>` calls `def action(self)` — no arguments. Use for reads.
- **POST** with a JSON body calls `def action(self, data)` — `data` is the parsed body dict. Use for writes.

```python
def get_notes(self):
    return {"value": [...]}

def create(self, data):          # POST {"title": ..., "body": ...}
    title = data.get("title", "Untitled")
    ...
    return {"value": [...]}
```

Method names starting with `_` are rejected (`Method not allowed`). Unknown methods return `Unknown method`.

### Response Format

Every action must return a dict. Accepted formats:

```python
# Simple value
return {"value": "texto"}                      # → widget text
return {"value": 42}                           # → widget text (numeric)
return {"value": {"status": "ok", "text": "VPN Connected"}}  # → widget badge
return {"value": [{"label": "Puerto", "value": "8080"}, ...]}  # → widget list

# Error
return {"error": "No se pudo conectar"}
```

The bridge returns your dict as-is when it already has `value`/`error` keys, so always wrap in one of the two shapes above. Keep data-fetch methods fast: they time out after **0.8s** (other methods: 30s).

### Lifecycle

```python
class Extension:
    def __init__(self, config):
        # Setup: load config, initialize connections, etc.
        pass

    def on_stop(self):
        # Cleanup when closing CoreFrame (optional)
        pass
```

### Accessing the Active Scene

```python
import json, os
# Global state is in widget_state.json
# But for most cases it's not needed — each action is independent
```

---

## Widgets — Types

### text

Displays a numeric value or text. Ideal for simple metrics.

```json
{ "id": "ping", "type": "text", "label": "Ping", "action": "get_ping" }
```

```python
def get_ping(self):
    return {"value": "23 ms"}
```

### badge

Status indicator with color dot.

```json
{ "id": "vpn", "type": "badge", "label": "VPN", "action": "check_vpn" }
```

```python
def check_vpn(self):
    return {"value": {"status": "ok", "text": "Connected"}}
```

Statuses: `ok` (green), `warn` (yellow), `error` (red).

### list

List of key/value items.

```json
{ "id": "puertos", "type": "list", "label": "Puertos", "action": "get_ports" }
```

```python
def get_ports(self):
    return {"value": [
        {"label": "HTTP", "value": "80 (open)"},
        {"label": "HTTPS", "value": "443 (open)"}
    ]}
```

### chart

Line chart (sparkline) with history of up to 30 values.

```json
{ "id": "cpu", "type": "chart", "label": "CPU", "action": "get_cpu" }
```

```python
def get_cpu(self):
    return {"value": {"percent": 45.2}}
```

Or a number directly: `return {"value": 45.2}`.

Colors are assigned as follows:
- `cpu` → `--accent-cyan` (`#00d4ff`)
- `ram` → `--accent-purple` (`#6644ff`)
- `disk` → `--accent-green` (`#00ff88`)
- `gpu` → `--accent-yellow` (`#ffbb00`)
- others → `--accent-blue` (`#0088ff`)

### terminal

Monospace text output, useful for logs or commands.

```json
{ "id": "log", "type": "terminal", "label": "Log", "action": "get_log" }
```

```python
def get_log(self):
    return {"value": "Line 1\nLine 2\nLine 3"}
```

### button

Button executes an action (no automatic visual feedback).

```json
{ "id": "btn", "type": "button", "label": "Reiniciar", "action": "do_restart" }
```

### input

Text field + submit button. Sends the value to the server.

```json
{
  "id": "buscar",
  "type": "input",
  "label": "Buscar",
  "action": "do_search",
  "placeholder": "Escribe...",
  "button_label": "Ir",
  "input_type": "text",
  "input_name": "query"
}
```

```python
def do_search(self, data):
    query = data.get("query", "")
    return {"value": f"Resultados para: {query}"}
```

### progress

Progress bar with polling. Useful for long processes.

```json
{
  "id": "dl",
  "type": "progress",
  "label": "Descarga",
  "action": "get_progress",
  "poll_interval": 800
}
```

The action must return:
```python
{
    "value": {
        "status": "running",        # running | completed | error | idle
        "progress": 7,
        "total": 10,
        "current": "song.mp3",
        "error": ""
    }
}
```

### form

Dynamic form generated from config. Requires `config_action` and `save_action`.

```json
{
  "id": "config",
  "type": "form",
  "label": "Config",
  "config_action": "get_config",
  "save_action": "save_config",
  "fields": [
    { "id": "host", "label": "Host", "type": "text", "default": "localhost" },
    { "id": "port", "label": "Port", "type": "text", "default": "8080" },
    { "id": "ssl", "label": "SSL", "type": "checkbox", "default": false }
  ]
}
```

Field types: `text`, `select`, `checkbox`. For `select` add `"options": [{"label": "Op1", "value": "op1"}]`.

### dropdown

Dropdown menu with actions.

```json
{
  "id": "menu",
  "type": "dropdown",
  "label": "",
  "icon": "⚙",
  "position": "top-right",
  "items": [
    { "label": "Acción 1", "action": "do_thing" },
    { "type": "separator" },
    { "label": "Acción 2", "action": "do_other", "method": "POST", "data": {"key": "val"} }
  ]
}
```

---

## Styles

### In extension.json

```json
{
  "id": "cpu",
  "type": "chart",
  "label": "CPU",
  "styles": {
    "neon": { "label": "Neon" },
    "ocean": { "label": "Ocean" },
    "custom": { "label": "Mi Estilo" }
  }
}
```

### In CSS

```css
/* Extension's style.css */
.widget-style-neon {
  --accent-blue: #ff00ff;
  --accent-cyan: #ff00aa;
  --border-color: #3a0040;
  --bg-widget: rgba(13, 0, 21, 0.85);
}
```

Available variables:

| Variable | Default | Affects |
|----------|---------|---------|
| `--accent-blue` | `#0088ff` | Main color |
| `--accent-cyan` | `#00d4ff` | Secondary color, values, hover borders |
| `--accent-green` | `#00ff88` | Badge ok |
| `--border-color` | `#1a1a3e` | Widget borders |
| `--bg-widget` | `rgba(8,12,30,0.75)` | Widget background |

To extend core styles, use the extension selector:

```css
.ext-mi_extension.widget-style-custom {
  --accent-blue: #ff6600;
  --accent-cyan: #ffaa44;
}
```

---

## JavaScript and CSS

Files in `static/` are automatically injected when the page loads.

```javascript
// static/script.js
(function() {
  const extId = 'mi_extension';

  // Wait for data to be ready
  function wait() {
    if (typeof extensionsData !== 'undefined' && extensionsData[extId]) {
      init();
      return;
    }
    setTimeout(wait, 200);
  }

  function init() {
    // Your logic here
    document.querySelector('.ext-' + extId + ' .widget-body')
      .addEventListener('click', () => {
        apiFetch('/api/extension/' + extId + '/mi_accion');
      });
  }

  wait();
})();
```

---

## Menus and Actions

```json
"menu_items": [
  { "label": "Abrir panel", "action": "open_panel" }
]
```

Menu actions are executed via the hook system in `menu.js`:

```javascript
registerMenuHook('mi_extension', 'open_panel', async function(extId, action, label) {
  // Show panel, open URL, etc.
});
```

---

## Global Frontend Utilities

These functions are available globally in any extension's JS module without importing anything.

### showToast(message)

Shows a transient notification at the bottom of the screen. Disappears after 2.5s.

```javascript
showToast('Hello from extension');
showToast('Note saved');
```

### apiFetch(url, options)

Thin wrapper around `fetch()`. Fetches `/api/token` itself and sends `X-CoreFrame-Token`; sets `Content-Type: application/json` automatically for string bodies; aborts after 90s (configurable via `options.timeout`).

**It never rejects**: HTTP errors resolve as `{error: "..."}` (extra 403 fields like `needs_escalation` are lost — match on the message string).

```javascript
apiFetch('/api/extension/mi_ext/mi_accion').then(function(data) {
  if (data.error) { /* e.g. 'Escalation required', 'Unauthorized' */ return; }
  console.log(data.value);
});

apiFetch('/api/extension/mi_ext/create', {
  method: 'POST',
  body: JSON.stringify({ title: 'Test' })
}).then(function(data) {
  if (data && data.value) { /* success */ }
});
```

### Result Panel (Modal)

The built-in overlay modal. Open it by adding the `open` class to `#result-panel` and `#overlay`.

```javascript
var panelTitle = document.getElementById('result-panel-title');
var panelBody = document.getElementById('result-panel-body');
panelTitle.textContent = 'My Extension';
panelBody.innerHTML = '<p>Any HTML content</p>';
document.getElementById('result-panel').classList.add('open');
document.getElementById('overlay').classList.add('open');
```

To close: `closeResultPanel()` or click outside the panel.

### Spinner Overlay

For long operations, show a centered spinner with a message:

```javascript
showInstallOverlay('Processing...');
// ... later:
hideInstallOverlay();
```

---

## Data Storage

Extensions receive a `data_dir` path in their config where they can store persistent user data (notes, configs, downloads, etc.). This directory is located at:

| Platform | Path |
|----------|------|
| Windows | `~/Documents/CoreFrame/data/<ext_id>/` |
| Linux | `~/.local/share/CoreFrame/data/<ext_id>/` |

```python
class Extension:
    def __init__(self, config):
        self.config = config
        data_dir = config.get('data_dir')           # e.g. ~/Documents/CoreFrame/data/my_extension/
        self.data_file = os.path.join(data_dir, 'data.json')
        os.makedirs(data_dir, exist_ok=True)         # create if you need it
```

The directory is **not created automatically** — your extension must create it when it actually needs to store data.

Frontend code can access the same location via API calls that read/write from `data_dir`.

---

## Libraries (PyPI packages)

Your extension runs isolated but shares one library directory with all extensions. Two ways to get a package (both end up importable with a plain `import`):

**Option A — `requirements.txt` (recommended).** Drop it in the extension folder:

```
trimesh
numpy
scipy
```

On first load CoreFrame installs it in the background (`pip install --prefix <DATA_DIR>/lib ...`). No restart needed — but the first call needing the lib can fail while install is still running, so return a friendly `{"error": ...}` in that case.

**Option B — ship a `lib/` folder** inside the extension. On load it is copied into the shared lib and removed from the extension. Useful for vendored or offline packages.

**Where they live and how imports resolve.** Shared lib paths:

| Platform | Shared lib | `pip --prefix` layout |
|----------|-----------|----------------------|
| Windows | `~/Documents/CoreFrame/lib/` | `lib/` + `lib/Lib/site-packages/` |
| Linux | `~/.local/share/CoreFrame/lib/` | `lib/` + `lib/python3.11/site-packages/` |

The child process `sys.path` already includes, in order: your extension folder, the shared lib, and its `site-packages` subdir. So this just works:

```python
import yt_dlp  # installed via A or B, no sys.path hacks needed
```

> Real case: `pip --prefix` on Windows puts packages under `lib/Lib/site-packages`, not `lib/` directly. If your `import` fails right after install, you are probably hitting a stale process — restart CoreFrame so the child picks up the new `sys.path`.

---

## HTTP API reference

Base URL `http://127.0.0.1:8420`. Auth: `GET /api/token` (no auth) → send `X-CoreFrame-Token` header on everything else under `/api/` (`/api/health`, `/api/debug` exempt; missing/invalid token → `403 Unauthorized`).

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/extensions` | All extensions: config, widgets, `js/css_modules`, permission info, consent state |
| GET/POST | `/api/extension/<id>/<action>` | Call a method. GET calls `def action(self)`; POST passes the JSON body as `def action(self, data)`. Returns `{"value": ...}` or `{"error": ...}` |
| GET | `/api/extensions/health` | Load status, load time, errors per extension |
| GET/POST | `/api/widget-state` | Scene + widget layout JSON |
| GET/POST | `/api/scenes`, PUT/DELETE `/api/scenes/<id>` | Scene CRUD |
| GET | `/api/extensions/<id>/permissions` | Granted level + escalations |
| POST | `/api/extensions/<id>/permissions/grant` | Body `{level, escalations[]}` |
| POST | `/api/extensions/<id>/permissions/revoke` | Revoke all (widget becomes paperweight, stays in picker) |
| POST | `/api/extensions/<id>/permissions/escalation` | Body `{method, grant, once}` |
| GET | `/api/extensions/pending_consent` | Extensions waiting for a user decision (startup polling) |
| POST | `/api/extensions/<id>/load`, `/unload` | Load/unload a deferred extension on demand |
| POST | `/api/install_extension` | Install a `.zip` |
| DELETE | `/api/extensions/<id>` | Uninstall |
| GET | `/ext-static/<id>/<file>` | Frontend files from the extension's `static/` folder |

```bash
TOKEN=$(curl -s http://127.0.0.1:8420/api/token | jq -r .token)
curl -H "X-CoreFrame-Token: $TOKEN" http://127.0.0.1:8420/api/extensions
curl -X POST -H "X-CoreFrame-Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"Hi"}' http://127.0.0.1:8420/api/extension/notes/create
```

---

## Real-time

For widgets that update continuously without client polling:

```json
{
  "realtime": true,
  "refresh_interval": 2000,
  "widgets": [...]
}
```

In `main.py`:
```python
def get_cpu(self):
    return {"value": psutil.cpu_percent()}
```

The server polls at the same `refresh_interval` and emits via WebSocket to all connected clients.

---

## Publishing

1. From the interface: **Package** button → select extension → download `.zip`
2. Or manually: compress the extension folder
3. Upload to GitHub or any host
4. Add to the marketplace registry (PR in the extensions-coreframe repo)

---

## Multi-language

See [`BRIDGE.md`](BRIDGE.md) for the complete extension protocol in Node.js, Go, Rust, etc.
