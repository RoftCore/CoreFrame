def _is_safe_url(url):
    """Validate URL to prevent SSRF. Only allows HTTPS, blocks private/internal IPs."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        if parsed.scheme not in ('https',):
            return False
        hostname = parsed.hostname or ''
        if not hostname:
            return False
        import ipaddress
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        except ValueError:
            if hostname in ('localhost', '127.0.0.1', '0.0.0.0', '::1'):
                return False
            if hostname.endswith('.local') or hostname.endswith('.internal') or hostname.endswith('.localhost'):
                return False
        return True
    except Exception:
        return False
