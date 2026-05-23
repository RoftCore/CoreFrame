from .base import BaseProvider


class WindscribeProvider(BaseProvider):
    id = "windscribe"
    name = "Windscribe"
    keywords = ["windscribe"]
    tunnel_services = ["WindscribeService"]
    app_services = []
    tunnel_procs = ["windscribeopenvpn.exe"]
    all_procs = ["windscribe.exe", "windscribeopenvpn.exe"]
    cli_name = "windscribe.exe"
    cli_connect = ["connect", "best"]
    cli_disconnect = ["disconnect"]
    client_names = ["windscribe.exe"]
    skip_rasdial = True
    skip_cli_connect = True  # windscribe.exe es CLI+GUI, cualquier llamada abre la ventana
    _cli_search_dirs = [r"C:\Program Files\Windscribe"]

    def on_connect(self, extension):
        msgs = []
        adapters = extension._active_vpn_adapters()
        if any("windscribe" in a.lower() for a in adapters):
            msgs.append("Windscribe ya conectado")
        else:
            msgs.append("Windscribe: abre la app y conecta manualmente")
        return msgs
