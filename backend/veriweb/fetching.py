import asyncio
import ipaddress
import re
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

import httpx
import trafilatura
from bs4 import BeautifulSoup

from veriweb.schemas import Source
from veriweb.sources import article_links, source_type, table_text

USER_AGENT = "VeriwebResearch/0.1"
MAX_BYTES = 2_000_000


class UnsafeURL(ValueError):
    """A target cannot be safely fetched by the public-web researcher."""


async def resolve_public(url: str) -> tuple[str, str]:
    parsed = urlsplit(url)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
    ):
        raise UnsafeURL("Only public HTTP(S) URLs without credentials are supported")
    host = parsed.hostname
    if host.lower() == "localhost" or host.lower().endswith((".localhost", ".local", ".internal")):
        raise UnsafeURL("Private hosts are not supported")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = await asyncio.wait_for(
            asyncio.to_thread(socket.getaddrinfo, host, port, type=socket.SOCK_STREAM), timeout=4
        )
        ips = [str(row[4][0]) for row in addresses]
        if not ips or any(
            not ipaddress.ip_address(ip).is_global or ipaddress.ip_address(ip).is_multicast
            for ip in ips
        ):
            raise UnsafeURL("The target resolves to a non-public address")
    except (socket.gaierror, TimeoutError, ValueError) as exc:
        raise UnsafeURL("Cannot resolve a safe public address") from exc
    return host, ips[0]


async def validate_public_url(url: str) -> str:
    await resolve_public(url)
    return url


async def download(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int = MAX_BYTES,
    before_request: Callable[[str], Awaitable[None]] | None = None,
) -> tuple[str, str, str]:
    for _ in range(5):
        host, ip = await resolve_public(url)
        if before_request is not None:
            await before_request(url)
        parts = urlsplit(url)
        port = parts.port
        authority = f"[{ip}]" if ":" in ip else ip
        if port:
            authority += f":{port}"
        pinned = urlunsplit((parts.scheme, authority, parts.path or "/", parts.query, ""))
        # Pin the validated address while preserving TLS SNI and HTTP virtual-host routing.
        async with client.stream(
            "GET",
            pinned,
            headers={"Host": parts.netloc, "User-Agent": USER_AGENT},
            extensions={"sni_hostname": host},
        ) as response:
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("Redirect has no destination")
                url = urljoin(url, location)
                continue
            response.raise_for_status()
            chunks = bytearray()
            async for chunk in response.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) > max_bytes:
                    raise ValueError("Page exceeds extraction size limit")
            encoding = response.encoding or "utf-8"
            return (
                bytes(chunks).decode(encoding, errors="replace"),
                url,
                response.headers.get("content-type", ""),
            )
    raise ValueError("Too many redirects")


async def check_robots(client: httpx.AsyncClient, url: str) -> None:
    parts = urlsplit(url)
    robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
    try:
        robots, _, _ = await download(client, robots_url, max_bytes=256_000)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code not in {404, 410}:
            raise ValueError("Robots policy unavailable; source skipped") from exc
    else:
        policy = RobotFileParser()
        policy.parse(robots.splitlines())
        if not policy.can_fetch(USER_AGENT, url):
            raise ValueError("Source disallows automated access")
        raw_delay = policy.crawl_delay(USER_AGENT)
        delay = float(raw_delay) if raw_delay is not None else 0.0
        if delay and delay > 0:
            if delay > 5:
                raise ValueError("Source crawl delay exceeds this run's budget")
            await asyncio.sleep(delay)


async def fetch_source(client: httpx.AsyncClient, url: str, identifier: str) -> Source:
    async def policy(target: str) -> None:
        await check_robots(client, target)

    html, final_url, content_type = await download(client, url, before_request=policy)
    if "html" not in content_type and "text/plain" not in content_type:
        raise ValueError("Source is not an HTML article")
    extracted = await asyncio.to_thread(
        trafilatura.extract,
        html,
        url=final_url,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
    )
    if not extracted or len(extracted.strip()) < 180:
        raise ValueError("Insufficient article text extracted")
    soup = BeautifulSoup(html[:500_000], "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else urlsplit(final_url).hostname
    date_tag = soup.find("meta", attrs={"property": "article:published_time"}) or soup.find(
        "meta",
        attrs={"name": re.compile(r"^(?:citation_publication_date|date|dc.date|pubdate)$", re.I)},
    )
    date = str(date_tag.get("content"))[:100] if date_tag and date_tag.get("content") else None
    tables = table_text(soup)
    if tables:
        extracted = tables + "\n\n" + extracted
    return Source(
        id=identifier,
        title=(title or "Untitled source")[:500],
        url=final_url,
        text=extracted[:100_000],
        published_at=date,
        source_type=source_type(final_url, title or ""),
        links=article_links(soup, final_url),
    )
