# Changelog

## v1.0.1 — Extension Isolation, Fault Tolerance, and Window Mode Persistence

**Release date:** 2025

### Features

- **Minimize button** added next to the settings gear (`#3333816`)
- **Favicon** — CoreFrame icon replaces the topbar logo text (`#bc56468`)
- **Install confirmation** — Show button after marketplace install instead of page reload (`#49af491`)
- **Pip-based dependency installer** — extensions can declare deps in `extension.json`, installed via bundled pip at runtime (`#8f9bcd0`)
- **Auto-bundle extension deps** into `lib/` during packaging; fixes `spotify_downloader` missing `spotify_scraper` (`#2fd5135`)
- **`data_dir` injection** — extensions receive a writable data directory in config; vault data migrated to `CoreFrame/data/` (`#11abf9d`)
- **Reload system redesigned** to perform inside the binary file (`#999d83d`)
- **CI/CD** — GitHub Actions workflow: auto-build on tags `v*`, auto-create release with Windows + Linux binaries, `workflow_dispatch` trigger, custom `gi.repository.WebKit2` hooks for Linux (`#8362ce6`, `#6abca76`, `#5d4fc80`, `#cdbe5ec`, `#70742d6`)

### Bug Fixes — Scene System

- `_sceneOrder` array for explicit render order, preserves drag-drop reorder (`#49d3168`, `#7a5ce7c`)
- Scene keys sorted numerically — prevents `Object.keys` insertion order quirks with `scene_11+` (`#c323647`, `#3a1a106`)
- New scene always goes to end of `_sceneOrder` (`#26cf4a2`)
- `sceneOrder` persisted in `widget-state` to survive restarts (`#f26609d`)
- Optimistic scene create/delete — UI updates instantly, API fires in background (`#aa64bfc`)
- Eliminated double HTTP roundtrip on scene create/delete (`#cee170b`)
- Removed redundant `POST`/`DELETE` scene API calls — `persistScenes` handles state atomically (`#08133fd`)
- Active scene button visually distinct with underline indicator (`#411edea`)
- Icon picker highlight no longer cleared by `saveIcon`; enhanced selection visibility (`#638f3a7`)
- Prevented scenes being overwritten by `autoAddExtensions` on corrupt state (`#b1bd14f`)

### Bug Fixes — Extension & Marketplace

- `autoAddExtensions` no longer adds extensions already known at page load (`#9f94527`)
- Marketplace uses `window.extensionsData` consistently to reflect deletions (`#636be4b`)
- Async marketplace install with proper error handling (`#500bf4f`)
- Install toast cleared on done/error and in `refreshAfterInstall` (`#ff3ea1e`)
- Don't auto-show installed extensions; expose `persistScenes` (`#7627b3f`)
- Background install, cleanup protocol, `spotipyfree` dep detection (`#68bb9bc`)
- Validate `extension.json` before blocking reinstall; allow overwrite if corrupted (`#f14fb7f`)
- Remove shipped `lib/` from extension after syncing to shared lib (`#ee02edb`)
- Extension `hideScrollbar` / scroll support + WebSocket `js_modules` fix + IP fallbacks (`#6a2c117`)
- Refreshed widget on Show click, reloaded JS modules (`#010b6fd`)

### Bug Fixes — Runtime & Stability

- Thread-safe atomic write for `widget_state.json` with stale `.tmp` cleanup (`#64e7eb7`)
- Race condition on widget init causing hidden extensions to reappear (`#9de5ed1`)
- Forced MSHTML backend in `.exe` build to avoid missing WebView2 DLL (`#b2d3c3f`, `#586dfea`)
- WindowState enum, interop DLL path, single-instance mutex, inline pip install (`#22df8ef`)
- Patched `interop_dll_path` for frozen build, added debug boot logging (`#9151d52`)
- Bundle full Python stdlib so runtime-loaded widget deps import cleanly on any machine (`#9c91419`)
- Kept bundled deps ahead of shared lib to avoid stale `cffi` shadowing (`#b74f78d`)
- Bundle `pip`/`setuptools`/`wheel` and register frozen distlib finder for runtime extension dep installs (`#af282bd`)

### Refactors

- Removed hardcoded widget IDs from core; moved format config to extensions (`#1f6028f`)
- Don't create data dirs eagerly — extensions do it on demand (`#aa5c6dc`)

### CI / Build

- Pinned deps and embed version metadata to reduce AV false positives (`#c8556f3`)
- Matched local build env (`py3.14` + `pyinstaller 6.17`) to avoid AV false positives (`#455e9f0`)

### Docs

- Global frontend utilities section added to `EXTENSIONS.md` (`#010b6fd`)
- `data_dir` storage documented in `EXTENSIONS.md` and `README` (`#8e1e4a4`)
- `EXTENSIONS.md` — corrected `scroll false` description (`#e3086f1`)
- README updated with image, marketplace link, sponsor button (`#b173304`, `#25571d3`, `#04fcfb3`, `#e7296ff`)

### Other

- MIT license added (`#91156ff`)

---

## v1.0.2 — Native GDI Loading Splash, Instant Swap, OneFile Portable

### Features

- **Native GDI loading splash screen** — zero-dependency Win32/GDI splash, renders instantly before Python loads (`#011ade0`)
- **Instant startup** — async deps, instant window, local loading page (`#ebab01c`)
- **Themed loading page** — CoreFrame dark theme (`#0d0d1a`) background (`#8765d38`, `#1ba6aba`)

### Bug Fixes

- Eliminated white flash: `html` parameter + `background_color` (`#1cce9c5`, `#b4f40ed`)
- `cffi` version mismatch, load timeouts, heartbeat handling (`#1a27924`)
- Intermittent post-load freeze + boot UX (`#cbefa2f`)

### CI

- Tkinter support: explicit Tcl/Tk data collection, `collect_all()` spec fix (`#9674755`, `#ae15c19`, `#4c76e24`, `#9dad2e2`, `#e48777f`)
- Build on development branch for testing (`#e600cae`)
- Branching strategy documented in `AGENTS.md` (`#cabb0ca`)

---

## v1.1.0 — Permission System, Subprocess Isolation & Autoruns

**Release date:** 2026-09-01 — Security overhaul, long-term stable version for testing.

### Features — Permissions & Isolation

- **6-level permission model** (`basic 0` → `admin 5`) with consent modals, `permissions.json` + `permissions_denied.json`, and `file_whitelists.json` for `user_files` mediated access.
- **Subprocess isolation for all Python extensions** via `coreframe/extensions/ext_runner.py` (embebido como string en `run_coreframe.pyw`, sin archivos en `MEIPASS`) → `CoreFrame.exe --ext-runner <config.json>` JSON-RPC over stdin/stdout. Enforces `builtins.open` (allowed_dirs + exe dir + `_MEIPASS` + `TEMP` + `ext_path`), `socket` and `subprocess` blocking at OS level. Fixes `builtins.open` bypass via `import` time capture.
- **UAC elevation via `coreframe_helper.exe`** (`ShellExecuteW("runas")` + batch mode) for `registry_write`/`service_control`/`delete_file` — single UAC prompt, no need to run CoreFrame as admin. `win_tweaker` and `windows_autoruns` use it.
- **Escalation `Once` vs `Always`** — `Once` stored in `temp_escalations` and consumed after one successful `check_escalation`, `Always` in `permanent_escalations`. Frontend `permissions.js` shows `Once`/`Always` and `script.js` polls `GET /permissions` (100ms + socket) for instant retry.

### Features — Autoruns Extension

- **New extension `windows_autoruns`** (`system` + escalation `admin` for `toggle`) — native Autoruns clone: Registry `Run`/`RunOnce` (HKLM/HKCU/WOW6432), Startup folders, Winlogon, Services (125 via `SYSTEM\CurrentControlSet\Services`), Drivers, Scheduled Tasks (CSV), BHOs. Shows `Hide Microsoft`/`Hide Windows` (like Sysinternals), publisher via `GetFileVersionInfoW`, 16×16 icons via `SHGetFileInfoW→DrawIconEx→GetDIBits→PIL→base64` (114/167), table with `Disable`/`Enable` staying visible (grey `ar-disabled`, `disabled.json` for registry). SunshineService correctly appears as `AUTO_START` and toggles via helper `service_control`.

### Bug Fixes — Widgets & Scenes

- **Revoke paperweight:** `03-menus-styles.js` `showRevokeConfirm` now does `hideWidget` + `loadState().applyHiddenState` so revoked stays in `Extensions` and `Show hidden widgets` picker, only hidden from viewport.
- **Widget disappearance on scene switch/reload:** `02-layout.js` `saveAllLayouts` now only updates `col/row/w/h` for visible DOM widgets, keeps `hidden` from `widget_state.json` (source of truth). `01-scenes.js` `switchScene` simplified to 6 lines (no `deferred` magic, no `reload`).
- **Plain text fallback:** `switchScene` lazy-load now correctly does `loadExtAssets` + filtered `renderWidgets` for deferred, and `01-scenes.js` re-renders with `renderWidgets(filtered)` to avoid `--` → `text` plain.
- **Text selection in Autoruns table:** `style.css` `user-select: text` for `td`.

### Bug Fixes — Core & Security

- **Stale `widget_state.json` on scene change:** `saveAllLayouts` no longer reconstructs `hidden` from DOM, prevents empty `widgets: {}` on new scenes.
- **`ext_runner`  `TypeError: unhashable type: dict`** (f-string `{{e}}` in raw string) → fixed to `{e}`; `OSError Invalid argument` on close (stdout pipe) → `try/except OSError` around `ready` signal and `for line in sys.stdin`.
- **`PermissionError` on `MEIPASS` files:** `ext_runner` moved from `datas` file to `PYZ` hiddenimport + `exec(compile(...))` to avoid `Permission denied: _MEI.../ext_runner.py`.
- **`Security: cannot access .../CoreFrame.exe`:** `allowed_dirs=['/']` only matched `C:\` on Windows; added implicit allow for `sys.executable` dir + `_MEIPASS` and handling for `'/'` as any absolute path; added `DATA_DIR` handling for `user_files`.
- **Double wrap `{"value":{"value":...}}`:** `bridge.py:_call` now returns `result` directly if dict, fixes `notes`/`fortune_cookie` `[object Object]`.
- **CMD flash every 2s:** `bridge.py` `CREATE_NO_WINDOW|DETACHED_PROCESS` + `STARTUPINFO SW_HIDE` + `ext_runner` child `Popen` patch for `CREATE_NO_WINDOW`.
- **Slow startup (2.5s):** `health.py` `max_workers 8→16`, `bridge` `sleep 0.1→0.01`, `loader` prioritizes visible (but now loads all, ~0.5s for 3 visible).
- **Scene `widget_state` loss on `createScene`:** fixed `persistScenes` atomic write.

### Docs

- `docs/EXTENSIONS.md` new `### permissions` section with 6-level table, `extension.json` example, isolation details, admin helper, and frontend `403` handling (10s `showPermWaiting` cancellable, `Once` vs `Always`).

### Bug Fixes — CoreFrame (subprocess isolation)

- `ext_runner.py:355` / `run_coreframe.pyw:344` missing `Lib/site-packages` on Windows: `pip --prefix` installs to `lib/Lib/site-packages` but isolated child only added `lib` to `sys.path` → `ModuleNotFoundError: trimesh` even after successful `pip install` (seen in `glb_convex_hull` with `trimesh 4.12.2` in `lib`). Fixed by adding `Lib/site-packages` and `lib/python3.11/site-packages` to child's `sys.path` before `import`. **Error de CoreFrame, no de la extensión.**

### Other

- `coreframe_helper.spec` batch support, `run_coreframe.pyw` `--ext-runner` early exit before heavy imports.
- `MEMORY.md` and `SKILLS/plan-apocalipsis` updated.

---

## v1.0.0 — Post-Release (development branch)

### Bug Fixes

- 25 bugs — security, runtime UI, and state persistence (`#fc5bc78`)
- Correct `_client_count` import in health route (`#1bffb09`)
- Splash screen no longer stays always on top (`#a49a285`)

### Performance

- Non-blocking scripts for instant spinner on load (`#46d9920`)

### Refactors

- Split `app.py` (1855 lines) into modular `coreframe/` package (`#c470068`)
- Split frontend JS into focused modules (`#fde6217`)

### Chores

- Residual debug logs cleaned up + `.gitignore` updated (`#ebe4096`)
