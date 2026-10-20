"""Fetch a page's <title> safely.

The server fetches URLs that users submit, so it must not become a proxy into private networks (SSRF):
only http(s), every hop's host must resolve to public IP addresses, at most 3 redirects, a 5 s timeout and a
256 KB read cap.
"""
import asyncio
import html
import ipaddress
import re
import socket
from urllib.parse import urljoin, urlsplit

import httpx

MAX_BYTES = 256 * 1024
MAX_REDIRECTS = 3
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


class UnsafeURL(Exception):
    pass


async def assert_public(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeURL("only http(s) URLs with a host are fetched")
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(parts.hostname, parts.port or 443,
                                                             type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UnsafeURL(f"cannot resolve host: {exc}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global:
            raise UnsafeURL(f"host resolves to a non-public address ({ip})")


async def fetch_title(url: str, client: httpx.AsyncClient | None = None) -> str | None:
    own = client is None
    client = client or httpx.AsyncClient(timeout=5.0, follow_redirects=False,
                                         headers={"User-Agent": "LinkMindBot/1.0"})
    try:
        for _ in range(MAX_REDIRECTS + 1):
            await assert_public(url)
            async with client.stream("GET", url) as resp:
                if resp.is_redirect and "location" in resp.headers:
                    url = urljoin(url, resp.headers["location"])
                    continue
                if "html" not in resp.headers.get("content-type", ""):
                    return None
                body = b""
                async for chunk in resp.aiter_bytes():
                    body += chunk
                    if len(body) >= MAX_BYTES:
                        break
                m = TITLE_RE.search(body.decode(resp.encoding or "utf-8", errors="replace"))
                return html.unescape(" ".join(m.group(1).split()))[:300] if m else None
        return None
    finally:
        if own:
            await client.aclose()
