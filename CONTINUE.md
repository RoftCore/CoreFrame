# CONTINUE — Proyecto CoreFrame (23/05/2026)

## Estado actual

### Hecho
- Control VPN en HUD: menú contextual con Conectar/Desconectar + Configurar
- Desconexión universal: `sc stop` → `rasdial /d` → `netsh disable` → `taskkill` (túnel) → `taskkill` (todo)
- Conexión universal: `sc start` → `netsh enable` → lanzar cliente GUI → `rasdial` → comando personalizado
- El proceso se auto-eleva vía `run.vbs` para que `sc`/`netsh`/`taskkill` funcionen sobre servicios del sistema
- Servicios de túnel vs GUI separados: disconnect solo para `ProtonVPN WireGuard`, NO para `ProtonVPN Service`
- `run.vbs` con self-elevation via ShellExecute + runas

### Fix reconnect + provider-awareness (23/05/2026)
**Problema original**: `sc start "ProtonVPN WireGuard"` inicia el túnel pero no sabe a qué servidor conectarse. CLI añadido como solución.

**Problema real reportado por Arnau**: al desconectar Proton, CoreFrame abrió Windscribe porque `_universal_connect` ejecutaba `sc start` sobre **todos** los servicios VPN (`VPN_ALL_SERVICES` incluye `WindscribeService`). Lo mismo al reconectar. `adapter_keywords` incluía "windscribe" junto a "proton", mezclando la detección.

**Solución definitiva — refactor provider-aware**:
- Eliminadas las listas planas `VPN_TUNNEL_SERVICES`, `VPN_APP_SERVICES`, `VPN_ALL_SERVICES`, `TUNNEL_PROCESS_NAMES`, `ALL_VPN_PROCESS_NAMES`, `VPN_CLI_DEFS`.
- Creado `PROVIDER_MAP`: diccionario con 12 proveedores mapeados (proton, windscribe, nord, mullvad, tailscale, zerotier, express, surfshark, cyberghost, pia, wireguard, hamachi, openvpn, generic).
- Cada proveedor tiene: keywords, tunnel_services, app_services, tunnel_procs, all_procs, cli_name, cli_connect/disconnect args, client_names.
- **`_detect_active_providers()`**: escanea servicios en ejecución (`sc query`) + adaptadores activos para identificar qué proveedor(es) están operando.
- **`_universal_disconnect()`**: solo para servicios/procesos de los proveedores activos detectados.
- **`_universal_connect()`**: solo para servicios/procesos del proveedor configurado o detectado.
- **`_resolve_target_providers()`**: resuelve qué proveedor atacar (configurado → detectado → ninguno).
- **`_detect_cli(provider_hint)`**: ahora acepta un hint de proveedor para buscar el CLI correcto.
- **`_cli_connect/disconnect`**: ejecutan CLI para cada proveedor detectado, no solo el primero.
- **`_find_vpn_client()`**: busca clients solo del proveedor activo/configurado, no de todos.
- **`check_vpn()` / `get_vpn_status()`**: resuelven el nombre real del proveedor desde los adaptadores.
- **`vpn_config.json`**: `adapter_keywords` limpiado (quitado windscribe, nord, etc. — solo proton, wireguard, tun, tap).
- **`DEFAULT_VPN_CONFIG`**: lo mismo, keywords reducidos a lo esencial.

### Pendiente / Bugs
1. **Probar en sistema real**: abrir CoreFrame (UAC → Yes), probar Conectar/Desconectar, ver mensajes en el panel
2. **Verificar elevación**: cuando run.vbs se eleva, el PowerShell que lanza controller.ps1 debería heredar admin. Verificar si los subprocess de Python también lo heredan.

### Archivos modificados en esta sesión
- `run.vbs` — self-elevation
- `extensions/network_monitor/main.py` — universal disconnect/connect, servicios separados, path detection, CLI detection + CLI connect/disconnect
- `static/js/core.js` — función `showVpnMenu()` con feedback
- `static/css/components.css` — `.widget-btn` standalone
- `static/css/layout.css` — `#hud-vpn` cursor pointer + hover glow
