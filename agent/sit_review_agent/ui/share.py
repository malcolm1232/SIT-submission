"""The Share link action of a finished review (decision #36, 2026-10-03).

A server bound to a non-loopback address (``dra ui --host 0.0.0.0 --allow-remote``) shows the page's
own address on this laptop's current network: the IPv4 address of the interface that carries the
default route, found by asking the kernel which local address a UDP socket would use (no packet is
sent). A loopback-only server shows the one line that restarts it shared instead of a link. No
tunnel, no hosted service, nothing stored: the link works while this server runs on this network.
"""

from __future__ import annotations

import ipaddress
import shlex
import socket
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

SHARE_TEXT = ("Anyone on this network can open this link while this laptop serves it; there is no login, and "
              "the link dies when the server stops.")
LOOPBACK_TEXT = ("This server answers this laptop only, so there is no link to share. To share the page on this "
                 "network, stop the server and start it again with:")
NO_ADDRESS_TEXT = ("The server listens on every interface, but this laptop has no network address other than "
                   "loopback right now. Join a network and open this again.")
#: A documentation address (RFC 5737): connecting a UDP socket to it picks the outgoing interface, sends nothing.
_PROBE = ("192.0.2.1", 9)


def _usable(ip: str | None) -> bool:
    try:
        a = ipaddress.ip_address(ip or "")
    except ValueError:
        return False
    return a.version == 4 and not (a.is_loopback or a.is_unspecified or a.is_link_local or a.is_multicast)


def lan_ipv4() -> str | None:
    """This laptop's IPv4 address on its current network, or ``None`` when it has none."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(_PROBE)
            ip = s.getsockname()[0]
        if _usable(ip):
            return ip
    except OSError:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = str(info[4][0])
            if _usable(ip):
                return ip
    except OSError:
        pass
    return None


def is_loopback(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def share_info(*, bind_host: str, port: int, run_id: str, ui_args: list[str],
               lan_ip: Callable[[], str | None]) -> dict[str, Any]:
    """``mode`` ``network`` with the link, ``loopback`` with the restart line, or ``no_address``."""
    if is_loopback(bind_host):
        restart = shlex.join(["dra", "ui", "--host", "0.0.0.0", "--allow-remote", "--port", str(port), *ui_args])
        return {"mode": "loopback", "url": None, "text": LOOPBACK_TEXT, "restart": restart}
    ip = lan_ip() if bind_host in ("0.0.0.0", "::", "") else bind_host
    if not ip:
        return {"mode": "no_address", "url": None, "text": NO_ADDRESS_TEXT, "restart": None}
    host = f"[{ip}]" if ":" in ip else ip
    return {"mode": "network", "url": f"http://{host}:{port}/?run={quote(run_id, safe='')}", "text": SHARE_TEXT,
            "restart": None}
