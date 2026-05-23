# CoreFrame

Centro de control personal con panel HUD, monitoreo del sistema, control VPN universal, gestor de notas y análisis de red.

## Stack

- **Backend:** Python 3 (Flask + Flask-SocketIO)
- **Frontend:** HTML, CSS, JavaScript vanilla (sin frameworks)
- **WebSocket:** Tiempo real para CPU, RAM, GPU, disco
- **Extensiones:** Sistema modular con carga dinámica vía importlib

## Captura

Panel tipo HUD con widgets en tiempo real, menú lateral de extensiones, panel de resultados deslizable, y conexión WebSocket permanente.

## Requisitos

```
pip install -r requirements.txt
```

## Uso

Ejecutar `run.vbs` (se auto-eleva con UAC para permisos de administrador).

Alternativa manual:
```
python app.py
```

Abrir en el navegador: http://127.0.0.1:5000

## Características

### Network Monitor
- **IP pública** — widget con detección de ubicación y proxy/VPN
- **VPN universal** — conecta/desconecta Proton, Nord, Mullvad, Windscribe y más
  - Arquitectura por módulos: cada VPN es un provider separado en `providers/`
  - Detección automática de proveedor activo por servicios y adaptadores
  - Killswitch vía CLI (Proton) con detección disponible/no disponible
  - Smart GUI restart: solo relanza el cliente si ya estaba abierto
- **DNS leak test** — verifica si las consultas DNS viajan por el túnel VPN
- **Conexiones activas** — tabla con proto, IPs, estado y proceso (PID)
- **Escaneo de puertos** — puertos comunes abiertos en localhost
- **Forzar DNS** — establece Cloudflare 1.1.1.1 en el adaptador VPN

### System Monitor
- CPU, RAM, GPU, disco en tiempo real
- Histogramas con los últimos 40 valores
- Broadcast vía WebSocket cada 1s

### Vault Manager
- Gestor de notas con persistencia JSON
- Creación, listado, exportación

## Seguridad

- Bind a `127.0.0.1` (no accesible desde LAN/Internet)
- CORS restringido a `http://127.0.0.1:5000`
- Token SHA-256 generado al arrancar, exigido en toda API (`X-CoreFrame-Token`)

## Estructura

```
coreframe/
├── app.py                  # Servidor Flask + SocketIO
├── controller.ps1          # Icono en bandeja + manejo de parada
├── run.vbs                 # Lanzador con auto-elevación UAC
├── requirements.txt
├── extensions.json
├── static/
│   ├── index.html          # SPA
│   ├── css/                # paleta, layout, componentes, efectos
│   └── js/                 # core.js, menu.js, widgets.js, utils.js
└── extensions/
    ├── network_monitor/
    │   ├── main.py         # Lógica universal (IP, VPN, DNS, puertos)
    │   ├── extension.json
    │   └── providers/      # Módulos por VPN
    │       ├── base.py     # Clase base BaseProvider
    │       ├── proton.py
    │       ├── windscribe.py
    │       ├── nord.py
    │       └── ... (13 proveedores)
    ├── system_monitor/
    │   ├── main.py         # CPU, RAM, GPU, disco
    │   └── extension.json
    └── vault_manager/
        ├── main.py         # Notas con persistencia
        └── extension.json
```

## Crear una extensión

1. Crear carpeta en `extensions/mi_extension/`
2. Crear `extension.json` con widgets, menús y acciones
3. Crear `main.py` con clase `Extension` y métodos para cada acción
4. El núcleo la carga automáticamente al iniciar

## Añadir un proveedor VPN

1. Crear `extensions/network_monitor/providers/mi_vpn.py`
2. Heredar de `BaseProvider` y definir atributos (keywords, servicios, procesos, CLI)
3. No tocar `main.py`
