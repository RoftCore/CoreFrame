# CoreFrame

Centro de control personal que unifica ciberseguridad, monitoreo del sistema, gestión de proyectos y notas en una sola interfaz web.

## Stack

- **Backend:** Python (Flask + Flask-SocketIO + WebSocket)
- **Frontend:** HTML, CSS, JavaScript vanilla (sin frameworks)
- **Extensiones:** Sistema modular con carga dinámica vía importlib

## Requisitos

`
pip install -r requirements.txt
`

## Uso

`
python app.py
`

Abrir en el navegador: http://127.0.0.1:5000

## Estructura

`
coreframe/
+-- app.py
+-- requirements.txt
+-- extensions.json
+-- static/
|   +-- index.html
|   +-- css/
|   +-- js/
|   +-- img/
+-- extensions/
|   +-- network_monitor/
|   +-- system_monitor/
|   +-- vault_manager/
+-- README.md
`

## Crear una extensión

1. Crear carpeta en extensions/mi_extension/
2. Crear extension.json con widgets, menús y acciones
3. Crear main.py con clase Extension y métodos para cada acción
4. ¡Listo! El núcleo la carga automáticamente al iniciar

## Seguridad

- Corre solo en 127.0.0.1 (localhost)
- Sin autenticación (entorno local)
- CORS deshabilitado

onecode



