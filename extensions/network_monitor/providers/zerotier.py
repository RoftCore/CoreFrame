from .base import BaseProvider

class ZeroTierProvider(BaseProvider):
    id = "zerotier"; name = "ZeroTier"
    keywords = ["zerotier"]
    tunnel_services = ["ZeroTierOne"]
    tunnel_procs = []; all_procs = ["zerotier-one.exe"]
    skip_rasdial = True
