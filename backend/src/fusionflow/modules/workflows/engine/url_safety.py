"""Guards `http.request`'s tenant-configurable `url` against SSRF.

That node lets any tenant with ordinary workflow access make a server-side
request to a URL of their choosing (interpolated from their own config) -
nothing previously stopped that URL from pointing at an internal service or
the cloud metadata endpoint (`169.254.169.254`). `ensure_public_http_url`
must be called on the fully-interpolated URL before the real request is made.

Known limitation: this resolves the hostname once, ahead of the real
request, so a DNS-rebinding attacker (whose resolver returns a public
address here and a private one moments later, at connection time) is not
fully closed off by this alone - doing that would require pinning the
actual request to the exact address validated here (a custom transport),
which is a larger change. This still blocks the overwhelmingly common
case: a literal internal IP/hostname, or a domain that always resolves
privately.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

_ALLOWED_SCHEMES = {"http", "https"}
_BLOCKED_HOSTNAMES = {"localhost"}


class UnsafeUrlError(ValueError):
    """`url` is not allowed: unsupported scheme, no hostname, or resolves
    to a non-public address."""


def _resolve_addresses(hostname: str) -> list[str]:
    """Split out so tests can monkeypatch DNS resolution instead of
    depending on real network/DNS access."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise UnsafeUrlError(f"could not resolve host {hostname!r}") from exc
    return [info[4][0] for info in infos]


def ensure_public_http_url(url: str) -> None:
    """Raises `UnsafeUrlError` unless `url` is an http(s) URL whose
    hostname resolves only to public, non-internal addresses."""
    parsed = urlsplit(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise UnsafeUrlError(f"unsupported URL scheme {parsed.scheme!r} - only http/https are allowed")

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeUrlError("URL has no hostname")
    lowered = hostname.lower()
    if lowered in _BLOCKED_HOSTNAMES or lowered.endswith(".local"):
        raise UnsafeUrlError(f"host {hostname!r} is not allowed")

    for raw_ip in _resolve_addresses(hostname):
        ip = ipaddress.ip_address(raw_ip)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise UnsafeUrlError(f"host {hostname!r} resolves to a non-public address ({ip}) - blocked")
