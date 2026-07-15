# CoreFrame

**Open-source modular dashboard.** Extensions in Python, Node.js and more. Grid widgets, scenes, customizable styles. A control center for systems, networks, development and daily tools.

<p align="center">
  <img src="https://img.shields.io/badge/version-1.0.0-blue" alt="Version">
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python">
  <img src="https://img.shields.io/badge/HTML-5+-E34F26?logo=html5" alt="Html">
  <img src="https://img.shields.io/badge/JavaScript-F7DF1E?logo=javascript&logoColor=black" alt="Javascript">
  <img src="https://img.shields.io/badge/platform-windows%20%7C%20linux%20%7C%20macos-lightgrey" alt="Platform">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="License">
</p>

---

## Table of Contents

- [Installation](#installation)
  - [Release version](#release-version)
  - [Running from source](#running-from-source)
  - [Release files](#release-files)
  - [Updating](#updating)
  - [Dependencies](#dependencies)
  - [Building from source](#building-from-source)
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
| `static/` | Frontend (HTML, CSS, JS) |
| `extensions/` | Built-in extensions (network_monitor, system_monitor, vault_manager, ...) |
| `data/` | Per-extension user data (notes, configs, downloads) — inside `~/Documents/CoreFrame/data/` |
| `docs/` | Guides (EXTENSIONS.md, BRIDGE.md) |
| `scaffolds/template-extension/` | Extension scaffold template |
| `CoreFrame.spec` | PyInstaller config |
| `requirements.txt` | Python dependencies |

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

- **Python**: loaded via `importlib`. Just need an `extension.json` and `main.py` with an `Extension` class.
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
└── static/          (optional)
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

    def get_greeting(self):
        return {"value": "Hello from my extension!"}
```

**Node.js — minimum:**

```json
{
  "id": "my_api",
  "language": "node",
  "main": "server.js",
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
