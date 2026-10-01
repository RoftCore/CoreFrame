# COREFRAME — GUIDE FOR ASSISTANTS

> **IMPORTANT:** update this file whenever the architecture changes, core mechanisms are modified, or a new pitfall is discovered. It is the source of truth for any AI working on the project. Authoring details live in `docs/`; keep the split: this guide is rules and invariants, `docs/` is reference.

## Branching Strategy (CRITICAL)

- **`main`**: ONLY tested, released versions (tagged `vX.Y.Z`). No direct pushes.
- **`development`**: all feature work, bug fixes, experiments. PRs target `development`.
- **Release flow**: `development` → tested → merge to `main` → tag `vX.Y.Z` → GitHub Actions builds the release.
- **CI** (`.github/workflows/build.yml`) runs on push to `main` and on `v*` tags, on Python 3.13, and fails if the ext_runner mirror is out of sync (see [Process model](#process-model)). There is no CI build for `development`: build locally with `py -3.13 -m PyInstaller --noconfirm CoreFrame.spec`.

## Identity

A personal control center with a widget grid, scenes, and self-contained extensions for system monitoring, VPN, processes and network analysis. Vanilla SPA, no frameworks. The core is generic: it knows nothing about any individual extension, and each extension lives in its own directory with its own backend, frontend and CSS.

## Stack

- **Backend:** Python **3.13** (Flask + Flask-SocketIO). 3.13 is the only supported runtime; 3.14 segfaults natively (pitfall 24). Never build with 3.14.
- **Frontend:** HTML, CSS, vanilla JS (no frameworks, no build step).
- **Realtime:** one daemon thread per extension with `"realtime": true`, fixed cadence via `next_tick`, SocketIO forced to `websocket` transport on both ends. No HTTP polling for widgets.
- **Extensions:** loaded with `importlib` from `DATA_DIR/extensions/` at runtime.
- **Isolation:** every extension runs in its own OS process (JSON-RPC over stdio). The core never imports extension code in-process.

## Structure

```
CoreFrame/
├── run_coreframe.pyw          # Windows host: single-instance check, splash, tray, frameless
├── app.py                     # 6-line back-compat shim re-exporting coreframe.app
├── coreframe/                 # All server code
│   ├── app.py                 # Flask app factory, /api/quit, /api/restart, socketio wiring
│   ├── config.py              # Paths: BASE_DIR, DATA_DIR, STATIC_DIR, EXTENSIONS_DIR, ports
│   ├── auth.py                # SHA-256 token, before_request guard for /api/*
│   ├── websocket.py           # SocketIO events, realtime_update
│   ├── utils.py               # Shared helpers
│   ├── routes/
│   │   ├── api.py             # /api/extensions, /api/extension/<id>/<action>, health, debug
│   │   ├── widgets.py         # /api/widget-state, scene widget layout
│   │   ├── scenes.py          # /api/scenes CRUD, activate, backgrounds
│   │   ├── static.py          # /ext-static/<id>/<path> and /ext-data/<id>/<path>
│   │   ├── install.py         # /api/install_extension, /api/package_extension
│   │   └── marketplace.py     # /api/marketplace/*
│   └── extensions/
│       ├── loader.py          # Discovery, consent gate, migration, poller threads
│       ├── bridge.py          # Per-extension process supervision, restart, drain
│       ├── ext_runner.py      # The child process: restrictions + JSON-RPC loop
│       ├── permissions.py     # Permission levels, consent, escalation
│       ├── health.py          # Heartbeats, isolation accounting
│       ├── security.py        # Consent guards and path validation for the host
│       └── deps.py            # Lazy pip install of extension requirements
├── static/
│   ├── index.html             # SPA shell
│   ├── css/                   # palette, layout, components, utilities, reset, widget-control, core-effects
│   └── js/
│       ├── app.js             # Boot, extension loading, asset loading
│       ├── core.js            # Realtime intake, widget updates, generic WebSocket
│       ├── widgets.js         # createExtensionCard, createSubWidget, updateWidgetValue
│       ├── menu.js            # Sidebar, registerMenuHook, executeMenuAction
│       ├── window.js          # Window mode (windowed/frameless/fullscreen)
│       ├── permissions.js     # Consent modals and escalation prompts
│       ├── install.js         # Marketplace / install flows
│       ├── utils.js           # apiFetch, showToast, feather, formatBytes
│       └── widget-control/    # Scene/layout engine, numbered by load order
│           ├── 00-state.js    # Shared state + cfHidden/cfHide/cfShow (pitfall 29)
│           ├── 01-scenes.js   # Scene switching
│           ├── 02-layout.js   # Grid layout, placement, drag/drop
│           ├── 03-menus-styles.js
│           └── 04-init.js     # Bootstrap
├── extensions/                # Dev copy of extensions only; runtime loads from DATA_DIR
├── scaffolds/template-extension/
├── tools/
│   ├── build_runner.py        # Builds the lightweight runner into runner.zip
│   └── sync_ext_runner_source.py  # Mirrors ext_runner.py into run_coreframe.pyw
├── runner.spec, runner.zip, runner_version_info.txt   # The child-process build
├── CoreFrame.spec, version_info.txt, CoreFrame.ico, splash.png
├── docs/                      # EXTENSIONS.md, BRIDGE.md, EXTENSION_NOTES.md
├── requirements.txt, extensions.json (generated), coreframe.json, widget_state.json
└── AGENTS.md, README.md, CHANGELOG.md
```

`extensions.json` and `widget_state.json` are generated at runtime: never edit them by hand.

## Architecture rules (IMPORTANT)

1. **The core contains NO code or CSS of any specific extension.** Zero references to extension names, specific classes, or per-extension if/else. If an extension is deleted, no trace should remain in the core — this includes this guide (extension internals belong in the extension, or `docs/EXTENSION_NOTES.md`).
2. **Each extension is self-contained.** Backend (`main.py`), frontend (`static/*.js`) and styles (`static/*.css`) live in its own directory, declared via `js_modules` / `css_modules` in `extension.json`.
3. **The core provides generic mechanisms:** 12-column grid, extension card, sub-widgets, realtime transport, menu hooks, scenes, permission levels, process supervision. No per-extension knowledge.
4. **Extensions run out of process.** In-process execution is not an option: a crash, hang or native fault in one extension must never take the host down (pitfalls 21, 26, 28).
5. **Data lives in `DATA_DIR`, not in the extension folder.** `config.get('data_dir')` points at `Documents/CoreFrame/data/<id>/`. Packaged or downloaded media goes there and is published with `"serve_data": true` → `/ext-data/<id>/<path>`.

## Code style

- **Split code into multiple files.** Structured and ordered; use folders when needed.
- **Minimal comments:** max one line, at the start of a function or only where essential. Compact, in English, one sentence.
- **English in code artifacts.** Comments, function and variable names, error messages, logs and single-language UI text are English. No exceptions.
- **Multilingual content is fine when translation is a feature of the extension:** phrase tables, a language selector, localized labels, bilingual prompts. That is product behaviour, not a style violation. The test: is the Spanish *content the extension ships to the user on purpose* (keep it) or is it *the code speaking* (translate it)?
- **No native browser popups:** `alert()`, `confirm()` and `prompt()` are blocked in the pywebview/WebView2 host — they never appear and they stall the caller. Use the core modal pattern (`.pkg-overlay` + `.pkg-dialog` with `.pkg-header`/`.pkg-body`/`.pkg-footer` from `layout.css`, click-outside to dismiss) or a scoped overlay of your own. Never depend on native dialogs.
- **Python must stay compact:** past ~300 lines, evaluate splitting. Keep it whole only if it is one cohesive concern.
- **HTML may stay in a single file.** JavaScript may run longer, but split it by logic when it grows.
- **Never edit files with `Get-Content | Set-Content` or `Out-File`** on this project: PowerShell 5.1 round-trips mangle UTF-8 (BOM + mojibake) and once silently corrupted three files' user-visible text. Use the editor tools and verify with a byte-level check (pitfall 30).

## Process model

Every extension gets its own process. `bridge.py` supervises them; the child is `runner.zip`'s `CoreFrame.exe`, or the main exe with `--ext-runner <config>` when the runner is absent.

- The child reads a temp JSON config (`config`, `ext_path`, `restrictions`, `coreframe_config`), applies its restrictions **before** importing extension code, sends `{"result": "ready", "id": 0}`, then serves JSON-RPC on stdio.
- **The child source is mirrored, not imported.** `coreframe/extensions/ext_runner.py` is the only editable copy; `run_coreframe.pyw` embeds a byte-identical copy because `--ext-runner` must run before any heavy import (`coreframe/__init__.py` pulls in Flask). After editing the runner, run `python tools/sync_ext_runner_source.py`; CI runs it with `--check` and fails on drift.
- Full protocol, config format and examples: `docs/BRIDGE.md`.

## Permissions

Levels 0–5 (`basic`, `storage`, `user_files`, `network`, `system`, `admin`) are declared per extension and enforced **in the child process** (file access allowlist, socket blocking, subprocess blocking, module purge). Levels 3+ require user consent on first start, stored per extension. Escalation is a runtime request via a `extension_escalation_request` event. Details and the correct way to request elevation: `docs/EXTENSIONS.md`.

## Realtime

`realtime_broadcast()` starts one daemon thread per extension with `"realtime": true`, `refresh_interval > 0` and widgets. Each thread keeps fixed cadence with `next_tick = max(next_tick + interval, tick + interval)`, so a slow iteration never accumulates drift and never blocks other extensions. The frontend applies values in `core.js`; extensions marked `realtime: true` are skipped by the HTTP poller. Poller threads must honour the restart drain (pitfall 26).

## Menus and hooks

`registerMenuHook(extId, action, fn)` registers a sidebar panel handler. `menu.js:executeMenuAction` runs the hook when one exists, otherwise it falls back to a generic fetch and renders the JSON. `click_action` on `badge` / `text` / `list` widgets wires the same path.

## Widgets

Generic sub-widget types: `text`, `badge`, `list`, `chart`, `terminal`, `button`. Data arrives through `updateWidgetValue(el, response)` in `widgets.js`. Per-type payload shapes, the full `extension.json` reference and the HTTP API are in `docs/EXTENSIONS.md`.

## API

- `GET|POST /api/extension/<id>/<action>` — extension actions (`GET` = no args, `POST` = JSON body as `data`).
- `GET /api/extensions` — registry, `GET /api/extensions/<id>` — detail, `POST /api/extensions/<id>/load|unload` — process control.
- `GET /api/scenes`, `POST /api/scenes/activate`, `GET|PUT /api/scenes/<id>` — scene layout.
- `GET /api/widget-state` — grid placement.
- `GET /ext-static/<id>/<path>` — extension assets, immutable caching for images, `no-store` for `.js`/`.css`/`.html`.
- `GET /ext-data/<id>/<path>` — extension data dir, only when the manifest sets `serve_data`, with Range/206 support.

All `/api/*` routes require the `X-CoreFrame-Token` header (fetch it from `/api/token`).

## Security

- Binds to `127.0.0.1`; CORS limited to the local origin.
- Single instance: the host probes `/api/token` at startup, brings the existing window to the front and exits if a server is already alive. Skipped for `--ext-runner` children.
- SHA-256 token generated at startup, required on every `/api/*` call.
- Static assets served with `Connection: keep-alive`; SocketIO is `websocket`-only on both ends.

## Known pitfalls

1. **Restart loop with `debug=True`:** writing `extensions.json` triggers the Flask reloader. Fixed by writing only when content changed (`coreframe/app.py`, registry save).
2. **Missing Pillow:** extensions using PIL fail at import with a cryptic `_imaging` error. It ships in `requirements.txt` and in the frozen bundle; a `lib/` directory holding a *different* Python's wheels is the usual cause — reinstall the dep with the same interpreter the children run (`py -3.13 -m pip install --target ...`).
3. **Outdated server:** an old process does not reflect file changes. Kill it and restart.
4. **Browser cache:** after frontend changes press Ctrl+F5. Extension JS/CSS also serve `no-store` with a `?v=<boot-timestamp>` cache buster — a stale bundle looks exactly like "the fix didn't work".
5. **Duplicated CSS modules:** a disabled extension's `css_modules` is not loaded and orphaned styles stay in the DOM. No automatic cleanup.
6. **`psutil.Process(pid).name()` raises access-denied** for some system processes on Windows. Use `tasklist /NH /FO CSV` instead of per-PID calls.
7. **Slow first paint when a panel fetches everything up front:** prefetch into a promise cache when the script loads and reuse the resolved promises; the backend caches its own detection.
8. **A "show all" flag reset by the tab switcher:** pass an explicit `expand` argument so switching tabs does not clear the flag.
9. **TIME_WAIT from HTTP polling:** every widget opened its own connection. Use `"realtime": true` and the persistent socket.
10. **SocketIO polling transport:** the default is `['polling', 'websocket']`, which starts with HTTP polling. Force `transports: ['websocket']` on the client.
11. **`refresh_interval` is in milliseconds:** treat it as seconds and a 2000 ms widget updates every 2000 s. Divide by 1000.
12. **Single blocking thread:** the original sequential realtime loop froze every extension when one action was slow. One thread per extension.
13. **Timing drift:** `sleep(1)` plus loop overhead accumulates. Use `next_tick = max(next_tick + interval, tick + interval)`.
14. **Restart button spins forever:** a fixed `setTimeout(reload, 1000)` assumed the server returns in 1 s. Poll `/api/token` until it answers, then reload.
15. **Collapsed rows not expandable:** children were only rendered when expanded, so there was nothing to show. Always render them and toggle visibility.
16. **Frameless flicker on startup:** `webview.create_window(frameless=False)` followed by `WindowState='maximized'` flashes a frame. Guard the timer callbacks with a flag set by the first successful `_apply_initial_frameless()`.
17. **Native drag in frameless mode:** pywebview's `easy_drag=True` lets any area drag the window. Pass `easy_drag=False`.
18. **Widget drag jank (superseded blanket rule):** the old `pointer-events: none` on all non-dragged cards is REMOVED — the coordinate-based engine never hit-tests, so the rule was pure full-document recalc. Only the dragged element gets `pointer-events: none`.
19. **Drag/drop lag with heavy widgets:** `onMove` ran on every mousemove with no throttle, re-queried the grid per candidate cell, and live updates rewrote DOM mid-drag. Host-immunity protocol: `window.__coreframeDragging` + `coreframe-dragstart/dragend`, rAF-throttled moves, per-gesture geometry cache, single per-frame occupancy map, realtime queue flushed in 8 ms slices, drag via `transform` (compositor only, no deep clone), `content-visibility: auto` on cards.
20. **pywebview `SetWindowPos` ctypes crash:** `winforms.py` passes `None` for cx/cy and ctypes rejects it → `ArgumentError` flood → WinForms congestion → `Timeout (0:00:15)!` → heartbeat failures → death. Fixed by monkey-patching `BrowserForm.move` in `run_coreframe.pyw` to pass `0`. **Any change to `run_coreframe.pyw` needs a rebuild** — the host is compiled into the exe.
21. **Runner segfault on shutdown:** isolated runners died inside C calls during interpreter teardown because `on_stop` never ran on stdin EOF. The runner now calls `instance.on_stop()` plus a short grace in a `finally`. Extensions must join their threads and close handles there; daemon threads alone do not save you. Remember the runner source is mirrored (see [Process model](#process-model)).
22. **`/api/restart` NameError:** the module used `jsonify` without importing it, so restart always 500'd and the user piled up manual relaunches.
23. **NEVER create the window with `frameless=True`:** on some machines WebView2 wedges and pywebview's `loaded` never fires, leaving a half-born app (server up, no window, watchdog silent). Always `create_window(frameless=False)` and let the existing `_apply_initial_frameless()` (BeginInvoke, center-then-maximize) do the switch after the show. Manual F11 uses the same path and always works, which is why it looks like "only boot fails".
24. **Build ONLY with Python 3.13 (`py -3.13`), NEVER 3.14:** the pre-release interpreter segfaults natively (`0xc0000005`, a different offset each time) under load. Rebuilding with 3.13 turned four crashes in three days into zero. `pip` is fine; only `npm` is banned.
25. **The watchdog must never touch the STA synchronously:** forcing a COM property on the WebView2 control or a synchronous `Invoke` blocks forever when the STA is wedged — which is exactly the case the watchdog exists for. Post both with `BeginInvoke`. On the watchdog path, nothing may block.
26. **A dead extension must never take down the host:** `/api/restart` used to leave realtime pollers running forever (one leak per restart per extension), kill children fire-and-forget while new ones spawned, and allow concurrent restarts. Now: `loader.stop_all_polls()` with per-tick re-resolution of the stop event, error logs throttled to 1/60 s, restart serialized under a lock (409 when busy) with a bounded parallel drain before reload, and health backoff plus session quarantine. `bridge` also reaps children that were spawned before a failed handshake. **On the restart path, stop everything old before starting anything new.**
27. **One widget must not jank the UI:** extension JS and data share the host's main thread. The core coalesces realtime per extension (250 ms, latest wins), hashes huge values cheaply (length + head + tail past 200 KB), caps lists at 300 rows and the terminal at 100 KB. A synchronous infinite loop in widget JS is *not* fixable from the core (only iframe sandboxing would); that is the accepted risk of the trust model.
28. **The segfault site was the traceback printer:** export-table forensics put every crash at `PyTraceBack_Print+0xC` — the process died while *printing* a traceback, with all threads idle. `faulthandler.dump_traceback_later(15, repeat=True)` walked every thread through frame printing forever. Never run repeating full-stack dumps in production: a single-shot boot net plus sparse rotating snapshots (`stacksnap*.log`) is enough.
29. **Never ask "is this widget hidden?" by reading `style.display`:** `display:none` drops the box tree and Chromium discards the decoded images with it, so revealing a heavy widget pays a full re-decode. Measured: a 16-photo gallery cost `paint_ms` 824–1085 on **every** scene switch while the core's own commit was 1.9 ms, with zero backend calls (pure raster/decode). Off-scene widgets move off-viewport with `.cf-offscene` (keeps the decode, skips raster, touches no inline style — drag owns `transform`). Contract: **`cfHidden(el)` / `cfHide(el)` / `cfShow(el)`** in `00-state.js`; a widget that must be torn down opts out with `"keep_alive": false`. Adding a new `style.display` read on a widget is the bug.
30. **PowerShell 5.1 corrupts UTF-8 on round-trips:** `Get-Content | Set-Content -Encoding UTF8` injects a BOM and re-encodes every non-ASCII character as mojibake (an em dash becomes three bytes of garbage), and byte-slicing a file with `Out-File` shifts offsets. It has silently broken `Cargando aplicación...` on the splash and 88 lines of Python. Edit with the editor tools, write with an explicit `UTF8Encoding($false)`, and scan the result for BOM/mojibake before committing — never quote the corrupted bytes inside a file you are about to scan.
31. **`diff` in PowerShell is `Compare-Object`, not a diff:** it reported "0 differences" between two files that differed by 27 real lines. Never trust it for change detection — use `git diff --no-index`, or do the comparison in Python with the same decoding the real consumer uses. And validate measurements, not just that the script ran. The nastier version of this bug is a **verification script whose cache is keyed too coarsely** (a per-file count instead of per-pattern): every later assertion then compares against a stale number, passes without ever looking for its own pattern, and the `replace` becomes a silent no-op. Key assertions to the exact thing being asserted, and re-read the file afterwards to confirm the new text is there.

## Related documents

- `docs/EXTENSIONS.md` — authoring reference: manifest, widget types, permissions, HTTP API, publishing.
- `docs/BRIDGE.md` — child-process protocol, config format, runner mirror, language examples.
- `docs/EXTENSION_NOTES.md` — extension-specific knowledge kept out of this guide. Unverified snapshots: check the extension source before relying on them.
- `CHANGELOG.md` — released changes, newest first.
