from .base import BaseProvider

class HamachiProvider(BaseProvider):
    id = "hamachi"; name = "Hamachi"
    keywords = ["hamachi"]
    tunnel_services = ["Hamachi2Svc"]
    tunnel_procs = []; all_procs = ["hamachi.exe", "hamachi-2.exe"]
