import ipaddress
from urllib.parse import urlsplit


def public_web_url(value: str) -> str | None:
    try:
        url = urlsplit(value.strip())
        host = url.hostname or ''
        if (
            url.scheme != 'https'
            or not host
            or url.username
            or url.password
            or url.query
            or url.fragment
            or url.port not in (None, 443)
        ):
            return None
        if host == 'localhost' or host.endswith(('.localhost', '.local')) or '.' not in host:
            return None
        try:
            if not ipaddress.ip_address(host).is_global:
                return None
        except ValueError:
            pass  # A DNS name; availability is checked by the user, not inferred here.
        return value.strip().rstrip('/')
    except ValueError:
        return None
