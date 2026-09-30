# Extension Notes

> **Not core documentation.** Everything here is extension-specific and lives outside the core guide on purpose: `AGENTS.md` documents the host, and per rule 1 an extension's internals must not leak into it. These are **unverified snapshots** of knowledge that was expensive to acquire — read the extension's own source before relying on any of it, and update or delete a section when the extension changes. The core's generic contracts live in `docs/EXTENSIONS.md` and `docs/BRIDGE.md`.

## Hardware deck driver (Mars Gaming MSD-ONE)

- **Device:** VID `0x0B00` PID `0x1000`, HID usage page 65440 usage 1 (Ajazz AKP153 family, protocol v1, 512-byte packets). Hardcoded serial `355499441494`. The official Mars app must be closed first (it opens the device exclusively).
- **Protocol** (`msd_protocol.py`, pure and testable, ported from mirajazz + opendeck-akp153 + community notes): commands are `00 CRT 00 00 + ASCII` — `DIS`/`LIG` init, `LIG..<pct>` brightness, `BAT..<len><key+1>` + JPEG chunks + `STP` commit, `CLE...<key+1|0xFF>` clear, `HAN` sleep, `CONNECT` keep-alive. The key index on the wire is device+1. Input reports start with `ACK`, key at byte 9 (1-based, 0 = idle); v1 emits press-only (Down+Up together).
- **Key maps:** 18 positions (3 rows × 6 cols, OpenDeck parity). `OPENDECK_TO_DEVICE` / `DEVICE_TO_OPENDECK` tables. Positions 5/11/17 (1-based 6/12/18) are the **lateral strip**: 3 separate LCD cells filling the side screen, not missing keys.
- **Side-strip widgets** (`msd_widgets.py`): clock / weather (Open-Meteo) / system (psutil CPU+RAM). A backend thread repaints every 10 s and pushes only on byte-change, so the LCD does not flicker; repaint immediately on profile switch and on connect. HTTP goes through `requests` + certifi (stdlib `urllib` has no CA bundle in the frozen exe) and UI thumbnails never block on network (`fetch=False` plus a background warm on assign).
- **Empty cells stay dark:** no label/icon/builtin/widget means a single-key `CLE`, not a dark image push. `_paint_slot` centralises push-or-clear for every slot mutation.
- **Compose pipeline:** background colour behind everything; glyph PNG recoloured white→ink with a bottom label; photo cover-bleed with a shadowed label; then rotate 90° CW + flip H/V + JPEG q90. Uploads are never recoloured (flattened onto the key background, black if transparent). `get_key_images` serves upright display images.
- **Layout gotcha:** the core's `.result-panel-body` is `flex:1`, so a bare `height` **and** a lone `flex-basis` are both ignored — a rigid panel must lock all four (`flex:none` + `height`/`min-height`/`max-height`) plus a fixed `width`.
- **Deps:** `hidapi` in requirements **and** `'hid'` in the core spec's hiddenimports — a dynamic extension import is not collected otherwise.
- **Permissions:** `"level": "system"` (USB/HID + process launch + input injection) → user consent on first start.
- Note: the panel's city-search labels were written in Spanish, which violates the English-everywhere rule; translate them if that extension is touched again.

## Network monitor notes

- Realtime over WebSocket (`"realtime": true`), not HTTP polling.
- The VPN panel renders a skeleton first, then loads config → status → providers in parallel.
- VPN detection is cached in the frontend as promises resolved at script load, and in the backend for 30 s.
- PID → process name uses one `tasklist /NH /FO CSV` call per refresh instead of `psutil.Process()` per PID.
- Connection tables have Incoming/Outgoing tabs, sort processes first, page at 200 rows with a "See more" toggle that resets when the tab changes.

## Process manager notes

- CSS prefix `ext-pm-` (floating panel) and `ext-pm-modal-` (fullscreen modal); loaded via `js_modules`; opens from the menu through `registerMenuHook`.
- Real icons are extracted with `ctypes` (`CreateDIBSection` + `DrawIconEx`) plus Pillow, cached with an LRU of 256 entries keyed by **process name** (not PID), so a group header and its children share one call.
- Processes are grouped by name like Windows Task Manager: single click on the header expands/collapses, double click on a child opens a context menu with details and End Task, and multi-process headers get a `✕` that kills every instance after a confirmation.
- State survives refreshes through `_expandedGroups` and the icon cache; auto-refresh is a 3 s interval.

## Generic patterns worth remembering

- A widget's own `js_modules` run on the host's main thread: honour `window.__coreframeDragging`, listen for `coreframe-dragend` to repaint, wrap render callbacks in try/catch, and skip DOM writes when the value hash is unchanged.
- `js_modules` are injected in parallel, so a multi-file frontend must not assume load order: set a flag at the end of each file and have the entry point wait for all of them (a partially initialised widget with a `ready` flag set is a silent, permanent failure).
- `coreframe.extensions.<mod>` imports the package `__init__`, which pulls in Flask and the whole loader. Anything that must run cold — the `--ext-runner` child above all — cannot import through the package.
