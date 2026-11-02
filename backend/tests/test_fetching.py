import socket

import httpx
import pytest
from veriweb.fetching import UnsafeURL, download, fetch_source


@pytest.fixture
def public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    def resolve(host: str, port: int, **kwargs: object) -> list[tuple[object, ...]]:
        address = host if host in {"127.0.0.1", "224.0.0.1"} else "93.184.216.34"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)


async def test_redirect_private_address_is_rejected_before_connection(public_dns: None) -> None:
    seen: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"Location": "http://127.0.0.1/private"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(UnsafeURL):
            await download(client, "https://public.example/article")
    assert len(seen) == 1


async def test_rejects_multicast_targets(public_dns: None) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, text="unexpected"))
    ) as client:
        with pytest.raises(UnsafeURL):
            await download(client, "http://224.0.0.1/article")


async def test_page_size_is_bounded(public_dns: None) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"a" * 17))
    ) as client:
        with pytest.raises(ValueError, match="size limit"):
            await download(client, "https://public.example/article", max_bytes=16)


async def test_redirected_host_robots_policy_is_checked_before_reading_article(
    public_dns: None,
) -> None:
    seen: list[tuple[str, str]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        host = request.headers["host"]
        seen.append((host, request.url.path))
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200,
                text="User-agent: *\nDisallow: /blocked"
                if host == "other.example"
                else "User-agent: *\nAllow: /",
            )
        if host == "public.example":
            return httpx.Response(302, headers={"Location": "https://other.example/blocked"})
        return httpx.Response(
            200,
            headers={"Content-Type": "text/html"},
            text="<article><p>"
            + "Semiconductor research budgets fund manufacturing capacity. " * 30
            + "</p></article>",
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ValueError, match="disallows"):
            await fetch_source(client, "https://public.example/article", "s1")
    assert ("other.example", "/blocked") not in seen
