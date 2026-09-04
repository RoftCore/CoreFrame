# CoreFrame

**Open-source modular dashboard.** Extensions in Python, Node.js and more. Grid widgets, scenes, customizable styles. A control center for systems, networks, development and daily tools.

<p align="center">
  <img src="https://img.shields.io/badge/version-1.1.0-blue" alt="Version">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/HTML-5+-E34F26?logo=html5" alt="Html">
  <img src="https://img.shields.io/badge/JavaScript-F7DF1E?logo=javascript&logoColor=black" alt="Javascript">
  <img src="https://img.shields.io/badge/platform-windows%20%7C%20linux%20%7C%20macos-lightgrey" alt="Platform">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

<table>
  <tr>
    <td style="border: 2px solid white; padding: 0;">
      <img src="https://github.com/user-attachments/assets/46f292dd-f620-4290-9d20-4dc199c2f86f" width="400">
    </td>
    <td style="border: 2px solid white; padding: 0;">
      <img src="https://github.com/user-attachments/assets/1270c893-23cd-461e-a295-f682203b476d" width="400">
    </td>
  </tr>
</table>
---

## Table of Contents

- [Installation](#installation)
  - [Release version](#release-version)
  - [Running from source](#running-from-source)
  - [Release files](#release-files)
  - [Updating](#updating)
  - [Dependencies](#dependencies)
  - [Building from source](#building-from-source)
- [How it works](#how-it-works)
- [Permissions](#permissions)
- [Using the API](#using-the-api)
- [Installing libraries](#installing-libraries)
- [Usage & options](#usage--options)
  - [Extensions](#extensions)
  - [Options](#options)
  - [Creating an extension](#creating-an-extension)
- [License](#license)

---

## Installation

### Release version

Download the latest [CoreFrame release](https://github.com/RoftCore/CoreFrame/releases) for your system.

**Windows:** grab `CoreFrame-Windows.exe` — portable, no installation needed. Just double-click and run.

**Linux:** grab `CoreFrame-Linux` — make it executable (`chmod +x CoreFrame-Linux`) and run.

**macOS:** grab `CoreFrame-macOS` — if macOS blocks it, go to System Settings → Privacy & Security → allow anyway.

> No dependencies required. No Python, no pip, no terminal. Just download and run.
- Marketplace: https://github.com/RoftCore/extensions-coreframe/releases

### Running from source

If you prefer to run from source (e.g. for development or if there's no binary for your architecture):

```bash
git clone https://github.com/RoftCore/CoreFrame
cd CoreFrame
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux / macOS:
source venv/bin/activate
pip install -r requirements.txt
python app.py
# Open http://127.0.0.1:8420
```

### Release files

| File | Description |
|------|------------|
| `app.py` | Flask + SocketIO server |
| `run_coreframe.pyw` | Native window launcher (pywebview) |
| `coreframe/` | Backend package (routes, extensions, permissions, bridge) |
| `coreframe_helper.py` / `coreframe_helper.exe` | UAC elevation helper (admin operations) |
| `static/` | Frontend (HTML, CSS, JS) |
| `docs/` | Guides (EXTENSIONS.md, BRIDGE.md) |
| `scaffolds/template-extension/` | Extension scaffold template |
| `CoreFrame.spec` | PyInstaller config |
| `requirements.txt` | Python dependencies |

### Where your data lives

Code and user data are strictly separated:

| What | Windows | Linux |
|------|---------|-------|
| Your data | `~/Documents/CoreFrame/` | `~/.local/share/CoreFrame/` |
| Extensions | `.../CoreFrame/extensions/<id>/` | same |
| Per-extension data | `.../CoreFrame/data/<id>/` | same |
| Shared libs | `.../CoreFrame/lib/` | same |
| Widget layout | `.../CoreFrame/widget_state.json` | same |
| Consents | `.../CoreFrame/permissions_consent.json`, `permissions_denied.json` | same |

### Updating

**Binary:** just download the new version from [Releases](https://github.com/RoftCore/CoreFrame/releases) and replace your old file. Your data (widgets, scenes, extensions, extension data) stays in `~/Documents/CoreFrame/`.

**Source:**

```bash
git pull
# If dependencies changed:
pip install -r requirements.txt --upgrade
```

### Dependencies

- **Python 3.10+**
- Flask, Flask-SocketIO, pywebview (see `requirements.txt`)
- Build only: PyInstaller

### Building from source

```bash
pip install pyinstaller
pyinstaller CoreFrame.spec
# ./dist/CoreFrame.exe  (Windows)
# ./dist/CoreFrame      (Linux / macOS)
```

---

## How it works

```
┌─────────────┐  JSON-RPC stdin/stdout  ┌──────────────────┐
│  CoreFrame  │ ◄─────────────────────► │ ext #1 (process) │
│  (Flask +   │                         ├──────────────────┤
│   web UI)   │ ◄─────────────────────► │ ext #2 (process) │
└─────────────┘                         └──────────────────┘
       │ HTTP API (:8420)          each extension = own OS process
       ▼
  dashboard, scenes,
  consent modals, UAC
```

- **Server:** Flask + Flask-SocketIO on `http://127.0.0.1:8420`. Serves the dashboard and a REST + WebSocket API.
- **Isolation:** every Python extension runs in its **own OS process** (`CoreFrame.exe --ext-runner <config>`), talking JSON-RPC over stdin/stdout. A crashing or malicious extension cannot take down CoreFrame or read other extensions' memory.
- **Enforcement:** the child process gets OS-level restrictions based on its permission level (file paths, network, subprocess). See [Permissions](#permissions).
- **Frontend:** the dashboard calls the API; widgets poll or receive WebSocket pushes.

Full protocol: [`docs/BRIDGE.md`](docs/BRIDGE.md). Full extension guide: [`docs/EXTENSIONS.md`](docs/EXTENSIONS.md).

---

## Permissions

Every extension declares a level in `extension.json`. CoreFrame enforces it in the child process — code running above its level gets `PermissionError`.

| Level | Name | Can do | Consent modal? |
|-------|------|--------|----------------|
| 0 | `basic` | UI only. No files, no network | No |
| 1 | `storage` | Read/write only its own `data/<id>/` folder | No |
| 2 | `user_files` | Only files **you** pick (whitelist) | No |
| 3 | `network` | Outbound HTTP/HTTPS + read its own data | **Yes** |
| 4 | `system` | System info, processes, registry (read) **+ run subprocesses** (e.g. `ffmpeg`) | **Yes** |
| 5 | `admin` | Full control: registry write, services, any file | **Yes** |

```json
{
  "permissions": {
    "level": "system",
    "requires": ["subprocess"],
    "mediated": false,
    "escalation": {
      "admin": {
        "methods": ["registry_write", "service_control"],
        "description": "Disable startup entries"
      }
    }
  }
}
```

- Levels 0–2 load silently. Levels 3–5 show a consent modal on first run.
- **`escalation`**: individual methods that need an extra approval even inside the base level. The user picks **Once** (single use, then consumed) or **Always** (permanent). Denying keeps the widget in a 10-second waiting state, not an error.
- **Admin operations** (`registry_write`, `service_control`, `delete_file`, …) never run CoreFrame as admin. They go through `coreframe_helper.exe`, which triggers a single Windows UAC prompt.

Details: [`docs/EXTENSIONS.md`](docs/EXTENSIONS.md) (permissions section).

---

## Using the API

Base URL: `http://127.0.0.1:8420`

**Auth:** a random token is generated on each launch. Get it without auth, then send it on every other call:

```bash
TOKEN=$(curl -s http://127.0.0.1:8420/api/token | jq -r .token)
curl -H "X-CoreFrame-Token: $TOKEN" http://127.0.0.1:8420/api/extensions
```

(`GET /api/token`, `/api/health`, `/api/debug` need no token. Everything else under `/api/` returns `403 Unauthorized` without the `X-CoreFrame-Token` header.)

**Main endpoints:**

| Method | Endpoint | What it does |
|--------|----------|--------------|
| GET | `/api/extensions` | List extensions (config, widgets, permission info, consent state) |
| GET/POST | `/api/extension/<id>/<action>` | Call an extension method. GET = no args, POST = JSON body as `data` |
| GET | `/api/extensions/health` | Load status per extension |
| GET | `/api/widget-state` / POST | Get/save scene + widget layout |
| GET/POST | `/api/scenes`, `PUT/DELETE /api/scenes/<id>` | Manage scenes |
| GET | `/api/extensions/<id>/permissions` | Granted level + escalations |
| POST | `/api/extensions/<id>/permissions/grant` | Grant `{level, escalations[]}` |
| POST | `/api/extensions/<id>/permissions/revoke` | Revoke all |
| POST | `/api/extensions/<id>/permissions/escalation` | Grant/deny one method `{method, grant, once}` |
| GET | `/api/extensions/pending_consent` | Extensions waiting for a decision |
| POST | `/api/install_extension` | Install a `.zip` |
| DELETE | `/api/extensions/<id>` | Uninstall |
| GET | `/ext-static/<id>/<file>` | Extension frontend files (`static/`) |

**Calling an extension method:**

```bash
# GET — calls def get_status(self)
curl -H "X-CoreFrame-Token: $TOKEN" \
  http://127.0.0.1:8420/api/extension/notes/get_notes

# POST — calls def create(self, data) with the JSON body
curl -X POST -H "X-CoreFrame-Token: $TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"Hi","body":"..."}' \
  http://127.0.0.1:8420/api/extension/notes/create
```

Extension methods must return `{"value": ...}` or `{"error": ...}`.
Data-fetch calls time out after **0.8s** (long operations: 30s); after 3 timeouts the widget is marked `degraded` instead of blocking CoreFrame.

**From extension JavaScript**, always use the global helper (it handles token + JSON for you):

```javascript
// GET
apiFetch('/api/extension/my_ext/get_status').then(function(data) {
  console.log(data.value);
});
// POST
apiFetch('/api/extension/my_ext/create', {
  method: 'POST',
  body: JSON.stringify({ title: 'Test' })
});
```

> Note: `apiFetch` resolves to `{error: ...}` on HTTP errors (it does not throw), and strips extra fields — check `data.error` / the message string.

---

## Installing libraries

Extensions often need PyPI packages (`trimesh`, `yt_dlp`, `psutil`…). Two ways, both land in the shared `.../CoreFrame/lib/` visible to every extension process:

**Option A — `requirements.txt` (recommended).** Put it in the extension folder:

```
trimesh
numpy
scipy
```

CoreFrame installs it in the background on first load (`pip install --prefix <DATA_DIR>/lib ...`). No restart needed — but the first call needing the lib may fail until install finishes, so handle that gracefully.

**Option B — ship a `lib/` folder** inside the extension. On load it is copied into the shared lib and removed from the extension. Useful for vendored or offline packages.

**Using them:** just `import` normally. The child process `sys.path` already includes the extension folder, the shared lib, and its `Lib/site-packages` (Windows) / `lib/python3.11/site-packages` (Linux):

```python
import yt_dlp  # works if installed via A or B
```

> Sandboxing note: libraries that **subclass `subprocess.Popen`** (like `yt_dlp`) import fine at levels < 4 — CoreFrame replaces `Popen` with a raisable *class*, not a function. Actually *spawning* processes still requires level ≥ 4 and raises `PermissionError` otherwise.

---

## Usage & options

### Dev mode

```bash
python app.py
# http://127.0.0.1:8420
```

### Desktop mode

```bash
python run_coreframe.pyw
# Native window, no browser needed
```

### Extensions

Extensions are loaded automatically from `~/Documents/CoreFrame/extensions/`. They can be:

- **Python**: an `extension.json` plus `main.py` with an `Extension` class. Runs isolated in its own subprocess — no `importlib` in the main process.
- **Multi-language** (Node.js, Go, etc.): use the JSON-RPC bridge over stdin/stdout. The `extension.json` must set `"language"` and `"main"`.

Each extension exposes widgets that appear in the grid. Widgets update:
- **Polling**: the widget calls the REST API periodically
- **Realtime**: if `extension.json` has `"realtime": true`, a daemon thread pushes data over WebSocket

Extensions that fail to load don't block the system. They appear in the Extensions panel with a ⚠ icon and can be deleted.

### Options

| Context | Action |
|---------|--------|
| Scene bar | Click → switch scene. Drag & drop → reorder. Right-click → icon, delete |
| Widget context menu | Hide, Move, Resize, Change Style |
| Settings (⚙️) | Scene Settings (label, icon, grid size, delete), Extensions (list, delete), Marketplace |
| Resize | Drag bottom-right corner of widget |
| Move | Context menu → move mode → click destination |
| F11 | Toggle fullscreen |

### Creating an extension

Full guide at [`docs/EXTENSIONS.md`](docs/EXTENSIONS.md).

**Python — minimum:**

```
extensions/my_extension/
├── extension.json
├── main.py
├── requirements.txt   (optional — auto-installed to shared lib)
├── lib/               (optional — vendored packages, synced to shared lib)
└── static/            (optional — served at /ext-static/my_extension/...)
    ├── script.js
    └── style.css
```

**extension.json:**
```json
{
  "id": "my_extension",
  "name": "My Extension",
  "icon": "star",
  "version": "1.0",
  "author": "Your name",
  "category": "general",
  "permissions": { "level": "basic" },
  "widgets": [
    { "id": "greeting", "type": "text", "label": "Greeting", "action": "get_greeting" }
  ]
}
```

**main.py:**
```python
class Extension:
    def __init__(self, config):
        self.config = config
        # config['data_dir'] -> your writable folder (create on demand)

    def get_greeting(self):
        return {"value": "Hello from my extension!"}
```

**Node.js — minimum:**

```json
{
  "id": "my_api",
  "language": "node",
  "main": "server.js",
  "permissions": { "level": "basic" },
  "widgets": [
    { "id": "status", "type": "text", "label": "Status", "action": "get_status" }
  ]
}
```

```javascript
// server.js
const rl = require('readline').createInterface({ input: process.stdin, stdout: process.stdout, terminal: false });
rl.on('line', (line) => {
  const { method, id } = JSON.parse(line);
  if (method === 'get_status') process.stdout.write(JSON.stringify({ result: 'OK', id }) + '\n');
});
```

Extensions are packaged as `.zip` from the UI (Package button, visible in dev mode) and distributed via GitHub or the community marketplace.

## License

MIT
