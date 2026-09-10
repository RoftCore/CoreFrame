# COREFRAME — GUIDE FOR ASSISTANTS

> **IMPORTANT:** This file must be updated whenever the architecture changes, extensions are added/removed, core mechanisms are modified, or new bugs/pitfalls are discovered. It is the source of truth for any AI working on the project.

## Branching Strategy (CRITICAL)

- **`main` branch**: ONLY tested, released versions (tagged as `vX.Y.Z`). No direct pushes.
- **`development` branch**: All feature work, bug fixes, experiments. PRs target `development`.
- **Release flow**: `development` → tested → merge to `main` → tag `vX.Y.Z` → GitHub Actions builds release.
- **CI/CD**: GitHub Actions builds on push to `main` and tags `v*`. Development builds run on `development` branch only.

## Identity

Personal control center with widget panel, system monitoring, VPN control, process manager and network analysis. Vanilla SPA (no frameworks). Architecture based on self-contained extensions: the core is generic, each extension lives in its own directory with backend, frontend and CSS.

## Stack

- **Backend:** Python 3.14+ (Flask + Flask-SocketIO)
- **Frontend:** HTML, CSS, vanilla JS (no frameworks)
- **WebSocket:** real-time per extension. Each extension with `"realtime": true` runs its own daemon thread (`_poll_extension`) that emits `realtime_update` via SocketIO respecting its `refresh_interval`. Fixed cadence with `next_tick` to prevent drift. No HTTP polling.
- **Extensions:** dynamic loading via `importlib` from `extensions/`
- **Widget DOM optimization:** internal hash (`_widgetHash`) prevents DOM updates if the value hasn't changed
- **Widget click_action:** badge/text/list widgets can open menu panels on click

## Structure

```
CoreFrame/
├── app.py                     # Flask + SocketIO server (generic, no extension-specific code)
├── requirements.txt
├── extensions.json            # Auto-generated registry (DO NOT edit manually)
├── static/
│   ├── index.html             # SPA
│   ├── css/
│   │   ├── palette.css        # Color and theme variables
│   │   ├── components.css     # Only generic CSS: base widget/sub-widget, extension-card, generic modal
│   │   ├── layout.css         # 12-column grid, sidebar, header
│   │   ├── utilities.css      # Helper classes
│   │   └── reset.css
│   └── js/
│       ├── core.js            # Bootstrap, extension loading, generic WebSocket, refresh
│       ├── menu.js            # Dynamic sidebar + registerMenuHook
│       ├── widgets.js         # createExtensionCard, createSubWidget, generic render/update
│       └── utils.js           # apiFetch, formatBytes, getProcessIcon, escapeHtml, etc.
├── extensions/
│   ├── network_monitor/       # IP, VPN, DNS, ports, connections (incoming/outgoing tabs, sorting by process, 200-pagination, "See more")
│   ├── msd_deck/              # Mars Gaming MSD-ONE driver (VID 0x0B00 PID 0x1000, AKP153 proto v1): 18 LCD slots, side-strip widgets, profiles, macros, hotkeys
│   ├── system_monitor/        # CPU, RAM, GPU, disk (WebSocket realtime)
│   ├── vault_manager/         # Notes with persistence
│   └── process_manager/       # Process management (with its own static/script.js + style.css)
└── scaffolds/
    └── template-extension/    # Template to copy when creating extensions
```

## Architecture rules (IMPORTANT)

1. **The core contains NO code or CSS of any specific extension.** Zero references to extension names, specific classes, or if/else per extension. If an extension is deleted, no trace should remain in the core.

2. **Each extension is self-contained.** Its backend (`main.py`), frontend (`static/script.js`) and styles (`static/style.css`) live in its directory. They are declared via `js_modules` and `css_modules` in `extension.json`.

3. **The core provides generic mechanisms:** 12-column grid, extension card (`createExtensionCard`), sub-widgets (text, badge, list, chart, terminal, button), polling via `startWidgetIntervals`, generic WebSocket (no hardcoding), hook system for menus (`registerMenuHook`).

## Menu system (hooks)

Extensions register handlers for menu actions via `registerMenuHook(extId, action, async function)`:

```js
registerMenuHook('network_monitor', 'vpn_control', async (panelBody) => {
  panelBody.classList.add('vpn-panel-body');
  // fetch data + render
});
```

The core (`menu.js:executeMenuAction`) checks if a registered hook exists. If so, it executes it. Otherwise, it makes a generic fetch and displays JSON.

## WebSocket (real-time — one thread per extension)

The backend runs `realtime_broadcast()` in a daemon thread. It scans extensions and launches one daemon thread per extension with `"realtime": true`, `refresh_interval > 0` and widgets. Each thread loops independently:

```python
def _poll_extension(ext_id, ext_data, interval_ms):
    interval = interval_ms / 1000.0
    next_tick = time.monotonic()
    while True:
        tick = time.monotonic()
        values = {wDef['id']: inst.action() for wDef in widgets}
        if values:
            socketio.emit('realtime_update', {'ext': ext_id, 'values': values})
        next_tick = max(next_tick + interval, tick + interval)
        remaining = next_tick - time.monotonic()
        if remaining > 0: time.sleep(remaining)
```

Benefits:
- Each extension updates at its own pace without blocking others.
- `next_tick` maintains fixed cadence even if a single iteration takes longer than the interval.
- No accumulated drift.

The frontend (`core.js`) iterates `data.values` and looks for `[data-widget-id="{id}"][data-ext-id="{ext}"]` elements.

Extensions with `"realtime": true` in `extension.json` make the core skip HTTP polling (`startWidgetIntervals` skips those with `realtime: true`).

SocketIO is configured with `transports: ['websocket']` on the client to avoid HTTP polling and eliminate accumulated TIME_WAIT.

## Extension System

> Runtime loads extensions ONLY from DATA_DIR (`Documents/CoreFrame/extensions/`, see `coreframe/config.py`), never from the repo `extensions/` dir (dev source). Deploy = copy dir + restart exe (no rebuild unless core/requirements/spec/`static/` changed). Beware `Copy-Item -Recurse` nesting when the target exists.

### Minimum structure

```
extensions/my_extension/
├── extension.json        # Metadata, widgets, js_modules, css_modules
├── main.py               # Extension class with methods per action
└── static/
    ├── script.js         # (optional) Extension-specific frontend logic
    └── style.css         # (optional) Extension-specific styles, prefixed .ext-{id}
```

### extension.json

```json
{
  "id": "my_extension",
  "name": "My Extension",
  "icon": "icon-name",
  "version": "1.0",
  "author": "",
  "category": "general",
  "realtime": false,
  "refresh_interval": 5000,
  "js_modules": ["script.js"],
  "css_modules": ["style.css"],
  "menu_items": [
    { "action": "do_something", "label": "Do something" }
  ],
  "widgets": [
    { "id": "my_widget", "type": "text", "label": "My Widget", "action": "my_action" }
  ]
}
```

- `realtime` (bool): if `true`, the core skips HTTP polling for this extension (handled by WebSocket).
- `js_modules`: array. The core loads each module via dynamic `<script>` from `/ext-static/{id}/{mod}`.
- `css_modules`: array. Each extension MUST use its own CSS for specific styles. Do not inject into core files.
- `menu_items`: sidebar entries. `action` maps to an `Extension` class method or a hook registered via `registerMenuHook`.
- `widgets`: grid widgets. The action is called as `/api/extension/{id}/{action}`.

### main.py

```python
class Extension:
    def __init__(self, config):
        self.config = config

    def my_action(self):
        return {"value": 42}
```

Methods can receive `GET` (no args) or `POST` (with `data` from JSON body). They always return a serializable dict.

### CSS Naming

Extensions use prefixed classes `ext-{id}` to avoid collisions:
- `ext-system_monitor` → `.ext-system_monitor .widget-body`
- `ext-network_monitor` → `.vpn-panel-body`, `.net-inspector-body`
- `ext-process_manager` → `.ext-pm-modal-body`, `.ext-pm-modal-table`

### Widget click_action

Widgets of type `badge`, `text` and `list` can include `"click_action"` in `extension.json` to open the corresponding menu panel on click. The core (`widgets.js:createSubWidget`) assigns the listener automatically when it detects the field.

```json
{ "id": "vpn_status", "type": "badge", "label": "VPN", "action": "vpn_status", "click_action": "vpn_control" }
```

The core exposes `window.extensionsData` globally (`core.js`) so the click handler can resolve the panel.

### Host immunity contract (extensions MUST obey)

CoreFrame is a host: one heavy/failing extension must never degrade the core or other extensions. The core enforces this for its own updates (drag flag + queued realtime values, see pitfall #19), but extension-owned scripts (`js_modules` with their own `setInterval` renders) run on the same main thread, so they must cooperate:

- **Pause heavy renders while dragging:** check `window.__coreframeDragging === true` at the top of any interval/refresh callback that rewrites large DOM (tables, lists, canvases) and return early. Missed ticks are harmless — the next tick after drop catches up.
- **Flush cue:** listen for `window.addEventListener('coreframe-dragend', refreshFn)` to repaint immediately after a gesture instead of waiting for the next tick.
- **Never throw across the core:** wrap extension render callbacks in try/catch. Core loops (`renderWidgets`, `refreshAllWidgets`, realtime flush) already isolate per-extension errors, but an uncaught exception inside an extension's own timer kills that extension's future ticks silently.
- **Keep per-tick DOM writes proportional to visible change:** reuse the `_widgetHash` pattern (skip DOM writes when the value hash is unchanged) instead of rebuilding `innerHTML` every tick.

### Widget types (generic core sub-widgets)

| type | Description | Expected Data |
|------|-------------|---------------|
| text | Simple value (e.g. IP) | string or number |
| badge | Status with 2 colors (ok/warn) | `{ status, text }` |
| list | Item list | `[{ label, value }]` |
| chart | Sparkline with history | number |
| terminal | Raw output with monospace font | string |
| button| Action button | — |

Updated data arrives via `updateWidgetValue(el, response)` which parses `response.value` based on the element's `data-type`.

### Extension JS load cycle

1. `DOMContentLoaded` → `apiFetch('/api/extensions')` → `extensionsData = data`
2. `buildSidebar(data)` → renders menu + hooks
3. `renderWidgets(data)` → renders cards with sub-widgets (uses `widgets.js`)
4. `loadExtensionAssets(data)` → dynamically loads `js_modules` and `css_modules`
5. The extension script runs and can:
   - Register hooks: `registerMenuHook(extId, action, fn)`
   - Initialize state: variables, intervals, event listeners
   - Use global `extensionsData` (already populated) or the `waitForInit` pattern

### Auto-start pattern for extension JS

```js
(function waitForInit() {
  if (typeof extensionsData !== 'undefined' && Object.keys(extensionsData).length) {
    initMyExtension();
    setInterval(refreshMyExtension, 3000);
    return;
  }
  setTimeout(waitForInit, 200);
})();
```

### MSD Deck specifics (Mars Gaming MSD-ONE hardware driver)

- **Device:** VID `0x0B00` PID `0x1000`, HID usage page 65440 usage 1 (Ajazz AKP153 family, protocol v1, 512-byte packets). Hardcoded serial `355499441494`. Close the official Mars app first (exclusive open).
- **Protocol** (`msd_protocol.py`, pure/testable, ported from mirajazz + opendeck-akp153 + Uriziel01 notes): commands are `00 CRT 00 00 + ASCII` (`DIS`/`LIG` init, `LIG..<pct>` brightness, `BAT..<len><key+1>` + JPEG chunks + `STP` commit, `CLE...<key+1|0xFF>` clear, `HAN` sleep, `CONNECT` keep-alive). Key index on wire is device+1. Input reports start with `ACK`, key at byte 9 (1-based, 0 = idle); v1 emits press-only (Down+Up together).
- **Key maps:** 18 positions (3 rows × 6 cols, OpenDeck parity). `OPENDECK_TO_DEVICE` / `DEVICE_TO_OPENDECK` tables in `msd_protocol.py`. Positions 5/11/17 (1-based 6/12/18) are the LATERAL strip: 3 separate LCD cells filling the side screen (NOT missing keys).
- **Side-strip widgets** (`msd_widgets.py`): clock / weather (Open-Meteo, no key, geo in profiles file) / system (psutil CPU+RAM). Backend thread repaints every 10s, pushes only on byte-change (no LCD flicker); immediate repaint on profile switch AND on connect. Panel cells get a Contenido picker (Botón/Reloj/Tiempo/Sistema); city search via Open-Meteo geocoding (`geo_search`, Spanish labels), no coordinates typing. HTTP goes through `requests`+certifi (stdlib urllib has no CA bundle in the frozen exe); UI thumbs never block on network (`fetch=False` + background warm on assign).
- **Empty cells stay dark:** `_is_slot_empty` (no label/icon/builtin/widget) → `CLE` single-key clear instead of pushing a dark image; `_paint_slot` centralizes push-or-clear (used by set_key/set_key_image/set_key_builtin/clear_icon/swap/set_widget-off). `get_config` exposes `widget_state` {tick, pushed, error} diagnostics.
- **Widget backgrounds:** transparent by default (RGBA, checkerboard in UI, black on-device); the key's Color fondo applies only when set (contrast ink auto). City search via Open-Meteo geocoding (`geo_search`, Spanish labels), no coordinates typing.
- **Layout:** `main.py` (device thread + auto-reconnect + executor) + `msd_protocol.py` + `msd_hotkey.py` (SendInput ctypes, no deps; INPUT struct must be 40 bytes or error 87; media/nav keys need EXTENDEDKEY). Profiles in `data_dir/msd_profiles.json`. Slot actions: launch/hotkey/text/command/multi/delay/profile/brightness (brightness `fixed` + `delta` +/-).
- **Widget = mini deck:** single undriven widget (`refresh_interval: 0`); `script.js` renders the 3×6 mirror in the card body (carousel pattern + MutationObserver), click opens the panel with that key preselected. Status dot + 15s self-refresh (pauses on `__coreframeDragging`).
- **Editor autosave (no save button):** every change persists via `set_key` immediately (field edits debounced 600ms) + `preview_key` thumb refresh; `✓ HH:MM:SS` indicator. Structural ops work on freshly collected state.
- **Enum dropdowns with pinned search** (`openEnumPopup`): hotkey keys multi-select grouped enum (`list_hotkeys`); command preset select + free-text custom.
- **Rigid panel (viewport-only sizing):** core `.result-panel-body` is `flex:1`, so bare `height` AND lone `flex-basis` are ignored — `.ext-msd_deck-panel` locks all four (`flex:none` + `height`/`min-height`/`max-height: 70vh`) + fixed `width:640px` (core modal is shrink-to-fit 480-900px). Grid `minmax(0,1fr)` + ellipsis, status/tabs nowrap, editor `flex:1` scroll. Cropper modal: fixed stage, square selection, geometry per-gesture.
- **swap_keys:** mouse drag-swap panel keys (plain mouse events, no HTML5 DnD) exchanges config + icon files + LCDs. Panel polls `get_config` every 2s to sync brightness slider with device-side changes.
- **Compose pipeline:** bg color always behind; glyph PNG recolored white→ink + label bottom, photo cover-bleed + label with shadow; then rotate90 CW + flip H+V + JPEG q90. `icons/` ships a 31-glyph 512px flat pack (drawn, no OS assets): gallery with crop fractions (`fractional_crop`, server-side hi-res compose). Uploads NEVER recolored (flattened onto key bg, black if transparent). `get_key_images` serves UPRIGHT display images (PNG if transparent).
- **Transparent bg:** slot color `"transparent"` stays RGBA in UI (checkerboard CSS) and flattens to black on-device.
- **Deps:** `hidapi==0.15.0` in requirements + `'hid'` in CoreFrame.spec hiddenimports (dynamic extension imports aren't collected otherwise). Pillow already bundled.
- **Permissions:** `"level": "system"` (USB/HID + process launch + input injection) → first start needs user consent in the UI.
- **Deploy:** copy `extensions/msd_deck/` to `Documents/CoreFrame/extensions/` (DATA_DIR, not the repo dir) + rebuild exe only when core/requirements/spec change.

### Network Monitor specifics

- **Transport:** WebSocket (migrated from HTTP polling). Uses `"realtime": true` in extension.json.
- **VPN panel:** renders instant skeleton, loads config → status → providers in parallel
- **VPN cache (`_vpnCache`):** Pre-fetched promises when the script loads; the panel reuses already resolved promises. The backend caches VPN detection for 30s (`_detect_vpns()` in `main.py`).
- **PID → Process name:** `_pid_name_map()` runs `tasklist /NH /FO CSV` (single call per refresh) instead of `psutil.Process()` per PID (avoids access-denied + race conditions on Windows).
- **Connection tabs:** two tabs (Incoming/Outgoing) in `#net-tab-content`, rendered with `renderTable()` helper.
- **Sorting:** outgoing connections sorted: those with processes first, `(pid:…)` entries last.
- **Pagination:** 200 rows by default, "See more" button that expands to all (via `showingAll` flag + re-render). Resets to 200 when switching tabs.
- **Click action widgets:**
  - VPN badge → `"click_action": "vpn_control"` → opens VPN panel
  - Open ports → `"click_action": "show_ports_panel"` → opens panel with ports + connections

### API

- `GET /api/extensions` → list of extensions with metadata, widgets, js_modules, css_modules
- `GET /api/extension/{id}/{action}` → executes action (GET)
- `POST /api/extension/{id}/{action}` → executes action with body data
- `GET /ext-static/{id}/{path}` → serves files from `extensions/{id}/static/`

All `/api/*` routes require `X-CoreFrame-Token` (obtained from `/api/token`).

## Process Manager (reference)

- **CSS prefix:** `ext-pm-` (hidden floating panel), `ext-pm-modal-` (fullscreen modal)
- **IDs:** `ext-pm-panel` (hidden via CSS), `ext-pm-toggle`, `ext-pm-search`, etc.
- **JS:** `extensions/process_manager/static/script.js` (loaded via `js_modules`)
- **CSS:** `extensions/process_manager/static/style.css`
- **Hook:** `registerMenuHook('process_manager', 'get_processes', fn)` that opens the modal from the menu
- **Real icons:** extracted via `ctypes` (CreateDIBSection + DrawIconEx) + Pillow in the backend, cached with LRU of 256 entries
- **Grouping:** processes grouped by name (like Windows Task Manager). Group header row with `▶` expand arrow, children rendered inline with `display:none` when collapsed.
- **Click behavior:** single click on group header → expand/collapse; double click on child row → context menu with details + End Task.
- **Icon cache:** `_iconCache` keyed by **process name** (not PID). Only one API call per name via `get_icon_by_name` endpoint. Group header and children share the same icon.
- **Kill group:** multi-process group headers have `✕` button that kills all instances with confirmation (`killGroupProcesses`). Single-process rows have individual `✕`.
- **Auto-refresh:** 3s interval via `setInterval(refreshProcessPanel, 3000)`. State preserved across refreshes via `_expandedGroups` and `_iconCache`.
- **Modal:** `showProcessManagerModal()` opens fullscreen overlay with grouped table, sortable columns, search filter.

## Security

- Bind to `127.0.0.1` (no external access)
- Single instance: `run_coreframe.pyw` probes `/api/token` at startup; if a server is alive it brings its window front (FindWindowW + EnumWindows fallback, ctypes only) and exits 0. No splash, no duplicate server. Skipped for `--ext-runner` children.- CORS restricted
- SHA-256 token generated at startup, required on all API calls
- `Connection: keep-alive` on HTTP responses (asset serving)
- SocketIO with `transports=['websocket']` on server and client — zero HTTP polling

## Known pitfalls

1. **Restart loop with `debug=True`:** writing `extensions.json` triggers Flask reloader to restart. Fixed: only write if content changed (`app.py:182-193`).
2. **Missing Pillow in venv:** `process_manager` fails silently without `PIL`. Listed in `requirements.txt`, `run.bat` installs it automatically.
3. **Outdated server:** old server doesn't reflect file changes. Kill process and restart.
4. **Browser cache:** after changes, Ctrl+F5. Extension JS/CSS additionally serve `no-store` + `?v=<boot-timestamp>` (`loadExtensionAssets` in `app.js`): a stale bundle looks exactly like "the fix didn't work".
5. **Duplicated CSS Modules:** if an extension is disabled, its `css_modules` is not loaded (the core iterates active extensions). No automatic cleanup of orphaned styles in the DOM.
6. **`psutil.Process(pid).name()` fails with access-denied on Windows for some system processes.** Solution: use `tasklist /NH /FO CSV` and parse CSV, don't call `psutil` per PID.
7. **VPN status slow (>30s) if external providers are called without cache.** Solution: `_vpnCache` with pre-fetched promises when script loads; panel reuses already resolved promises.
8. **"See more" button didn't expand:** `showTab()` reset `showingAll = false` at start, overwriting the flag. Solution: `expand` parameter in `showTab(tab, expand)` that skips the reset.
9. **TIME_WAIT accumulated from HTTP polling:** each widget opened a new HTTP connection. Solution: migrate to generic WebSocket (`realtime_broadcast()` in `app.py`). All extensions with `"realtime": true` use the persistent socket. Zero periodic HTTP connections.
10. **SocketIO polling transport:** by default SocketIO uses `['polling', 'websocket']`, starting with HTTP polling → TIME_WAIT. Solution: force pure WebSocket on client (`transports: ['websocket']`).
11. **`refresh_interval` in ms vs seconds:** the interval in `extension.json` is in milliseconds, but `time.time()` returns seconds. Using `interval` directly as seconds caused system_monitor (2000ms) to update every 2000s instead of every 2s. Solution: divide by 1000 (`interval / 1000.0`).
12. **Single blocking thread:** the original `realtime_broadcast` loop processed all extensions sequentially. If `get_open_ports` took 3s, it froze system_monitor. Solution: one daemon thread per extension (`_poll_extension`).
13. **Timing drift:** fixed `time.sleep(1)` + loop overhead accumulated delay. Solution: `next_tick = max(next_tick + interval, tick + interval)` which maintains fixed cadence even if an iteration takes longer.
14. **Restart button spins forever:** old `setTimeout(() => location.reload(), 1000)` assumed server is back in 1s, but restart + extension loading can take 5-30s. Solution: poll `/api/token` every 1s until the server responds, then `location.reload()`.
15. **Child rows not expandable:** `renderPanelGroupRows`/`renderWidgetGroupRows` only rendered children when `isExpanded` was true. On click, no DOM existed to show. Solution: always render children with `style="display:none"` when collapsed, toggle via inline style.
16. **Frameless window flicker on startup:** `webview.create_window(framless=False)` + subsequent `WindowState='maximized'` triggers a visible frame → unframe → re-maximize cycle (~1s flash). Solution: `_frameless_ok` guard flag in `run_coreframe.pyw` — timer callbacks only apply frameless if the first `_apply_initial_frameless()` succeeded.
17. **Native drag in frameless mode:** pywebview's `easy_drag=True` (default) allows dragging the entire window from any area without `-webkit-app-region: drag`. Solution: `easy_drag=False` in `webview.create_window()`.
18. **Widget drag jank (superseded blanket rule):** the old `body.widget-drag-active .widget-extension:not(.widget-dragging) { pointer-events: none }` fix is REMOVED — the coordinate-based engine never hit-tests, so the rule was pure full-document recalc cost at grab+drop. Only the dragged element keeps `pointer-events: none`.
19. **Drag/drop lag with heavy widgets (all core-side):** (a) `onMove` ran on EVERY mousemove with zero throttling, calling `getComputedStyle(grid)` twice + `querySelectorAll('.widget-extension')` per test, and the single-overlap displace scan called `getOverlappingWidgets` per candidate cell (up to ~72 DOM queries per mousemove). (b) Live updates rewrote widget DOM mid-drag. (c) SocketIO client used `transports: ['polling']` (fixed back to `['websocket']`). (d) Grab deep-cloned heavy subtrees; drop ran full-grid scans + synchronous flush. Solution: host-immunity protocol — `window.__coreframeDragging` + `coreframe-dragstart/dragend`, rAF-throttled `onMoveFrame`, per-gesture geometry cache + cross-gesture pitch cache (`_pitchCache` keyed by height+rows), single per-frame occupancy map, realtime queue with time-sliced (8ms/frame) flush, refresh/applyWidgetState skipped mid-drag, live-widget drag via transform (compositor-only, no clone), `content-visibility: auto` on cards, map-based drop (`findFreeSpotOnMap`), reads-before-writes grab order.
20. **pywebview SetWindowPos ctypes crash:** `winforms.py:635` passes `None` for cx/cy to `windll.user32.SetWindowPos()` (args 5-6). ctypes rejects `None` as non-integer → `ctypes.ArgumentError` flood (39K+ in log) → WinForms thread congestion → `Timeout (0:00:15)!` from faulthandler → extension heartbeat failures → process death. Solution: monkey-patch in `run_coreframe.pyw:462-497` replaces `BrowserForm.move` with safe version using `0, 0` for cx/cy. Secondary defense: patched `site-packages/webview/platforms/winforms.py:640-641` directly. The exe MUST be rebuilt after any change to `run_coreframe.pyw` for the patch to take effect.
21. **Extension runner segfault on shutdown (hid.dll_unloaded):** isolated runners died inside C calls (e.g. blocking `hid.read`) during interpreter teardown because `on_stop` was never invoked on stdin-EOF. Fix: `ext_runner` (BOTH `coreframe/extensions/ext_runner.py` AND the embedded copy in `run_coreframe.pyw`) calls `instance.on_stop()` + 0.6s grace in a `finally`. Extensions must join threads and close handles there (see msd_deck `on_stop`). Daemon threads alone do NOT save you.
22. **`/api/restart` NameError:** `coreframe/app.py` used `jsonify` without importing it — restart always 500'd (a failed restart + stacked manual relaunches caused several "won't open" pileups). Fixed import.
