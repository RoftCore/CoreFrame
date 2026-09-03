# Extension Guide — CoreFrame

## Table of Contents

1. [Extension Structure](#estructura)
2. [extension.json — Complete Reference](#extensionjson)
3. [main.py — Python API](#mainpy)
4. [Widgets — Types and Configuration](#widgets)
5. [Custom Styles](#estilos)
6. [JavaScript and CSS](#javascript-y-css)
7. [Menus and Actions](#menús-y-acciones)
8. [Real-time (WebSocket)](#tiempo-real)
9. [Publishing an Extension](#publicar)
10. [Multi-language (Bridge)](#multi-lenguaje)

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
| `permissions` | object | — | ❌ | Permission declaration (see [Permissions](#permisos)) |

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
- `escalation.admin.methods` lists actions that require **extra** admin approval even if base level is `system`. When the frontend calls one of those methods, CoreFrame shows a second modal: **Once** (single use, consumed after one successful call) vs **Always** (permanent). If denied, the widget must stay in waiting state for **10s** (cancellable) and then show a CoreFrame timeout message, not an error.

**Isolation:** All Python extensions go through `coreframe/extensions/ext_runner.py` (embebido como string en `run_coreframe.pyw`, sin archivos en `MEIPASS`). `builtins.open` is restricted to `allowed_dirs` + `exe dir` + `_MEIPASS` + `TEMP` + `ext_path`. `socket` and `subprocess` are blocked below the required level. `DATA_DIR` and `SHARED_LIB_DIR` are injected via `config['_coreframe']`.

**Admin elevation:** Methods in `escalation.admin` that need to write the system must not do `winreg`/`sc` directly. Use the helper:

```python
# inside Extension.toggle / service_control etc.
from coreframe.extensions.bridge import _call_elevated  # or use helper via _elevated_via_helper
# For registry/service, call helper which runs coreframe_helper.exe with UAC:
ok, res = _elevated_via_helper("service_control", {"service": svc, "action": "disable"})
# or for registry:
ok, res = _elevated_via_helper("registry_write", {"hive":"HKEY_LOCAL_MACHINE","key":subkey,"name":vname, ...})
```

If you do direct `winreg`/`sc` without helper, it will fail with `Access is denied` unless CoreFrame itself is run as admin. With helper, CoreFrame shows **Windows UAC** (blue prompt) once, then AVG whitelists `coreframe_helper.exe`.

**Frontend:** Always use global `apiFetch` (handles `X-CoreFrame-Token`). Handle `403` with `needs_escalation` / `needs_consent`:

```javascript
try {
  const r = await apiFetch('/api/extension/my_ext/toggle', {method:'POST', body:JSON.stringify({id})});
} catch(e) {
  if(e.message.includes('Escalation')) {
    // Show single waiting UI for 10s, cancellable
    showPermWaiting(e.message); // 10s, no error on timeout → CoreFrame message
    // Poll GET /api/extensions/my_ext/permissions until granted, then retry once
  }
}
```

Widgets must never show `Error: Escalation required` as a red error. Instead show a CoreFrame waiting message for 10s (`Esperando permiso... 10s` + Cancel) and on timeout show `CoreFrame: tiempo de espera agotado` (not `Error`). The `Once` grant is consumed after one successful call, `Always` persists in `permissions_consent.json`.

### widgets[]

Each widget is an object:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | ✅ | Unique identifier within the extension |
| `type` | string | ✅ | Widget type (see [types](#widgets)) |
| `label` | string | ✅ | Visible label |
| `action` | string | ❌* | Python method to call for data retrieval |
| `click_action` | string | ❌ | Action when clicking the widget |
| `styles` | object | ❌ | Swappable styles (see [styles](#estilos)) |

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

Thin wrapper around `fetch()` with automatic JSON parsing and error handling. Returns a Promise.

```javascript
apiFetch('/api/extension/mi_ext/mi_accion').then(function(data) {
  console.log(data.value);
});

apiFetch('/api/extension/mi_ext/create', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
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
