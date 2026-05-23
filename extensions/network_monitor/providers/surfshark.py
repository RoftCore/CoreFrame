from .base import BaseProvider

class SurfsharkProvider(BaseProvider):
    id = "surfshark"; name = "Surfshark"
    keywords = ["surfshark"]
    tunnel_procs = []; all_procs = ["surfshark.exe"]
