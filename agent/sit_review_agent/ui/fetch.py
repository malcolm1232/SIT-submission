"""A pasted ``https://`` link to a PDF on the drop screen (decision #39, 2026-10-03).

The server downloads the PDF before it starts the run, with the URL policy's checks
(``config/url_policy.yaml``: deny or allow domains, through ``tools.policy.check_urls``; the link the
person typed is its own source, so ``fetch_only_from_results`` is met by construction) and these
of its own: https only, no user name or password in the link, a host whose every address is public
(no loopback, private, link-local or reserved address: the page must not become a way into this
laptop's network), the same checks again on each redirect (at most :data:`MAX_REDIRECTS`), at most
:data:`MAX_BYTES` (refused on the declared length before reading, and while streaming), and a body
that starts with ``%PDF-``. The file is saved with the run's other inputs, under
``runs/<id>/ui/input/``, so the command the page shows names the saved file.

Known limit: the host is resolved for the check and again by the HTTP client, so a DNS answer that
changes between the two (rebinding) is not caught.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import unquote, urljoin, urlsplit

import httpx

from sit_review_agent.config import UrlPolicy
from sit_review_agent.tools.policy import SeenUrls, check_urls
from sit_review_agent.ui.launcher import safe_name

MAX_BYTES = 50 * 1024 * 1024
MAX_REDIRECTS = 5
MAX_URL_CHARS = 2048
TIMEOUT_S = 60.0

Resolve = Callable[[str], list[str]]


class LinkRefused(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@dataclass(frozen=True)
class Fetched:
    name: str
    data: bytes
    final_url: str


def resolve_host(host: str) -> list[str]:
    """Every address ``host`` resolves to (blocking; :func:`fetch_pdf` calls it in a thread)."""
    try:
        return sorted({str(i[4][0]) for i in socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)})
    except OSError:
        return []


def _mb(n: int) -> str:
    return f"{n // (1024 * 1024)} MB" if n >= 1024 * 1024 else f"{n} bytes"


def file_name(url: str) -> str:
    """The saved name: the link's last path segment, made safe, ending in ``.pdf``. The page's
    preview of the command derives the same name in the same way."""
    seg = PurePosixPath(unquote(urlsplit(url).path)).name
    name = safe_name(seg)
    return name if name.lower().endswith(".pdf") else f"{name}.pdf"


def check_link(url: str, policy: UrlPolicy, resolve: Resolve) -> None:
    """Raise :class:`LinkRefused` with the reason, or return when ``url`` may be fetched."""
    if not url or len(url) > MAX_URL_CHARS or any(c.isspace() for c in url):
        raise LinkRefused("The link is not one link: paste a single https:// address with no spaces.")
    try:
        p = urlsplit(url)
        host = (p.hostname or "").lower()
        _ = p.port
    except ValueError:
        raise LinkRefused("The link does not parse as a URL.") from None
    if p.scheme.lower() != "https":
        raise LinkRefused("Only an https:// link is accepted.")
    if p.username is not None or p.password is not None:
        raise LinkRefused("A link with a user name or password in it is refused.")
    if not host:
        raise LinkRefused("The link has no host.")
    seen = SeenUrls()
    seen.add([url])
    why = check_urls({"url": url}, policy, seen)
    if why:
        raise LinkRefused(f"The URL policy refuses this link: {why}.")
    try:
        addrs = [str(ipaddress.ip_address(host.strip("[]")))]      # an address typed as the host
    except ValueError:
        addrs = resolve(host)
    if not addrs:
        raise LinkRefused(f"The host {host} could not be resolved.")
    bad = [a for a in addrs if not ipaddress.ip_address(a.split("%", 1)[0]).is_global]
    if bad:
        raise LinkRefused(f"The host {host} resolves to a loopback, private or link-local address ({', '.join(bad)}), "
                          "which the page does not fetch. Download the file and drop it here instead.")


async def fetch_pdf(url: str, policy: UrlPolicy, *, transport: Any = None,
                    resolve: Resolve = resolve_host) -> Fetched:
    """Download the PDF at ``url``; raise :class:`LinkRefused` with the reason on any refusal."""
    async def check(u: str) -> None:
        await asyncio.to_thread(check_link, u, policy, resolve)

    current = url.strip()
    await check(current)
    async with httpx.AsyncClient(transport=transport, follow_redirects=False, timeout=TIMEOUT_S) as client:
        for _ in range(MAX_REDIRECTS + 1):
            try:
                async with client.stream("GET", current, headers={"Accept": "application/pdf"}) as res:
                    if res.is_redirect:
                        nxt = urljoin(current, res.headers.get("location", ""))
                        await check(nxt)
                        current = nxt
                        continue
                    if res.status_code != 200:
                        raise LinkRefused(f"The link returned HTTP {res.status_code}, not the file.")
                    declared = res.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > MAX_BYTES:
                        raise LinkRefused(f"The file is larger than {_mb(MAX_BYTES)}; the page fetches at most that.")
                    buf = bytearray()
                    async for chunk in res.aiter_bytes():
                        buf += chunk
                        if len(buf) > MAX_BYTES:
                            raise LinkRefused(f"The file is larger than {_mb(MAX_BYTES)}; the page fetches at most "
                                              "that.")
            except httpx.HTTPError as exc:
                raise LinkRefused(f"The download failed: {type(exc).__name__}.") from None
            data = bytes(buf)
            if not data.startswith(b"%PDF-"):
                raise LinkRefused("The link did not return a PDF (the file is not a PDF: it does not start with "
                                  "%PDF-). A page that asks you to sign in returns HTML; download the file and drop "
                                  "it here instead.")
            return Fetched(name=file_name(url), data=data, final_url=current)
    raise LinkRefused(f"The link took more than {MAX_REDIRECTS} redirects.")
