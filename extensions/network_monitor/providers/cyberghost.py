from .base import BaseProvider

class CyberghostProvider(BaseProvider):
    id = "cyberghost"; name = "CyberGhost"
    keywords = ["cyberghost"]
    tunnel_procs = []; all_procs = ["cyberghost.exe"]
