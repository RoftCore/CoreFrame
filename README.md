# CoreFrame

Personal control center with HUD panel, system monitoring, universal VPN control, note manager, and network analysis.

## Stack

- **Backend:** Python 3 (Flask + Flask-SocketIO)
- **Frontend:** HTML, CSS, vanilla JavaScript (no frameworks)
- **WebSocket:** Real-time for CPU, RAM, GPU, disk
- **Extensions:** Modular system with dynamic loading via importlib

## Screenshot

HUD-style panel with real-time widgets, sidebar menu, sliding result panel, and persistent WebSocket connection.

## Requirements

```
pip install -r requirements.txt
```

## Usage

Run `run.vbs` (self-elevates with UAC for admin privileges).

Manual alternative:
```
python app.py
```

Open in browser: http://127.0.0.1:5000

## Features

### Network Monitor
- **Public IP** — widget with location and proxy/VPN detection
- **Universal VPN** — connect/disconnect Proton, Nord, Mullvad, Windscribe and more
  - Modular architecture: each VPN is a separate provider in `providers/`
  - Automatic detection of active provider by services and adapters
  - Killswitch via CLI (Proton) with availability detection
  - Smart GUI restart: only relaunches client if it was already open
- **DNS leak test** — checks whether DNS queries travel through the VPN tunnel
- **Active connections** — table with proto, IPs, state and process (PID)
- **Port scanning** — common ports open on localhost
- **Force DNS** — sets Cloudflare 1.1.1.1 on the VPN adapter

### System Monitor
- CPU, RAM, GPU, disk in real time
- Histograms with the last 40 values
- Broadcast via WebSocket every 1s

### Vault Manager
- Note manager with JSON persistence
- Creation, listing, export

## Security

- Bind to `127.0.0.1` (not accessible from LAN/Internet)
- CORS restricted to `http://127.0.0.1:5000`
- SHA-256 token generated at startup, required on all APIs (`X-CoreFrame-Token`)

## Structure

```
coreframe/
├── app.py                  # Flask + SocketIO server
├── controller.ps1          # System tray icon + stop handling
├── run.vbs                 # Launcher with UAC self-elevation
├── requirements.txt
├── extensions.json
├── static/
│   ├── index.html          # SPA
│   ├── css/                # palette, layout, components, effects
│   └── js/                 # core.js, menu.js, widgets.js, utils.js
└── extensions/
    ├── network_monitor/
    │   ├── main.py         # Universal logic (IP, VPN, DNS, ports)
    │   ├── extension.json
    │   └── providers/      # VPN modules
    │       ├── base.py     # BaseProvider class
    │       ├── proton.py
    │       ├── windscribe.py
    │       ├── nord.py
    │       └── ... (13 providers)
    ├── system_monitor/
    │   ├── main.py         # CPU, RAM, GPU, disk
    │   └── extension.json
    └── vault_manager/
        ├── main.py         # Notes with persistence
        └── extension.json
```

## Creating an extension

1. Create folder in `extensions/my_extension/`
2. Create `extension.json` with widgets, menus and actions
3. Create `main.py` with `Extension` class and methods for each action
4. The core loads it automatically at startup

## Adding a VPN provider

1. Create `extensions/network_monitor/providers/my_vpn.py`
2. Inherit from `BaseProvider` and define attributes (keywords, services, processes, CLI)
3. Don't modify `main.py`
