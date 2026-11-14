"""Explicit Telegram transport selection; never fall back from proxy to direct."""

from urllib.parse import urlsplit


def proxy_url(value: str | None) -> str | None:
    value = (value or '').strip()
    if not value or value == 'direct':
        return None
    try:
        url = urlsplit(value)
        if (
            url.scheme not in ('socks5', 'socks4', 'http')
            or not url.hostname
            or url.port is None
            or url.path not in ('', '/')
            or url.query
            or url.fragment
        ):
            raise ValueError
    except ValueError:
        raise ValueError('Invalid BOT_PROXY_URL: expected socks5/socks4/http host:port') from None
    return value
